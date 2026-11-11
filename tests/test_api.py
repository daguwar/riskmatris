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
# Per-IP rate limit on read endpoints (session-code
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
        assert (
            isolated_client.get(f"/api/sessions/{sid}/ws-ticket", headers={"X-Admin-Token": "tok"}).status_code == 200
        )
        assert isolated_client.get(f"/api/sessions/{sid}/qr.svg?url=http://x/s/{sid}").status_code == 429

    def test_health_is_not_rate_limited(self, isolated_client, monkeypatch):
        """The health endpoint is used by Docker HEALTHCHECK and must stay free."""
        import app as app_module

        monkeypatch.setattr(app_module, "SESSION_READ_LIMIT", 1)
        for _ in range(5):
            assert isolated_client.get("/health").status_code == 200


# ---------------------------------------------------------------------------
# CSV export: formula injection
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


# ---------------------------------------------------------------------------
# CSV export language (?lang=sv|en, issue #9 phase 3)
# ---------------------------------------------------------------------------


class TestCsvLanguage:
    def test_default_is_swedish(self, add_session, test_client):
        sid = "CSVLANG1"
        add_session(sid)
        resp = test_client.get(f"/api/sessions/{sid}/export.csv")
        assert resp.status_code == 200
        assert "Risknivå" in resp.text

    def test_english_headers(self, add_session, test_client):
        sid = "CSVLANG2"
        add_session(sid)
        resp = test_client.get(f"/api/sessions/{sid}/export.csv?lang=en")
        assert resp.status_code == 200
        assert "Risk level" in resp.text
        assert "Risknivå" not in resp.text

    def test_invalid_lang_rejected(self, add_session, test_client):
        sid = "CSVLANG3"
        add_session(sid)
        resp = test_client.get(f"/api/sessions/{sid}/export.csv?lang=fr")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "invalid_lang"


# ---------------------------------------------------------------------------
# A01-4: admin token is only accepted via the X-Admin-Token header, never as
# a query parameter (tokens in URLs leak into logs/history/Referer)
# ---------------------------------------------------------------------------


class TestAdminTokenHeaderOnly:
    def test_query_param_is_not_accepted(self, add_session, test_client):
        sid = "AUTHQ01"
        add_session(sid, admin_token="sekret")
        resp = test_client.get(f"/api/sessions/{sid}?admin_token=sekret")
        assert resp.status_code == 200
        assert resp.json()["is_admin"] is False

    def test_header_is_accepted(self, add_session, test_client):
        sid = "AUTHH01"
        add_session(sid, admin_token="sekret")
        resp = test_client.get(f"/api/sessions/{sid}", headers={"X-Admin-Token": "sekret"})
        assert resp.status_code == 200
        assert resp.json()["is_admin"] is True

    def test_wrong_header_is_not_admin(self, add_session, test_client):
        sid = "AUTHW01"
        add_session(sid, admin_token="sekret")
        resp = test_client.get(f"/api/sessions/{sid}", headers={"X-Admin-Token": "fel"})
        assert resp.status_code == 200
        assert resp.json()["is_admin"] is False


# ---------------------------------------------------------------------------
# A05-2: /health must not leak the absolute DB path
# ---------------------------------------------------------------------------


class TestHealthDoesNotLeakDbPath:
    def test_db_path_is_a_constant(self, isolated_client, tmp_path):
        resp = isolated_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["db_path"] == "data/riskmatris.db"
        assert str(tmp_path) not in resp.text


# ---------------------------------------------------------------------------
# A03-5: QR endpoint returns a generic 500 – no internal exception details
# ---------------------------------------------------------------------------


class TestQrGenericError:
    def test_500_detail_does_not_leak_exception_text(self, add_session, test_client, monkeypatch):
        import qrcode

        def boom(*args, **kwargs):
            raise RuntimeError("internal path /app/secret/db.sqlite")

        monkeypatch.setattr(qrcode, "QRCode", boom)
        sid = "QRERR01"
        add_session(sid)
        resp = test_client.get(f"/api/sessions/{sid}/qr.svg?url=http://x/s/{sid}")
        assert resp.status_code == 500
        assert "/app/secret" not in resp.text
        assert "db.sqlite" not in resp.text


# ---------------------------------------------------------------------------
# A05-3: security headers on every HTTP response
# ---------------------------------------------------------------------------


class TestSecurityHeaders:
    def test_headers_on_api_response(self, test_client):
        resp = test_client.get("/health")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["Referrer-Policy"] == "no-referrer"
        assert resp.headers["X-Frame-Options"] == "DENY"
        csp = resp.headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
        assert "connect-src 'self' ws: wss:" in csp
        assert "frame-ancestors 'none'" in csp

    def test_headers_on_html_and_svg(self, add_session, test_client):
        sid = "HDR01"
        add_session(sid)
        for resp in (
            test_client.get("/"),
            test_client.get(f"/api/sessions/{sid}/qr.svg?url=http://x/s/{sid}"),
            test_client.get(f"/api/sessions/{sid}/export.csv"),
        ):
            assert resp.headers["X-Content-Type-Options"] == "nosniff"
            assert "default-src 'self'" in resp.headers["Content-Security-Policy"]
            assert resp.headers["Referrer-Policy"] == "no-referrer"


# ---------------------------------------------------------------------------
# A05-1: /docs, /redoc and /openapi.json are disabled by default
# ---------------------------------------------------------------------------


class TestDocsDisabledByDefault:
    def test_docs_redoc_openapi_are_404(self, test_client):
        assert test_client.get("/docs").status_code == 404
        assert test_client.get("/redoc").status_code == 404
        assert test_client.get("/openapi.json").status_code == 404


# ---------------------------------------------------------------------------
# Session expiry in API responses (drives the recent-sessions countdown on the
# landing page: entries show remaining time and drop out when expired)
# ---------------------------------------------------------------------------


class TestSessionExpiresAt:
    def test_session_info_includes_expires_at(self, add_session, test_client):
        import time

        import app as app_module

        session = add_session("EXPIR01")
        session["updated_at"] = time.time() - 100
        resp = test_client.get("/api/sessions/EXPIR01")
        assert resp.status_code == 200
        expires_at = resp.json()["expires_at"]
        assert abs(expires_at - (session["updated_at"] + app_module.SESSION_TTL_SECONDS)) < 5

    def test_create_response_includes_expires_at(self, isolated_client):
        import time

        resp = isolated_client.post("/api/sessions", json={"title": "Expiry", "threshold": 4})
        assert resp.status_code == 200
        expires_at = resp.json()["expires_at"]
        assert time.time() < expires_at <= time.time() + 48 * 3600 + 5
