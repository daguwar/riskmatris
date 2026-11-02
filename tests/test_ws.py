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
