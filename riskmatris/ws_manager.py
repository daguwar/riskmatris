"""WebSocket connection manager."""

from typing import Any

from fastapi import WebSocket

from riskmatris.db import save_session_to_db
from riskmatris.session import compute_risk_stats, get_session_threshold
from riskmatris.utils import get_local_lan_ip


class ConnectionInfo:
    def __init__(self, websocket: WebSocket, role: str, client_id: str, is_admin: bool):
        self.websocket = websocket
        self.role = role  # "admin" or "participant"
        self.client_id = client_id
        self.is_admin = is_admin


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

    def build_client_payload(self, session: dict[str, Any], conn: ConnectionInfo | None = None) -> dict[str, Any]:
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

        if state_changed:
            save_session_to_db(session)

        active_risk_raw = next(
            (r for r in session["risks"] if r["number"] == active_num),
            session["risks"][-1],
        )
        my_vote = None
        if conn and conn.client_id:
            my_vote = active_risk_raw["votes"].get(conn.client_id)

        return {
            "type": "session_state",
            "session_id": sid,
            "title": session.get("title", "Riskanalys"),
            "threshold": session.get("threshold", 4),
            "participant_count": participant_count,
            "active_risk_number": active_num,
            "risks": risks_summary,
            "my_vote": my_vote,
            "is_admin": bool(conn and conn.is_admin),
            "lan_ip": get_local_lan_ip(),
        }

    async def broadcast(self, session: dict[str, Any]) -> None:
        sid = session["session_id"]
        conns = list(self.connections.get(sid, []))
        dead_sockets: list[WebSocket] = []
        for conn in conns:
            try:
                payload = self.build_client_payload(session, conn)
                await conn.websocket.send_json(payload)
            except Exception:
                dead_sockets.append(conn.websocket)
        for ws in dead_sockets:
            self.disconnect(sid, ws)


# Singleton instance used across the application
manager = SessionConnectionManager()
