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
