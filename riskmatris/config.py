"""Configuration, constants and environment variable parsing."""

import logging
import os

from riskmatris.log_formatter import JsonFormatter, build_log_formatter

# JsonFormatter is re-exported for backwards compatibility (tests import it
# from this module).
__all__ = ["JsonFormatter"]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

# All loggers (including uvicorn's own, see log_config.json) use the same
# formatter: JSON lines when RISKMATRIS_LOG_FORMAT=json (default in the Docker
# image), otherwise a timestamped human-readable format.
_handler = logging.StreamHandler()
_handler.setFormatter(build_log_formatter())
logging.basicConfig(level=logging.INFO, handlers=[_handler])
logger = logging.getLogger("riskmatris")

# Validate LOG_LEVEL after basicConfig so the fallback warning is visible in the
# log format; an invalid value would otherwise crash the app at import time.
_raw_log_level = os.environ.get("LOG_LEVEL", "INFO")
_log_level = getattr(logging, _raw_log_level.upper(), None)
if isinstance(_log_level, int) and _log_level > 0:
    logging.getLogger().setLevel(_log_level)
else:
    logger.warning("Invalid LOG_LEVEL value %r – falling back to INFO", _raw_log_level)

# ---------------------------------------------------------------------------
# Environment variable parsing
# ---------------------------------------------------------------------------


def _parse_env_int(name: str, default: int, min_value: int, max_value: int | None = None) -> int:
    """Parses an integer environment variable with a safe fallback.

    Invalid or out-of-range values log a warning and fall back to the default.
    Bare int() would crash at startup on non-numeric values, and a silent zero
    or negative limit could disable a safety mechanism (rate limiting, message
    size caps) or wedge the app in a busy loop (cleanup interval).
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        value = None
    if value is None or value < min_value or (max_value is not None and value > max_value):
        logger.warning("Invalid %s value %r – falling back to %d", name, raw, default)
        return default
    return value


def _parse_env_bool(name: str, default: bool) -> bool:
    """Parses a boolean environment variable with a safe fallback.

    Accepts 1/true/yes/on as True and 0/false/no/off as False (case-insensitive);
    anything else logs a warning and falls back to the default.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    logger.warning("Invalid %s value %r – falling back to %s", name, raw, default)
    return default


# ---------------------------------------------------------------------------
# Feature toggles
# ---------------------------------------------------------------------------

# Interactive API docs (/docs, /redoc, /openapi.json). Disabled by default –
# secure by default: in production they are a recon aid (sakerhetsrapport
# A05-1). Set RISKMATRIS_ENABLE_DOCS=1 for local debugging (the local
# docker-compose.yml does this).
ENABLE_DOCS = _parse_env_bool("RISKMATRIS_ENABLE_DOCS", False)

# ---------------------------------------------------------------------------
# Database path
# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("RISKMATRIS_DB_PATH", os.path.join("data", "riskmatris.db"))
# Create the data directory if it does not exist (for local runs without Docker)
os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)

# SQLite: how long a connection waits for a lock before failing with
# "database is locked" (sakerhetsrapport T-4). Writes run in a thread pool, so
# without this, concurrent writes fail immediately under load.
SQLITE_BUSY_TIMEOUT_MS = _parse_env_int("RISKMATRIS_SQLITE_BUSY_TIMEOUT_MS", 5000, min_value=0, max_value=60_000)

# ---------------------------------------------------------------------------
# Session & WebSocket constants
# ---------------------------------------------------------------------------

SESSION_TTL_HOURS = _parse_env_int("RISKMATRIS_TTL_HOURS", 48, min_value=1)
SESSION_TTL_SECONDS = SESSION_TTL_HOURS * 3600
SESSION_CLEANUP_INTERVAL = _parse_env_int("RISKMATRIS_CLEANUP_INTERVAL", 3600, min_value=60)

# Abuse/availability limits (single-process, in-memory – fits the deployment model)
SESSION_CREATE_LIMIT = _parse_env_int("RISKMATRIS_SESSION_CREATE_LIMIT", 10, min_value=1)  # per IP per window
SESSION_CREATE_WINDOW_SECONDS = 3600
# Per-IP limit on the public read endpoints (session info, WS ticket, QR, CSV
# export, WS handshake). These are keyed by the session code and answer 404 for
# unknown codes – without a limit the codes could be enumerated by scripted
# requests (sakerhetsrapport A01-3). Generous enough for a whole meeting behind
# one shared NAT, infeasible for enumeration of the code space.
SESSION_READ_LIMIT = _parse_env_int("RISKMATRIS_SESSION_READ_LIMIT", 300, min_value=1)  # per IP per window
SESSION_READ_WINDOW_SECONDS = _parse_env_int("RISKMATRIS_SESSION_READ_WINDOW_SECONDS", 60, min_value=1)
# Length of generated session codes. 8 chars from a 32-char alphabet = 40 bits
# (6 chars = only 30 bits). Still fits the manual join field and the QR code.
SESSION_CODE_LENGTH = _parse_env_int("RISKMATRIS_SESSION_CODE_LENGTH", 8, min_value=6, max_value=16)
WS_MAX_CONNECTIONS_PER_SESSION = _parse_env_int("RISKMATRIS_WS_MAX_CONNECTIONS", 200, min_value=2)
# Per-IP and global connection caps (sakerhetsrapport A04-1/T-1): without them
# one IP could occupy all per-session slots with throwaway connections.
WS_MAX_CONNECTIONS_PER_IP = _parse_env_int("RISKMATRIS_WS_MAX_CONNECTIONS_PER_IP", 20, min_value=1)
WS_MAX_CONNECTIONS_TOTAL = _parse_env_int("RISKMATRIS_WS_MAX_CONNECTIONS_TOTAL", 1000, min_value=10)
# Per-connection message rate limit (A04-1): each vote triggers a DB write +
# a broadcast, so an unthrottled connection is an amplification vector.
WS_MESSAGE_RATE_LIMIT = _parse_env_int("RISKMATRIS_WS_MESSAGE_RATE_LIMIT", 120, min_value=1)  # per connection per window
WS_MESSAGE_RATE_WINDOW_SECONDS = _parse_env_int("RISKMATRIS_WS_MESSAGE_RATE_WINDOW_SECONDS", 60, min_value=1)
WS_MAX_MESSAGE_BYTES = _parse_env_int("RISKMATRIS_WS_MAX_MESSAGE_BYTES", 8192, min_value=256, max_value=1_048_576)
WS_TICKET_TTL_SECONDS = 30  # one-time admin WebSocket tickets
MAX_TITLE_LENGTH = 100
MAX_LABEL_LENGTH = 120
MAX_CLIENT_ID_LENGTH = 64
MAX_QR_URL_LENGTH = 1000

# ---------------------------------------------------------------------------
# Risk labels (Swedish)
# ---------------------------------------------------------------------------

PROBABILITY_LABELS = {
    1: "Osannolik",
    2: "Möjlig",
    3: "Sannolik",
    4: "Mycket sannolik",
}

CONSEQUENCE_LABELS = {
    1: "Försumbar",
    2: "Måttlig",
    3: "Allvarlig",
    4: "Mycket allvarlig",
}
