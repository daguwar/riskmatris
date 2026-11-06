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
# Origin check (cross-site WebSocket hijacking)
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
# Read rate limit on WS handshakes (the close codes
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


# ---------------------------------------------------------------------------
# Connection caps : per-IP and global limits on
# WS connections, rejected with close code 1013
# ---------------------------------------------------------------------------


class TestWebSocketConnectionCaps:
    def test_per_ip_cap_rejects_second_connection(self, add_session, test_client, monkeypatch):
        import pytest
        from starlette.websockets import WebSocketDisconnect

        import app as app_module

        monkeypatch.setattr(app_module, "WS_MAX_CONNECTIONS_PER_IP", 1)
        sid = "CAPIP01"
        add_session(sid)
        # TestClient connects all come from the same IP ("testclient"): the
        # first connection stays open, the second must be rejected.
        with test_client.websocket_connect(f"/ws/{sid}?role=participant&client_id=cap1") as ws1:
            assert ws1.receive_json()["type"] == "session_state"
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with test_client.websocket_connect(f"/ws/{sid}?role=participant&client_id=cap2"):
                    pass
            assert exc_info.value.code == 1013

    def test_global_cap_rejects_when_total_reached(self, add_session, test_client, monkeypatch):
        import pytest
        from starlette.websockets import WebSocketDisconnect

        import app as app_module

        monkeypatch.setattr(app_module, "WS_MAX_CONNECTIONS_TOTAL", 1)
        sid = "CAPTOT1"
        add_session(sid)
        with test_client.websocket_connect(f"/ws/{sid}?role=participant&client_id=tot1") as ws1:
            assert ws1.receive_json()["type"] == "session_state"
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with test_client.websocket_connect(f"/ws/{sid}?role=participant&client_id=tot2"):
                    pass
            assert exc_info.value.code == 1013

    def test_manager_connection_counters(self):
        from unittest.mock import MagicMock

        from app import ConnectionInfo, manager

        ws = MagicMock()
        manager.connections["CAPCNT1"] = [
            ConnectionInfo(websocket=ws, role="participant", client_id="a", is_admin=False, client_ip="1.1.1.1"),
            ConnectionInfo(websocket=ws, role="participant", client_id="b", is_admin=False, client_ip="2.2.2.2"),
        ]
        manager.connections["CAPCNT2"] = [
            ConnectionInfo(websocket=ws, role="participant", client_id="c", is_admin=False, client_ip="1.1.1.1"),
        ]
        try:
            assert manager.total_connection_count() == 3
            assert manager.count_connections_for_ip("1.1.1.1") == 2
            assert manager.count_connections_for_ip("2.2.2.2") == 1
            assert manager.count_connections_for_ip("9.9.9.9") == 0
            assert manager.count_connections_for_ip("") == 0
        finally:
            manager.connections.pop("CAPCNT1", None)
            manager.connections.pop("CAPCNT2", None)


# ---------------------------------------------------------------------------
# Per-connection message rate limit
# ---------------------------------------------------------------------------


class TestWebSocketMessageRateLimit:
    def test_messages_over_limit_get_error_not_broadcast(self, add_session, test_client, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "WS_MESSAGE_RATE_LIMIT", 2)
        monkeypatch.setattr(app_module, "WS_MESSAGE_RATE_WINDOW_SECONDS", 60)
        sid = "MSGRAT1"
        add_session(sid)
        with test_client.websocket_connect(f"/ws/{sid}?role=participant&client_id=rate1") as ws:
            assert ws.receive_json()["type"] == "session_state"  # on-connect broadcast
            ws.send_json({"action": "vote", "probability": 2, "consequence": 2})
            assert ws.receive_json()["type"] == "session_state"
            ws.send_json({"action": "vote", "probability": 3, "consequence": 3})
            assert ws.receive_json()["type"] == "session_state"
            # Third message within the window is rejected with an error
            ws.send_json({"action": "vote", "probability": 1, "consequence": 1})
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "meddelanden" in msg["message"]


# ---------------------------------------------------------------------------
# Broadcast cost: the shared payload is computed once
# per broadcast; only my_vote/is_admin differ per connection
# ---------------------------------------------------------------------------


class TestBroadcastSharedPayload:
    def test_broadcast_sets_per_connection_fields_on_shared_payload(self, make_session):
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        from app import ConnectionInfo, manager

        session = make_session(sid="BCAST01")
        session["risks"][0]["votes"] = {
            "alice": {"probability": 2, "consequence": 2, "updated_at": 0},
            "bob": {"probability": 3, "consequence": 3, "updated_at": 0},
        }
        ws_a, ws_b = MagicMock(), MagicMock()
        ws_a.send_json = AsyncMock()
        ws_b.send_json = AsyncMock()
        conn_a = ConnectionInfo(websocket=ws_a, role="participant", client_id="alice", is_admin=False)
        conn_b = ConnectionInfo(websocket=ws_b, role="participant", client_id="bob", is_admin=False)
        manager.connections["BCAST01"] = [conn_a, conn_b]
        try:
            asyncio.run(manager.broadcast(session))
            payload_a = ws_a.send_json.call_args[0][0]
            payload_b = ws_b.send_json.call_args[0][0]
            # Shared part is identical (computed once) ...
            assert payload_a["risks"] == payload_b["risks"]
            assert payload_a["cell_meta"] == payload_b["cell_meta"]
            # ... only the per-connection fields differ
            assert payload_a["my_vote"]["probability"] == 2
            assert payload_b["my_vote"]["probability"] == 3
            assert payload_a["is_admin"] is False
            # Each connection got its own top-level dict (no cross-talk)
            payload_a["risks"] = []
            assert payload_b["risks"] != []
        finally:
            manager.connections.pop("BCAST01", None)


# ---------------------------------------------------------------------------
# Session title editing over WS (issue #13)
# ---------------------------------------------------------------------------


class TestSetTitleOverWs:
    def test_admin_can_change_title_over_ws(self, add_session, test_client):
        sid = "TITLE01"
        add_session(sid, admin_token="secret")
        resp = test_client.get(f"/api/sessions/{sid}/ws-ticket", headers={"X-Admin-Token": "secret"})
        assert resp.status_code == 200
        ticket = resp.json()["ticket"]
        with test_client.websocket_connect(f"/ws/{sid}?role=admin&client_id=adm&ticket={ticket}") as ws:
            assert ws.receive_json()["type"] == "session_state"
            ws.send_json({"action": "set_title", "title": "Ny titel"})
            data = ws.receive_json()
            assert data["type"] == "session_state"
            assert data["title"] == "Ny titel"
        import app as app_module

        assert app_module.SESSIONS[sid]["title"] == "Ny titel"

    def test_participant_cannot_change_title(self, add_session, test_client):
        sid = "TITLE02"
        add_session(sid)
        with test_client.websocket_connect(f"/ws/{sid}?role=participant&client_id=p1") as ws:
            ws.receive_json()
            ws.send_json({"action": "set_title", "title": "Kapad titel"})
            msg = ws.receive_json()
            assert msg["type"] == "error"
        import app as app_module

        assert app_module.SESSIONS[sid]["title"] == "Test"
