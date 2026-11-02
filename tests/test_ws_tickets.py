"""Tests for WebSocket tickets (riskmatris.ws_tickets) and the ticket endpoint."""

from app import consume_ws_ticket, create_ws_ticket

# ---------------------------------------------------------------------------
# Admin WebSocket connection tickets
# ---------------------------------------------------------------------------


class TestWsTickets:
    def test_valid_ticket(self):
        ticket = create_ws_ticket("ABC123")
        assert consume_ws_ticket(ticket, "ABC123") is True

    def test_ticket_is_single_use(self):
        ticket = create_ws_ticket("ABC123")
        assert consume_ws_ticket(ticket, "ABC123") is True
        assert consume_ws_ticket(ticket, "ABC123") is False

    def test_ticket_for_wrong_session_is_burned(self):
        ticket = create_ws_ticket("ABC123")
        assert consume_ws_ticket(ticket, "OTHER1") is False
        # A failed attempt burns the ticket, so it cannot be replayed
        assert consume_ws_ticket(ticket, "ABC123") is False

    def test_expired_ticket_rejected(self):
        import time as time_module

        import app as app_module

        ticket = create_ws_ticket("ABC123")
        app_module.WS_TICKETS[ticket]["expires_at"] = time_module.time() - 1
        assert consume_ws_ticket(ticket, "ABC123") is False

    def test_unknown_ticket_rejected(self):
        assert consume_ws_ticket("does-not-exist", "ABC123") is False

    def test_no_ticket_is_not_admin(self):
        # An empty ticket must never authenticate as admin
        assert consume_ws_ticket("", "ABC123") is False


# ---------------------------------------------------------------------------
# Admin WebSocket ticket endpoint
# ---------------------------------------------------------------------------


class TestWsTicketEndpoint:
    def test_requires_valid_admin_token(self, add_session, test_client):
        from app import consume_ws_ticket

        sid = "TICKET1"
        add_session(sid, admin_token="secret-token")
        assert test_client.get(f"/api/sessions/{sid}/ws-ticket").status_code == 401
        assert test_client.get(f"/api/sessions/{sid}/ws-ticket", headers={"X-Admin-Token": "wrong"}).status_code == 401
        resp = test_client.get(f"/api/sessions/{sid}/ws-ticket", headers={"X-Admin-Token": "secret-token"})
        assert resp.status_code == 200
        ticket = resp.json()["ticket"]
        assert ticket
        assert consume_ws_ticket(ticket, sid) is True

    def test_unknown_session_returns_404(self, test_client):
        assert test_client.get("/api/sessions/NOPE00/ws-ticket").status_code == 404
