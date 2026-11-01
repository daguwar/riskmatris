"""In-memory rate limiter for public session creation (single-process deployment)."""

import time

import riskmatris.config as config

SESSION_CREATE_LOG: dict[str, list[float]] = {}
SESSION_CREATE_LIMIT = config.SESSION_CREATE_LIMIT
SESSION_CREATE_WINDOW_SECONDS = config.SESSION_CREATE_WINDOW_SECONDS


def check_session_create_rate(client_ip: str) -> bool:
    """Returns True if the client IP is still within the session-creation rate limit."""
    now = time.time()
    limit = getattr(config, "SESSION_CREATE_LIMIT", SESSION_CREATE_LIMIT)
    window = getattr(config, "SESSION_CREATE_WINDOW_SECONDS", SESSION_CREATE_WINDOW_SECONDS)
    cutoff = now - window
    recent = [t for t in SESSION_CREATE_LOG.get(client_ip, []) if t > cutoff]
    if len(recent) >= limit:
        SESSION_CREATE_LOG[client_ip] = recent
        return False
    recent.append(now)
    SESSION_CREATE_LOG[client_ip] = recent
    return True


def cleanup_rate_limit_log() -> None:
    """Drops rate-limit entries that are entirely outside the current window."""
    window = getattr(config, "SESSION_CREATE_WINDOW_SECONDS", SESSION_CREATE_WINDOW_SECONDS)
    cutoff = time.time() - window
    for ip in list(SESSION_CREATE_LOG):
        if not any(t > cutoff for t in SESSION_CREATE_LOG[ip]):
            SESSION_CREATE_LOG.pop(ip, None)
