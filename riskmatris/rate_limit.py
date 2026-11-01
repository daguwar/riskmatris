"""In-memory rate limiter for public session creation (single-process deployment)."""

import time

import riskmatris.config as config

SESSION_CREATE_LOG: dict[str, list[float]] = {}
SESSION_CREATE_LIMIT = config.SESSION_CREATE_LIMIT
SESSION_CREATE_WINDOW_SECONDS = config.SESSION_CREATE_WINDOW_SECONDS


def check_session_create_rate(client_ip: str, log: dict[str, list[float]] | None = None) -> bool:
    """Returns True if the client IP is still within the session-creation rate limit."""
    now = time.time()
    active_log = log if log is not None else SESSION_CREATE_LOG
    limit = getattr(config, "SESSION_CREATE_LIMIT", SESSION_CREATE_LIMIT)
    window = getattr(config, "SESSION_CREATE_WINDOW_SECONDS", SESSION_CREATE_WINDOW_SECONDS)
    cutoff = now - window
    recent = [t for t in active_log.get(client_ip, []) if t > cutoff]
    if len(recent) >= limit:
        active_log[client_ip] = recent
        return False
    recent.append(now)
    active_log[client_ip] = recent
    return True


def cleanup_rate_limit_log(log: dict[str, list[float]] | None = None) -> None:
    """Drops rate-limit entries that are entirely outside the current window."""
    active_log = log if log is not None else SESSION_CREATE_LOG
    window = getattr(config, "SESSION_CREATE_WINDOW_SECONDS", SESSION_CREATE_WINDOW_SECONDS)
    cutoff = time.time() - window
    for ip in list(active_log):
        if not any(t > cutoff for t in active_log[ip]):
            active_log.pop(ip, None)
