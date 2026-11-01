"""SQLite database operations and the in-memory sessions store."""

import json
import sqlite3
import sys
import time
from typing import Any

import riskmatris.config as config
from riskmatris.config import logger

# ---------------------------------------------------------------------------
# In-memory session cache (authoritative copy – persisted to SQLite)
# ---------------------------------------------------------------------------

SESSIONS: dict[str, dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Helpers to resolve DB_PATH dynamically
# ---------------------------------------------------------------------------


def _get_db_path() -> str:
    this_mod = sys.modules[__name__]
    return getattr(this_mod, "DB_PATH", getattr(config, "DB_PATH", "data/riskmatris.db"))


def _get_ttl_seconds() -> int:
    return getattr(config, "SESSION_TTL_SECONDS", getattr(config, "SESSION_TTL_HOURS", 48) * 3600)


# ---------------------------------------------------------------------------
# Schema & lifecycle
# ---------------------------------------------------------------------------


def init_db() -> None:
    with sqlite3.connect(_get_db_path()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                admin_token TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                data_json TEXT NOT NULL
            )
            """
        )
        conn.commit()


def cleanup_expired_sessions(sessions: dict[str, dict[str, Any]] | None = None) -> None:
    active_sessions = sessions if sessions is not None else SESSIONS
    cutoff = time.time() - _get_ttl_seconds()
    with sqlite3.connect(_get_db_path()) as conn:
        cursor = conn.execute("SELECT session_id FROM sessions WHERE updated_at < ?", (cutoff,))
        expired_ids = [row[0] for row in cursor.fetchall()]
        if expired_ids:
            conn.execute("DELETE FROM sessions WHERE updated_at < ?", (cutoff,))
            conn.commit()
    for sid in expired_ids:
        active_sessions.pop(sid, None)
    if expired_ids:
        logger.info("Removed %d expired sessions: %s", len(expired_ids), expired_ids)


def save_session_to_db(session: dict[str, Any]) -> None:
    session["updated_at"] = time.time()
    payload = json.dumps(session, ensure_ascii=False)
    with sqlite3.connect(_get_db_path()) as conn:
        conn.execute(
            """
            INSERT INTO sessions (session_id, admin_token, created_at, updated_at, data_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                updated_at = excluded.updated_at,
                data_json = excluded.data_json
            """,
            (
                session["session_id"],
                session["admin_token"],
                session["created_at"],
                session["updated_at"],
                payload,
            ),
        )
        conn.commit()


def load_sessions_from_db() -> dict[str, dict[str, Any]]:
    init_db()
    cleanup_expired_sessions()
    loaded: dict[str, dict[str, Any]] = {}
    with sqlite3.connect(_get_db_path()) as conn:
        cursor = conn.execute("SELECT session_id, data_json FROM sessions")
        for sid, data_json in cursor.fetchall():
            try:
                loaded[sid] = json.loads(data_json)
            except Exception:
                logger.warning("Could not load session %s from DB – skipping", sid)
                continue
    logger.info("Loaded %d sessions from DB at startup", len(loaded))
    return loaded
