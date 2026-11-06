"""One-time, short-lived tokens for handing admin rights to another device.

Flow: the current admin creates a handover token (shown as a QR code pointing at
``/s/{sid}?handover={token}``). The new device opens that URL, which POSTs the token
to ``/api/sessions/{sid}/consume-handover`` and receives the session's admin token
in the response body (never in a URL, so it stays out of proxy/access logs).
"""

import secrets
import time
from typing import Any

from riskmatris.config import ADMIN_HANDOVER_TTL_SECONDS

HANDOVER_TOKENS: dict[str, dict[str, Any]] = {}


def create_handover_token(session_id: str, tokens: dict[str, dict[str, Any]] | None = None) -> str:
    """Issues a single-use handover token for the given session."""
    active = tokens if tokens is not None else HANDOVER_TOKENS
    token = secrets.token_urlsafe(24)
    active[token] = {"session_id": session_id, "expires_at": time.time() + ADMIN_HANDOVER_TTL_SECONDS}
    return token


def consume_handover_token(token: str, session_id: str, tokens: dict[str, dict[str, Any]] | None = None) -> bool:
    """Burns a handover token and returns True if it was valid for the session.

    A failed attempt burns the token, so it cannot be replayed or brute-forced.
    """
    active = tokens if tokens is not None else HANDOVER_TOKENS
    data = active.pop(token, None)
    return bool(data and data["session_id"] == session_id and data["expires_at"] >= time.time())


def cleanup_expired_handover_tokens(tokens: dict[str, dict[str, Any]] | None = None) -> None:
    active = tokens if tokens is not None else HANDOVER_TOKENS
    now = time.time()
    for token in [t for t, d in active.items() if d["expires_at"] < now]:
        active.pop(token, None)
