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


def create_ws_ticket(session_id: str) -> str:
    """Issues a single-use connection ticket for the given session."""
    ticket = secrets.token_urlsafe(24)
    WS_TICKETS[ticket] = {"session_id": session_id, "expires_at": time.time() + WS_TICKET_TTL_SECONDS}
    return ticket


def consume_ws_ticket(ticket: str, session_id: str) -> bool:
    """Burns a connection ticket and returns True if it was valid for the session."""
    data = WS_TICKETS.pop(ticket, None)
    return bool(data and data["session_id"] == session_id and data["expires_at"] >= time.time())


def cleanup_expired_ws_tickets() -> None:
    """Drops connection tickets that are past their TTL without having been used."""
    now = time.time()
    for ticket in [t for t, d in WS_TICKETS.items() if d["expires_at"] < now]:
        WS_TICKETS.pop(ticket, None)
