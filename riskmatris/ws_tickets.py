"""One-time, short-lived tickets for admin WebSocket authentication.

Tickets let an admin authenticate the WebSocket without putting the long-lived
admin token in the URL (query strings end up in proxy/access logs and browser
history).
"""

import secrets
import time
from typing import Any

from riskmatris.config import WS_TICKET_TTL_SECONDS

WS_TICKETS: dict[str, dict[str, Any]] = {}


def create_ws_ticket(session_id: str, tickets: dict[str, dict[str, Any]] | None = None) -> str:
    """Issues a single-use connection ticket for the given session."""
    active_tickets = tickets if tickets is not None else WS_TICKETS
    ticket = secrets.token_urlsafe(24)
    active_tickets[ticket] = {"session_id": session_id, "expires_at": time.time() + WS_TICKET_TTL_SECONDS}
    return ticket


def consume_ws_ticket(ticket: str, session_id: str, tickets: dict[str, dict[str, Any]] | None = None) -> bool:
    """Burns a connection ticket and returns True if it was valid for the session."""
    active_tickets = tickets if tickets is not None else WS_TICKETS
    data = active_tickets.pop(ticket, None)
    return bool(data and data["session_id"] == session_id and data["expires_at"] >= time.time())


def cleanup_expired_ws_tickets(tickets: dict[str, dict[str, Any]] | None = None) -> None:
    """Drops connection tickets that are past their TTL without having been used."""
    active_tickets = tickets if tickets is not None else WS_TICKETS
    now = time.time()
    for ticket in [t for t, d in active_tickets.items() if d["expires_at"] < now]:
        active_tickets.pop(ticket, None)
