"""Integration tests for the REST API endpoints (riskmatris.routes.api)."""

from app import MAX_TITLE_LENGTH

# ---------------------------------------------------------------------------
# /health endpoint (integration test with httpx)
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """Tests that /health responds correctly via the FastAPI TestClient."""

    def test_health_returns_ok(self, test_client):
        resp = test_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "active_sessions" in data
        assert isinstance(data["active_sessions"], int)
        assert "db_path" in data


# ---------------------------------------------------------------------------
# POST /api/sessions (title sanitization + rate limit, integration)
# ---------------------------------------------------------------------------


class TestCreateSessionHardening:
    def test_title_sanitized_before_storing(self, isolated_client):
        resp = isolated_client.post("/api/sessions", json={"title": "Foo\x00Bar\nBaz\u202eRTL"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "FooBarBazRTL"

    def test_whitespace_only_title_falls_back_to_default(self, isolated_client):
        resp = isolated_client.post("/api/sessions", json={"title": "  \n\x00 "})
        assert resp.status_code == 200
        assert resp.json()["title"] == "Riskanalys"

    def test_overlong_title_clamped(self, isolated_client):
        resp = isolated_client.post("/api/sessions", json={"title": "x" * 500})
        assert resp.status_code == 200
        assert len(resp.json()["title"]) == MAX_TITLE_LENGTH

    def test_rate_limit_returns_429(self, isolated_client, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "SESSION_CREATE_LIMIT", 1)
        assert isolated_client.post("/api/sessions", json={"title": "First"}).status_code == 200
        assert isolated_client.post("/api/sessions", json={"title": "Second"}).status_code == 429


# ---------------------------------------------------------------------------
# client_id clamping (unbounded query input otherwise)
# ---------------------------------------------------------------------------


class TestClientIdClamping:
    def test_long_client_id_is_clamped(self, monkeypatch, tmp_path, add_session, test_client):
        import app as app_module

        monkeypatch.setattr(app_module, "DB_PATH", str(tmp_path / "test.db"))
        app_module.init_db()
        sid = "CLAMPID"
        add_session(sid)
        long_id = "x" * 300
        with test_client.websocket_connect(f"/ws/{sid}?role=participant&client_id={long_id}") as ws:
            ws.receive_json()  # drain the on-connect broadcast
            ws.send_json({"action": "vote", "probability": 2, "consequence": 2})
            ws.receive_json()
        votes = app_module.SESSIONS[sid]["risks"][0]["votes"]
        assert len(votes) == 1
        key = next(iter(votes))
        assert len(key) <= app_module.MAX_CLIENT_ID_LENGTH


# ---------------------------------------------------------------------------
# QR endpoint URL limit
# ---------------------------------------------------------------------------


class TestQrUrlLimit:
    def test_long_url_rejected_with_400(self, add_session, test_client):
        sid = "QRTEST1"
        add_session(sid)
        resp = test_client.get(f"/api/sessions/{sid}/qr.svg?url={'a' * 2000}")
        assert resp.status_code == 400

    def test_short_url_returns_svg(self, add_session, test_client):
        sid = "QRTEST2"
        add_session(sid)
        resp = test_client.get(f"/api/sessions/{sid}/qr.svg?url=http://localhost:8000/s/{sid}")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/svg+xml"


# ---------------------------------------------------------------------------
# Per-IP rate limit on read endpoints (sakerhetsrapport A01-3: session-code
# enumeration via 404 probing on /api/sessions/{sid}, qr.svg, export.csv,
# ws-ticket)
# ---------------------------------------------------------------------------


class TestReadRateLimit:
    def test_session_info_returns_429_over_limit(self, isolated_client, add_session, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "SESSION_READ_LIMIT", 2)
        sid = "READLIM1"
        add_session(sid)
        assert isolated_client.get(f"/api/sessions/{sid}").status_code == 200
        assert isolated_client.get(f"/api/sessions/{sid}").status_code == 200
        resp = isolated_client.get(f"/api/sessions/{sid}")
        assert resp.status_code == 429

    def test_failed_lookups_count_toward_limit(self, isolated_client, monkeypatch):
        """404 probing of unknown session codes must be throttled, not free."""
        import app as app_module

        monkeypatch.setattr(app_module, "SESSION_READ_LIMIT", 2)
        assert isolated_client.get("/api/sessions/NOPE01").status_code == 404
        assert isolated_client.get("/api/sessions/NOPE02").status_code == 404
        assert isolated_client.get("/api/sessions/NOPE03").status_code == 429

    def test_qr_export_and_ticket_share_the_read_budget(self, isolated_client, add_session, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "SESSION_READ_LIMIT", 3)
        sid = "READLIM2"
        add_session(sid, admin_token="tok")
        assert isolated_client.get(f"/api/sessions/{sid}/qr.svg?url=http://x/s/{sid}").status_code == 200
        assert isolated_client.get(f"/api/sessions/{sid}/export.csv").status_code == 200
        assert isolated_client.get(f"/api/sessions/{sid}/ws-ticket", headers={"X-Admin-Token": "tok"}).status_code == 200
        assert isolated_client.get(f"/api/sessions/{sid}/qr.svg?url=http://x/s/{sid}").status_code == 429

    def test_health_is_not_rate_limited(self, isolated_client, monkeypatch):
        """The health endpoint is used by Docker HEALTHCHECK and must stay free."""
        import app as app_module

        monkeypatch.setattr(app_module, "SESSION_READ_LIMIT", 1)
        for _ in range(5):
            assert isolated_client.get("/health").status_code == 200


# ---------------------------------------------------------------------------
# CSV export: formula injection (sakerhetsrapport A03-1)
# ---------------------------------------------------------------------------


class TestCsvFormulaInjection:
    def test_malicious_label_is_escaped_in_export(self, add_session, test_client):
        import csv
        import io

        sid = "CSVEVIL1"
        session = add_session(sid)
        session["risks"][0]["label"] = "=cmd|' /C calc'!A1"
        resp = test_client.get(f"/api/sessions/{sid}/export.csv")
        assert resp.status_code == 200
        text = resp.content.decode("utf-8-sig")  # strip the BOM
        rows = list(csv.reader(io.StringIO(text), delimiter=";"))
        data_row = next(r for r in rows if r and r[0] == "#1")
        # The label cell must be prefixed with an apostrophe so Excel/LibreOffice
        # treats it as text instead of evaluating it as a formula
        assert data_row[1] == "'=cmd|' /C calc'!A1"

    def test_normal_label_is_unchanged_in_export(self, add_session, test_client):
        import csv
        import io

        sid = "CSVOK01"
        session = add_session(sid)
        session["risks"][0]["label"] = "Brandrisk i lager"
        resp = test_client.get(f"/api/sessions/{sid}/export.csv")
        assert resp.status_code == 200
        text = resp.content.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text), delimiter=";"))
        data_row = next(r for r in rows if r and r[0] == "#1")
        assert data_row[1] == "Brandrisk i lager"
