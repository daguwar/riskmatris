"""Tests for the WebSocket endpoint lifecycle (riskmatris.routes.ws)."""

# ---------------------------------------------------------------------------
# WebSocket disconnect (regression: a disconnect used to deadlock the event loop)
# ---------------------------------------------------------------------------


class TestWebSocketDisconnect:
    """A disconnected client must be cleaned up and the endpoint must return.

    Regression test: WebSocketDisconnect used to be caught by the "except Exception"
    around receive_json(), so the handler spun in an infinite loop without yielding
    to the event loop – the whole server deadlocked on the first disconnect
    (closed tab/F5).
    """

    def test_disconnect_cleans_up_and_returns(self, add_session):
        import asyncio
        import threading
        from unittest.mock import AsyncMock, MagicMock

        from fastapi import WebSocketDisconnect

        from app import manager, websocket_endpoint

        sid = "TEST01"
        add_session(sid, admin_token="hemlig")

        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        # Simulate the client disconnecting immediately
        ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect(1000))

        result = {}

        def runner():
            try:
                asyncio.run(
                    asyncio.wait_for(
                        websocket_endpoint(ws, sid, role="participant", client_id="test-klient", ticket=""),
                        timeout=5,
                    )
                )
                result["ok"] = True
            except Exception as exc:
                result["ok"] = False
                result["error"] = exc

        # Run in a daemon thread: if the endpoint hangs (regression), the
        # test should fail via timeout instead of hanging the whole suite.
        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join(timeout=15)

        assert result.get("ok") is True, f"Endpoint did not return as expected: {result.get('error')}"
        # The connection must be removed after the disconnect
        assert sid not in manager.connections


# ---------------------------------------------------------------------------
# Origin check (sakerhetsrapport A01-2: cross-site WebSocket hijacking)
# ---------------------------------------------------------------------------


class TestWebSocketOriginCheck:
    """Browsers do not enforce same-origin on WebSocket handshakes – without
    a server-side check, any webpage can open a participant socket and vote
    if it knows the session code. Connections whose Origin does not match the
    request Host must be rejected with close code 1008. Connections without
    an Origin header (non-browser clients) are allowed; they are covered by
    connection/rate limits instead."""

    def test_foreign_origin_rejected(self, add_session, test_client):
        import pytest
        from starlette.websockets import WebSocketDisconnect

        sid = "ORIGIN1"
        add_session(sid)
        url = f"/ws/{sid}?role=participant&client_id=origin-check"
        origin = "https://evil.example"
        with pytest.raises(WebSocketDisconnect):
            with test_client.websocket_connect(url, headers={"Origin": origin}) as ws:
                ws.receive_json()
        # The rejected connection must not remain in the manager
        import app as app_module

        assert sid not in app_module.manager.connections

    def test_same_origin_allowed(self, add_session, test_client):
        sid = "ORIGIN2"
        add_session(sid)
        url = f"/ws/{sid}?role=participant&client_id=origin-check"
        # TestClient sends Host "testserver" – an Origin matching it must pass
        with test_client.websocket_connect(url, headers={"Origin": "http://testserver"}) as ws:
            data = ws.receive_json()
        assert data["type"] == "session_state"
        assert data["session_id"] == sid

    def test_same_origin_with_port_allowed(self, add_session, test_client):
        sid = "ORIGIN3"
        add_session(sid)
        url = f"/ws/{sid}?role=participant&client_id=origin-check"
        with test_client.websocket_connect(
            url, headers={"Origin": "http://localhost:8000", "Host": "localhost:8000"}
        ) as ws:
            data = ws.receive_json()
        assert data["type"] == "session_state"

    def test_origin_port_mismatch_rejected(self, add_session, test_client):
        import pytest
        from starlette.websockets import WebSocketDisconnect

        sid = "ORIGIN4"
        add_session(sid)
        url = f"/ws/{sid}?role=participant&client_id=origin-check"
        with pytest.raises(WebSocketDisconnect):
            with test_client.websocket_connect(
                url, headers={"Origin": "http://localhost:9999", "Host": "localhost:8000"}
            ) as ws:
                ws.receive_json()

    def test_malformed_origin_rejected(self, add_session, test_client):
        import pytest
        from starlette.websockets import WebSocketDisconnect

        sid = "ORIGIN5"
        add_session(sid)
        url = f"/ws/{sid}?role=participant&client_id=origin-check"
        with pytest.raises(WebSocketDisconnect):
            with test_client.websocket_connect(url, headers={"Origin": "http://[::1", "Host": "testserver"}) as ws:
                ws.receive_json()

    def test_missing_origin_allowed(self, add_session, test_client):
        """Non-browser clients (no Origin header) must not be blocked."""
        sid = "ORIGIN6"
        add_session(sid)
        url = f"/ws/{sid}?role=participant&client_id=origin-check"
        with test_client.websocket_connect(url) as ws:
            data = ws.receive_json()
        assert data["type"] == "session_state"


# ---------------------------------------------------------------------------
# Read rate limit on WS handshakes (sakerhetsrapport A01-3: the close codes
# 4004/1008/1013 would otherwise make session codes enumerable via WS)
# ---------------------------------------------------------------------------


class TestWebSocketReadRateLimit:
    def test_ws_connect_rate_limited_with_1013(self, add_session, test_client, monkeypatch):
        import pytest
        from starlette.websockets import WebSocketDisconnect

        import app as app_module

        monkeypatch.setattr(app_module, "SESSION_READ_LOG", {})
        monkeypatch.setattr(app_module, "SESSION_READ_LIMIT", 1)
        sid = "WSRATE1"
        add_session(sid)
        with test_client.websocket_connect(f"/ws/{sid}?role=participant&client_id=rl1") as ws:
            data = ws.receive_json()
            assert data["type"] == "session_state"
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with test_client.websocket_connect(f"/ws/{sid}?role=participant&client_id=rl2"):
                pass
        assert exc_info.value.code == 1013

    def test_ws_probe_of_unknown_session_also_limited(self, test_client, monkeypatch):
        """Repeated connects to non-existent sessions must be throttled."""
        import pytest
        from starlette.websockets import WebSocketDisconnect

        import app as app_module

        monkeypatch.setattr(app_module, "SESSION_READ_LOG", {})
        monkeypatch.setattr(app_module, "SESSION_READ_LIMIT", 2)
        for code in (4004, 4004):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with test_client.websocket_connect("/ws/NOPE01?role=participant&client_id=probe"):
                    pass
            assert exc_info.value.code == code
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with test_client.websocket_connect("/ws/NOPE02?role=participant&client_id=probe"):
                pass
        assert exc_info.value.code == 1013
