"""WebSocket connection manager."""

from typing import Any

from fastapi import WebSocket

from riskmatris.db import save_session_to_db, save_session_to_db_async
from riskmatris.session import compute_risk_stats, get_session_threshold
from riskmatris.utils import get_local_lan_ip, get_risk_level


def build_cell_meta() -> dict[str, dict[str, Any]]:
    """Static 4x4 map of cell key ("prob_cons") -> score/level/color.

    Sent in every session payload so the frontend never has to duplicate the
    server's risk-level thresholds (fas 7.2) – it only maps color -> CSS/hex.
    """
    return {f"{p}_{c}": {"score": p * c, **get_risk_level(p * c)} for p in range(1, 5) for c in range(1, 5)}


class ConnectionInfo:
    def __init__(
        self,
        websocket: WebSocket,
        role: str,
        client_id: str,
        is_admin: bool,
        client_ip: str = "",
    ):
        self.websocket = websocket
        self.role = role  # "admin" or "participant"
        self.client_id = client_id
        self.is_admin = is_admin
        self.client_ip = client_ip
        # Monotonic timestamps of recent messages, used for the per-connection
        # message rate limit (sakerhetsrapport A04-1)
        self.message_times: list[float] = []


class SessionConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[str, list[ConnectionInfo]] = {}

    async def connect(self, session_id: str, conn: ConnectionInfo) -> None:
        await conn.websocket.accept()
        if session_id not in self.connections:
            self.connections[session_id] = []
        # Remove any previous connection with the same websocket
        self.connections[session_id] = [c for c in self.connections[session_id] if c.websocket != conn.websocket]
        self.connections[session_id].append(conn)

    def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        if session_id in self.connections:
            self.connections[session_id] = [c for c in self.connections[session_id] if c.websocket != websocket]
            if not self.connections[session_id]:
                del self.connections[session_id]

    def get_connection_count(self, session_id: str) -> int:
        """Number of open WebSocket connections for the session."""
        return len(self.connections.get(session_id, []))

    def get_participant_count(self, session_id: str) -> int:
        """Number of unique connected participants (excluding the admin)."""
        conns = self.connections.get(session_id, [])
        participant_ids: set[str] = {c.client_id for c in conns if c.role == "participant" and c.client_id}
        return len(participant_ids)

    def total_connection_count(self) -> int:
        """Total open WebSocket connections across all sessions (global cap, A04-1)."""
        return sum(len(conns) for conns in self.connections.values())

    def count_connections_for_ip(self, client_ip: str) -> int:
        """Open WebSocket connections from one client IP, across all sessions (A04-1/T-1)."""
        if not client_ip:
            return 0
        return sum(1 for conns in self.connections.values() for c in conns if c.client_ip == client_ip)

    def _compute_base_payload(self, session: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], bool]:
        """Computes the part of the session_state payload shared by all connections
        (everything except my_vote/is_admin). Returns (base, active_risk, state_changed).

        Splitting this out lets broadcast() build the expensive part (risk stats,
        cell meta) once per broadcast instead of once per connection
        (sakerhetsrapport T-2).
        """
        sid = session["session_id"]
        participant_count = self.get_participant_count(sid)
        threshold = get_session_threshold(session)

        # Compute stats for all risks (and update revealed at threshold)
        risks_summary: list[dict[str, Any]] = []
        active_num = session["active_risk_number"]
        state_changed = False

        for r in session["risks"]:
            r_stats = compute_risk_stats(r, threshold)
            # Update revealed explicitly based on threshold_reached (no side effect in compute_risk_stats)
            if r_stats["threshold_reached"]:
                r["revealed"] = True
                state_changed = True
            risks_summary.append(r_stats)

        active_risk_raw = next(
            (r for r in session["risks"] if r["number"] == active_num),
            session["risks"][-1],
        )
        payload = {
            "type": "session_state",
            "session_id": sid,
            "title": session.get("title", "Riskanalys"),
            "threshold": session.get("threshold", 4),
            "participant_count": participant_count,
            "active_risk_number": active_num,
            "risks": risks_summary,
            "lan_ip": get_local_lan_ip(),
            # QR overlay in the presentation views, toggled from the admin view
            "qr_visible": bool(session.get("qr_visible", False)),
            # Static cell meta so the client never duplicates risk-level logic (fas 7.2)
            "cell_meta": build_cell_meta(),
        }
        return payload, active_risk_raw, state_changed

    def compute_client_payload(
        self, session: dict[str, Any], conn: ConnectionInfo | None = None
    ) -> tuple[dict[str, Any], bool]:
        """Builds the session_state payload. Returns (payload, state_changed)."""
        base, active_risk_raw, state_changed = self._compute_base_payload(session)
        my_vote = None
        if conn and conn.client_id:
            my_vote = active_risk_raw["votes"].get(conn.client_id)
        payload = dict(base)
        payload["my_vote"] = my_vote
        payload["is_admin"] = bool(conn and conn.is_admin)
        return payload, state_changed

    def build_client_payload(self, session: dict[str, Any], conn: ConnectionInfo | None = None) -> dict[str, Any]:
        """Sync variant (kept for tests/direct callers); persists via blocking sqlite."""
        payload, state_changed = self.compute_client_payload(session, conn)
        if state_changed:
            save_session_to_db(session)
        return payload

    async def build_client_payload_async(
        self, session: dict[str, Any], conn: ConnectionInfo | None = None
    ) -> dict[str, Any]:
        """Async variant (fas 7.3) – the sqlite write runs in a worker thread."""
        payload, state_changed = self.compute_client_payload(session, conn)
        if state_changed:
            await save_session_to_db_async(session)
        return payload

    async def broadcast(self, session: dict[str, Any]) -> None:
        """Sends the session state to all connections of the session.

        The shared payload (risk stats, cell meta, ...) is computed ONCE per
        broadcast and the DB is persisted at most once – previously both were
        done per connection, so N connections cost Nx the work (T-2). Only the
        per-connection fields (my_vote, is_admin) are set individually.
        """
        sid = session["session_id"]
        conns = list(self.connections.get(sid, []))
        if not conns:
            return
        base, active_risk_raw, state_changed = self._compute_base_payload(session)
        if state_changed:
            await save_session_to_db_async(session)
        dead_sockets: list[WebSocket] = []
        for conn in conns:
            payload = dict(base)
            payload["my_vote"] = active_risk_raw["votes"].get(conn.client_id) if conn.client_id else None
            payload["is_admin"] = conn.is_admin
            try:
                await conn.websocket.send_json(payload)
            except Exception:
                dead_sockets.append(conn.websocket)
        for ws in dead_sockets:
            self.disconnect(sid, ws)


# Singleton instance used across the application
manager = SessionConnectionManager()
