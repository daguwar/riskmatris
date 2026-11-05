"""Application state encapsulation and dependency injection."""

from __future__ import annotations

from typing import Any

from fastapi import Request, WebSocket

import riskmatris.db as db
import riskmatris.rate_limit as rate_limit
import riskmatris.ws_manager as ws_manager
import riskmatris.ws_tickets as ws_tickets_mod
from riskmatris.ws_manager import SessionConnectionManager


class AppState:
    """Encapsulates all mutable application state.

    Allows clean dependency injection, test isolation, and avoids module-level globals.
    """

    def __init__(
        self,
        sessions: dict[str, dict[str, Any]] | None = None,
        session_create_log: dict[str, list[float]] | None = None,
        session_read_log: dict[str, list[float]] | None = None,
        ws_tickets: dict[str, dict[str, Any]] | None = None,
        manager: SessionConnectionManager | None = None,
    ) -> None:
        self._sessions = sessions
        self._session_create_log = session_create_log
        self._session_read_log = session_read_log
        self._ws_tickets = ws_tickets
        self._manager = manager

    @property
    def sessions(self) -> dict[str, dict[str, Any]]:
        if self._sessions is not None:
            return self._sessions
        return db.SESSIONS

    @sessions.setter
    def sessions(self, val: dict[str, dict[str, Any]]) -> None:
        self._sessions = val

    @property
    def session_create_log(self) -> dict[str, list[float]]:
        if self._session_create_log is not None:
            return self._session_create_log
        return rate_limit.SESSION_CREATE_LOG

    @session_create_log.setter
    def session_create_log(self, val: dict[str, list[float]]) -> None:
        self._session_create_log = val

    @property
    def session_read_log(self) -> dict[str, list[float]]:
        if self._session_read_log is not None:
            return self._session_read_log
        return rate_limit.SESSION_READ_LOG

    @session_read_log.setter
    def session_read_log(self, val: dict[str, list[float]]) -> None:
        self._session_read_log = val

    @property
    def ws_tickets(self) -> dict[str, dict[str, Any]]:
        if self._ws_tickets is not None:
            return self._ws_tickets
        return ws_tickets_mod.WS_TICKETS

    @ws_tickets.setter
    def ws_tickets(self, val: dict[str, dict[str, Any]]) -> None:
        self._ws_tickets = val

    @property
    def manager(self) -> SessionConnectionManager:
        if self._manager is not None:
            return self._manager
        return ws_manager.manager

    @manager.setter
    def manager(self, val: SessionConnectionManager) -> None:
        self._manager = val

    # --- Domain actions on state ---

    def check_session_create_rate(self, client_ip: str) -> bool:
        return rate_limit.check_session_create_rate(client_ip, self.session_create_log)

    def check_session_read_rate(self, client_ip: str) -> bool:
        return rate_limit.check_session_read_rate(client_ip, self.session_read_log)

    def cleanup_rate_limit_log(self) -> None:
        rate_limit.cleanup_rate_limit_log(self.session_create_log)
        rate_limit.cleanup_read_rate_limit_log(self.session_read_log)

    def create_ws_ticket(self, session_id: str) -> str:
        return ws_tickets_mod.create_ws_ticket(session_id, self.ws_tickets)

    def consume_ws_ticket(self, ticket: str, session_id: str) -> bool:
        return ws_tickets_mod.consume_ws_ticket(ticket, session_id, self.ws_tickets)

    def cleanup_expired_ws_tickets(self) -> None:
        ws_tickets_mod.cleanup_expired_ws_tickets(self.ws_tickets)

    def cleanup_expired_sessions(self) -> None:
        db.cleanup_expired_sessions(self.sessions)

    async def cleanup_expired_sessions_async(self) -> None:
        """Async variant – the sqlite work runs in a worker thread."""
        await db.cleanup_expired_sessions_async(self.sessions)


default_state = AppState()


def get_app_state(request: Request) -> AppState:
    """Dependency that extracts AppState from the HTTP request, or returns default_state."""
    try:
        app = getattr(request, "app", None)
        if app and hasattr(app, "state") and hasattr(app.state, "app_state"):
            candidate = app.state.app_state
            if isinstance(candidate, AppState):
                return candidate
    except Exception:
        pass
    return default_state


def get_ws_app_state(websocket: WebSocket) -> AppState:
    """Dependency that extracts AppState from the WebSocket, or returns default_state."""
    try:
        app = getattr(websocket, "app", None)
        if app and hasattr(app, "state") and hasattr(app.state, "app_state"):
            candidate = app.state.app_state
            if isinstance(candidate, AppState):
                return candidate
    except Exception:
        pass
    return default_state
