"""Backward-compatible entry point.

All application code lives in the ``riskmatris`` package (see
``riskmatris/__init__.py``). This module re-exports the public API so that
the test suite (``import app ...``) and older tooling keep working.
New code should import from ``riskmatris.*`` directly.
"""

import sys
import types

import riskmatris.config as _config
import riskmatris.db as _db
import riskmatris.handover as _handover
import riskmatris.models as _models
import riskmatris.rate_limit as _rate_limit
import riskmatris.session as _session
import riskmatris.snapshot as _snapshot
import riskmatris.state as _state
import riskmatris.utils as _utils
import riskmatris.ws_manager as _ws_manager
import riskmatris.ws_tickets as _ws_tickets
from riskmatris import app  # noqa: F401
from riskmatris.config import (  # noqa: F401
    CONSEQUENCE_LABELS,
    DB_PATH,
    ENABLE_DOCS,
    MAX_CLIENT_ID_LENGTH,
    MAX_LABEL_LENGTH,
    MAX_QR_URL_LENGTH,
    MAX_TITLE_LENGTH,
    PROBABILITY_LABELS,
    SESSION_CLEANUP_INTERVAL,
    SESSION_CODE_LENGTH,
    SESSION_CREATE_LIMIT,
    SESSION_CREATE_WINDOW_SECONDS,
    SESSION_READ_LIMIT,
    SESSION_READ_WINDOW_SECONDS,
    SESSION_TTL_HOURS,
    SESSION_TTL_SECONDS,
    SQLITE_BUSY_TIMEOUT_MS,
    WS_MAX_CONNECTIONS_PER_IP,
    WS_MAX_CONNECTIONS_PER_SESSION,
    WS_MAX_CONNECTIONS_TOTAL,
    WS_MAX_MESSAGE_BYTES,
    WS_MESSAGE_RATE_LIMIT,
    WS_MESSAGE_RATE_WINDOW_SECONDS,
    WS_TICKET_TTL_SECONDS,
    _parse_env_bool,
    _parse_env_int,
    logger,
)
from riskmatris.db import (  # noqa: F401
    SESSIONS,
    cleanup_expired_sessions,
    init_db,
    load_sessions_from_db,
    save_session_to_db,
)
from riskmatris.handover import (  # noqa: F401
    HANDOVER_TOKENS,
    cleanup_expired_handover_tokens,
    consume_handover_token,
    create_handover_token,
)
from riskmatris.models import CreateSessionRequest  # noqa: F401
from riskmatris.rate_limit import (  # noqa: F401
    SESSION_CREATE_LOG,
    SESSION_READ_LOG,
    check_connection_message_rate,
    check_session_create_rate,
    check_session_read_rate,
    cleanup_rate_limit_log,
    cleanup_read_rate_limit_log,
)
from riskmatris.routes.spa import get_static_version  # noqa: F401
from riskmatris.routes.ws import websocket_endpoint  # noqa: F401
from riskmatris.session import (  # noqa: F401
    compute_risk_stats,
    create_new_risk,
    generate_session_id,
    get_session_threshold,
)
from riskmatris.snapshot import SnapshotFile, build_snapshot, risks_from_snapshot  # noqa: F401
from riskmatris.state import AppState, default_state, get_app_state  # noqa: F401
from riskmatris.utils import (  # noqa: F401
    _safe_int,
    get_local_lan_ip,
    get_risk_level,
    round_half_up,
    sanitize_csv_cell,
    sanitize_user_text,
)
from riskmatris.ws_manager import (  # noqa: F401
    ConnectionInfo,
    SessionConnectionManager,
    manager,
)
from riskmatris.ws_tickets import (  # noqa: F401
    WS_TICKETS,
    cleanup_expired_ws_tickets,
    consume_ws_ticket,
    create_ws_ticket,
)


class _AppModule(types.ModuleType):
    """Dynamic module proxy to synchronize monkeypatched attributes during tests."""

    def __getattr__(self, name: str):
        if hasattr(_rate_limit, name):
            return getattr(_rate_limit, name)
        if hasattr(_db, name):
            return getattr(_db, name)
        if hasattr(_config, name):
            return getattr(_config, name)
        if hasattr(_state, name):
            return getattr(_state, name)
        if hasattr(_session, name):
            return getattr(_session, name)
        if hasattr(_snapshot, name):
            return getattr(_snapshot, name)
        if hasattr(_utils, name):
            return getattr(_utils, name)
        if hasattr(_ws_manager, name):
            return getattr(_ws_manager, name)
        if hasattr(_ws_tickets, name):
            return getattr(_ws_tickets, name)
        if hasattr(_handover, name):
            return getattr(_handover, name)
        if hasattr(_models, name):
            return getattr(_models, name)
        raise AttributeError(f"module 'app' has no attribute '{name}'")

    def __setattr__(self, name: str, value):
        super().__setattr__(name, value)
        if name in (
            "SESSION_CREATE_LOG",
            "SESSION_CREATE_LIMIT",
            "SESSION_CREATE_WINDOW_SECONDS",
            "SESSION_READ_LOG",
            "SESSION_READ_LIMIT",
            "SESSION_READ_WINDOW_SECONDS",
        ):
            setattr(_rate_limit, name, value)
            if hasattr(_state.default_state, name):
                setattr(_state.default_state, name, value)
        if name in (
            "SESSION_CREATE_LIMIT",
            "SESSION_CREATE_WINDOW_SECONDS",
            "SESSION_READ_LIMIT",
            "SESSION_READ_WINDOW_SECONDS",
            "SESSION_CODE_LENGTH",
            "WS_MAX_CONNECTIONS_PER_IP",
            "WS_MAX_CONNECTIONS_TOTAL",
            "WS_MESSAGE_RATE_LIMIT",
            "WS_MESSAGE_RATE_WINDOW_SECONDS",
            "ENABLE_DOCS",
            "SQLITE_BUSY_TIMEOUT_MS",
            "DB_PATH",
            "SESSION_TTL_HOURS",
            "SESSION_TTL_SECONDS",
            "MAX_SNAPSHOT_BYTES",
        ):
            setattr(_config, name, value)
        if name in ("SESSIONS", "DB_PATH"):
            setattr(_db, name, value)
            if name == "SESSIONS":
                _state.default_state.sessions = value
        if name in ("WS_TICKETS",):
            setattr(_ws_tickets, name, value)
            _state.default_state.ws_tickets = value


sys.modules[__name__].__class__ = _AppModule
