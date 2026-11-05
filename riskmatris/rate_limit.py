"""In-memory rate limiters (single-process deployment).

Two sliding-window limiters, both keyed by client IP:

- session *creation* (strict – the expensive operation), and
- *read/probe* requests on endpoints keyed by the session code (session info,
  WS ticket, QR, CSV export, WS handshake). Without the latter, the 404
  responses for unknown codes make session codes enumerable by scripted
  requests.
"""

import time

import riskmatris.config as config

SESSION_CREATE_LOG: dict[str, list[float]] = {}
SESSION_READ_LOG: dict[str, list[float]] = {}
SESSION_CREATE_LIMIT = config.SESSION_CREATE_LIMIT
SESSION_CREATE_WINDOW_SECONDS = config.SESSION_CREATE_WINDOW_SECONDS
SESSION_READ_LIMIT = config.SESSION_READ_LIMIT
SESSION_READ_WINDOW_SECONDS = config.SESSION_READ_WINDOW_SECONDS


def check_rate(log: dict[str, list[float]], key: str, limit: int, window: float, now: float | None = None) -> bool:
    """Sliding-window limiter. Returns True if the key is still within the limit."""
    now = time.time() if now is None else now
    cutoff = now - window
    recent = [t for t in log.get(key, []) if t > cutoff]
    if len(recent) >= limit:
        log[key] = recent
        return False
    recent.append(now)
    log[key] = recent
    return True


def check_session_create_rate(client_ip: str, log: dict[str, list[float]] | None = None) -> bool:
    """Returns True if the client IP is still within the session-creation rate limit."""
    active_log = log if log is not None else SESSION_CREATE_LOG
    limit = getattr(config, "SESSION_CREATE_LIMIT", SESSION_CREATE_LIMIT)
    window = getattr(config, "SESSION_CREATE_WINDOW_SECONDS", SESSION_CREATE_WINDOW_SECONDS)
    return check_rate(active_log, client_ip, limit, window)


def check_session_read_rate(client_ip: str, log: dict[str, list[float]] | None = None) -> bool:
    """Returns True if the client IP is still within the read/probe rate limit."""
    active_log = log if log is not None else SESSION_READ_LOG
    limit = getattr(config, "SESSION_READ_LIMIT", SESSION_READ_LIMIT)
    window = getattr(config, "SESSION_READ_WINDOW_SECONDS", SESSION_READ_WINDOW_SECONDS)
    return check_rate(active_log, client_ip, limit, window)


def check_connection_message_rate(times: list[float], limit: int, window: float, now: float | None = None) -> bool:
    """Sliding-window message-rate limiter for a single WS connection.

    ``times`` is the connection's own list of recent message timestamps
    (monotonic clock); it is pruned and updated in place. Returns True if the
    connection is still within the limit.
    """
    now = time.monotonic() if now is None else now
    cutoff = now - window
    recent = [t for t in times if t > cutoff]
    if len(recent) >= limit:
        times[:] = recent
        return False
    recent.append(now)
    times[:] = recent
    return True


def _cleanup_log(log: dict[str, list[float]], window: float) -> None:
    """Drops entries that are entirely outside the current window."""
    cutoff = time.time() - window
    for key in list(log):
        if not any(t > cutoff for t in log[key]):
            log.pop(key, None)


def cleanup_rate_limit_log(log: dict[str, list[float]] | None = None) -> None:
    """Drops session-create rate-limit entries that are entirely outside the current window."""
    active_log = log if log is not None else SESSION_CREATE_LOG
    window = getattr(config, "SESSION_CREATE_WINDOW_SECONDS", SESSION_CREATE_WINDOW_SECONDS)
    _cleanup_log(active_log, window)


def cleanup_read_rate_limit_log(log: dict[str, list[float]] | None = None) -> None:
    """Drops read rate-limit entries that are entirely outside the current window."""
    active_log = log if log is not None else SESSION_READ_LOG
    window = getattr(config, "SESSION_READ_WINDOW_SECONDS", SESSION_READ_WINDOW_SECONDS)
    _cleanup_log(active_log, window)
