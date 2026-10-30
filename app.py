import asyncio
import csv
import io
import json
import logging
import math
import os
import secrets
import socket
import sqlite3
import time
import unicodedata
from contextlib import asynccontextmanager
from functools import cache
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("riskmatris")

# ---------------------------------------------------------------------------
# Configuration & Constants
# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("RISKMATRIS_DB_PATH", os.path.join("data", "riskmatris.db"))
# Create the data directory if it does not exist (for local runs without Docker)
os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
SESSION_TTL_SECONDS = int(os.environ.get("RISKMATRIS_TTL_HOURS", "48")) * 3600
SESSION_CLEANUP_INTERVAL = int(os.environ.get("RISKMATRIS_CLEANUP_INTERVAL", "3600"))  # 1 hour default

# Abuse/availability limits (single-process, in-memory – fits the deployment model)
SESSION_CREATE_LIMIT = int(os.environ.get("RISKMATRIS_SESSION_CREATE_LIMIT", "10"))  # per IP per window
SESSION_CREATE_WINDOW_SECONDS = 3600
WS_MAX_CONNECTIONS_PER_SESSION = int(os.environ.get("RISKMATRIS_WS_MAX_CONNECTIONS", "200"))
WS_MAX_MESSAGE_BYTES = int(os.environ.get("RISKMATRIS_WS_MAX_MESSAGE_BYTES", "8192"))
WS_TICKET_TTL_SECONDS = 30  # one-time admin WebSocket tickets
MAX_TITLE_LENGTH = 100
MAX_LABEL_LENGTH = 120

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


def sanitize_user_text(value: str, max_length: int) -> str:
    """Strips control/format characters (e.g. newlines, RTL overrides) from
    user-supplied text and clamps its length. Keeps titles and labels safe to
    store, render and log."""
    return "".join(ch for ch in value if unicodedata.category(ch) not in ("Cc", "Cf")).strip()[:max_length]


# In-memory rate limiter for public session creation (single-process deployment)
SESSION_CREATE_LOG: dict[str, list[float]] = {}


def check_session_create_rate(client_ip: str) -> bool:
    """Returns True if the client IP is still within the session-creation rate limit."""
    now = time.time()
    cutoff = now - SESSION_CREATE_WINDOW_SECONDS
    recent = [t for t in SESSION_CREATE_LOG.get(client_ip, []) if t > cutoff]
    if len(recent) >= SESSION_CREATE_LIMIT:
        SESSION_CREATE_LOG[client_ip] = recent
        return False
    recent.append(now)
    SESSION_CREATE_LOG[client_ip] = recent
    return True


def cleanup_rate_limit_log() -> None:
    """Drops rate-limit entries that are entirely outside the current window."""
    cutoff = time.time() - SESSION_CREATE_WINDOW_SECONDS
    for ip in list(SESSION_CREATE_LOG):
        if not any(t > cutoff for t in SESSION_CREATE_LOG[ip]):
            SESSION_CREATE_LOG.pop(ip, None)


def round_half_up(value: float) -> int:
    """Rounds half up (cautious rounding: .5 rounds up) to an integer in 1..4."""
    rounded = int(math.floor(value + 0.5))
    return max(1, min(4, rounded))


def get_risk_level(score: int) -> dict[str, str]:
    """
    Risk score = Probability (1-4) x Consequence (1-4) -> 1..16
    Green (1-2 Low), Yellow (3-6 Medium), Orange (8-9 High), Red (12-16 Very High)
    """
    if score <= 2:
        return {"level": "Låg", "color": "green"}
    elif score <= 6:
        return {"level": "Medel", "color": "yellow"}
    elif score <= 9:
        return {"level": "Hög", "color": "orange"}
    else:
        return {"level": "Mycket Hög", "color": "red"}


@cache
def get_local_lan_ip() -> str:
    """Returns the machine's local network IP (cached – computed only once per process)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                logger.info("Local LAN IP: %s", ip)
                return ip
    except Exception:
        pass
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        if ip and not ip.startswith("127."):
            logger.info("Local LAN IP (via hostname %s): %s", hostname, ip)
            return ip
    except Exception:
        pass
    logger.info("Could not determine LAN IP – falling back to 127.0.0.1")
    return "127.0.0.1"


# ---------------------------------------------------------------------------
# Database & Session Storage (SQLite + RAM cache)
# ---------------------------------------------------------------------------


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
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


def cleanup_expired_sessions() -> None:
    cutoff = time.time() - SESSION_TTL_SECONDS
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("SELECT session_id FROM sessions WHERE updated_at < ?", (cutoff,))
        expired_ids = [row[0] for row in cursor.fetchall()]
        if expired_ids:
            conn.execute("DELETE FROM sessions WHERE updated_at < ?", (cutoff,))
            conn.commit()
    for sid in expired_ids:
        SESSIONS.pop(sid, None)
    if expired_ids:
        logger.info("Removed %d expired sessions: %s", len(expired_ids), expired_ids)


async def _periodic_cleanup() -> None:
    """Background loop that removes expired sessions at regular intervals."""
    while True:
        await asyncio.sleep(SESSION_CLEANUP_INTERVAL)
        try:
            cleanup_expired_sessions()
            cleanup_expired_ws_tickets()
            cleanup_rate_limit_log()
        except Exception:
            logger.exception("Error during periodic session cleanup")


def save_session_to_db(session: dict[str, Any]) -> None:
    session["updated_at"] = time.time()
    payload = json.dumps(session, ensure_ascii=False)
    with sqlite3.connect(DB_PATH) as conn:
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
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("SELECT session_id, data_json FROM sessions")
        for sid, data_json in cursor.fetchall():
            try:
                loaded[sid] = json.loads(data_json)
            except Exception:
                logger.warning("Could not load session %s from DB – skipping", sid)
                continue
    logger.info("Loaded %d sessions from DB at startup", len(loaded))
    return loaded


SESSIONS: dict[str, dict[str, Any]] = {}


def generate_session_id() -> str:
    """Generates a readable 6-character code (without confusable characters like 0/O, 1/I)."""
    alphabet = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(6))
        if code not in SESSIONS:
            return code


def create_new_risk(number: int, label: str = "") -> dict[str, Any]:
    return {
        "number": number,
        "label": label.strip(),
        "votes": {},  # client_id -> {"probability": int, "consequence": int, "updated_at": float}
        "revealed": False,
        "locked": False,
        "final_probability": None,
        "final_consequence": None,
    }


def get_session_threshold(session: dict[str, Any]) -> int:
    """Returns the session's configured vote threshold.

    The threshold is the exact number of votes needed to auto-reveal a risk's
    result. It is deliberately never adjusted to the number of currently
    connected participants: the system cannot know how many participants are
    expected, only the meeting leader can. Revealing early would leak partial
    results to the room before everyone has voted.
    """
    return max(1, int(session.get("threshold", 4)))


def compute_risk_stats(risk: dict[str, Any], threshold: int) -> dict[str, Any]:
    """Computes statistics for a risk without side effects (pure function).

    Also returns ``threshold_reached`` so the caller can update
    ``risk['revealed']`` explicitly when needed.
    """
    votes_list = list(risk["votes"].values())
    vote_count = len(votes_list)

    # Threshold is reached if votes exist and the count >= threshold (and the risk is not already revealed)
    threshold_reached = (
        vote_count > 0
        and vote_count >= threshold
        and not risk["revealed"]
    )

    is_revealed = bool(risk["revealed"] or risk["locked"])

    avg_prob: float | None = None
    avg_cons: float | None = None
    suggested_prob: int | None = None
    suggested_cons: int | None = None
    cell_counts: dict[str, int] = {}

    if vote_count > 0:
        avg_prob = round(sum(v["probability"] for v in votes_list) / vote_count, 2)
        avg_cons = round(sum(v["consequence"] for v in votes_list) / vote_count, 2)
        suggested_prob = round_half_up(avg_prob)
        suggested_cons = round_half_up(avg_cons)

        for v in votes_list:
            key = f"{v['probability']}_{v['consequence']}"
            cell_counts[key] = cell_counts.get(key, 0) + 1

    final_prob = risk["final_probability"] or suggested_prob
    final_cons = risk["final_consequence"] or suggested_cons
    final_score = (final_prob * final_cons) if (final_prob and final_cons) else None
    risk_meta = get_risk_level(final_score) if final_score else None

    return {
        "number": risk["number"],
        "label": risk["label"],
        "vote_count": vote_count,
        "revealed": is_revealed,
        "locked": risk["locked"],
        "threshold_reached": threshold_reached,
        "avg_probability": avg_prob if is_revealed else None,
        "avg_consequence": avg_cons if is_revealed else None,
        "suggested_probability": suggested_prob if is_revealed else None,
        "suggested_consequence": suggested_cons if is_revealed else None,
        "final_probability": risk["final_probability"] if is_revealed else None,
        "final_consequence": risk["final_consequence"] if is_revealed else None,
        "effective_probability": final_prob if is_revealed else None,
        "effective_consequence": final_cons if is_revealed else None,
        "score": final_score if is_revealed else None,
        "level": risk_meta["level"] if (is_revealed and risk_meta) else None,
        "color": risk_meta["color"] if (is_revealed and risk_meta) else None,
        "cell_counts": cell_counts if is_revealed else {},
    }


# One-time, short-lived tickets that let an admin authenticate the WebSocket
# without putting the long-lived admin token in the URL (query strings end up
# in proxy/access logs and browser history).
WS_TICKETS: dict[str, dict[str, Any]] = {}


def create_ws_ticket(session_id: str) -> str:
    """Issues a single-use connection ticket for the given session."""
    ticket = secrets.token_urlsafe(24)
    WS_TICKETS[ticket] = {"session_id": session_id, "expires_at": time.time() + WS_TICKET_TTL_SECONDS}
    return ticket


def consume_ws_ticket(ticket: str, session_id: str) -> bool:
    """Burns a connection ticket and returns True if it was valid for the session."""
    data = WS_TICKETS.pop(ticket, None)
    return bool(data and data["session_id"] == session_id and data["expires_at"] >= time.time())


def cleanup_expired_ws_tickets() -> None:
    """Drops connection tickets that are past their TTL without having been used."""
    now = time.time()
    for ticket in [t for t, d in WS_TICKETS.items() if d["expires_at"] < now]:
        WS_TICKETS.pop(ticket, None)


# ---------------------------------------------------------------------------
# WebSocket Connection Manager
# ---------------------------------------------------------------------------


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


manager = SessionConnectionManager()


# ---------------------------------------------------------------------------
# FastAPI Lifespan & App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    global SESSIONS
    logger.info("Starting Riskmatris Live – loading sessions from DB (%s)", DB_PATH)
    SESSIONS = load_sessions_from_db()
    logger.info("Server ready. %d active sessions.", len(SESSIONS))

    # Start background cleanup of expired sessions (hourly)
    cleanup_task = asyncio.create_task(_periodic_cleanup())
    logger.info("Periodic cleanup scheduled (interval: %d seconds).", SESSION_CLEANUP_INTERVAL)

    yield

    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    logger.info("Shutting down – sessions saved to DB.")


app = FastAPI(title="Riskmatris Live", lifespan=lifespan)


@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    """Sets Cache-Control depending on the request path.

    Static files (CSS/JS): 1 day (content-based versioning via rebuild).
    SPA routes (HTML): no-cache (index.html must always be fetched fresh).
    API routes: no-store (default, sensitive data).
    """
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=86400"
    elif path == "/" or path.startswith("/s/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


class CreateSessionRequest(BaseModel):
    title: str | None = "Riskanalys"
    threshold: int | None = 4


@app.get("/health")
async def health_check():
    """Health check for Docker HEALTHCHECK, Kubernetes and cloud platforms."""
    return {
        "status": "ok",
        "active_sessions": len(SESSIONS),
        "db_path": DB_PATH,
    }


@app.post("/api/sessions")
async def create_session(req: CreateSessionRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if not check_session_create_rate(client_ip):
        logger.warning("Session creation rate limit hit for client %s", client_ip)
        raise HTTPException(status_code=429, detail="För många sessioner skapade. Försök igen om en stund.")
    cleanup_expired_sessions()
    session_id = generate_session_id()
    admin_token = secrets.token_urlsafe(24)
    now = time.time()
    threshold = max(1, min(50, req.threshold or 4))
    title = sanitize_user_text(req.title or "", MAX_TITLE_LENGTH) or "Riskanalys"

    session = {
        "session_id": session_id,
        "admin_token": admin_token,
        "title": title,
        "threshold": threshold,
        "created_at": now,
        "updated_at": now,
        "active_risk_number": 1,
        "risks": [create_new_risk(1, "")],
    }
    SESSIONS[session_id] = session
    save_session_to_db(session)
    logger.info("New session created: %s – '%s' (threshold: %d)", session_id, title, threshold)
    return {
        "session_id": session_id,
        "admin_token": admin_token,
        "title": title,
        "threshold": threshold,
        "lan_ip": get_local_lan_ip(),
    }


@app.get("/api/sessions/{session_id}")
async def get_session_info(
    session_id: str,
    request: Request,
    admin_token: str | None = Query(default=None),
    client_id: str | None = Query(default=None),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    sid = session_id.strip().upper()
    session = SESSIONS.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail="Sessionen hittades inte.")
    # Prefer the header over the query param (avoids token in URLs/logs/history)
    token = x_admin_token or admin_token
    is_admin = bool(token and secrets.compare_digest(token, session["admin_token"]))
    dummy_conn = ConnectionInfo(
        websocket=None,  # type: ignore
        role="admin" if is_admin else "participant",
        client_id=client_id or "",
        is_admin=is_admin,
    )
    return manager.build_client_payload(session, dummy_conn)


@app.get("/api/sessions/{session_id}/ws-ticket")
async def get_ws_ticket(session_id: str, x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")):
    """Issues a one-time, short-lived ticket for admin WebSocket authentication.

    This keeps the long-lived admin token out of the WebSocket query string.
    """
    sid = session_id.strip().upper()
    session = SESSIONS.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail="Sessionen hittades inte.")
    if not x_admin_token or not secrets.compare_digest(x_admin_token, session["admin_token"]):
        raise HTTPException(status_code=401, detail="Ogiltig administratörs-token.")
    return {"ticket": create_ws_ticket(sid), "expires_in": WS_TICKET_TTL_SECONDS}


@app.get("/api/sessions/{session_id}/qr.svg")
async def get_session_qr_svg(session_id: str, url: str = Query(...)):
    sid = session_id.strip().upper()
    if sid not in SESSIONS:
        raise HTTPException(status_code=404, detail="Sessionen hittades inte.")
    try:
        import qrcode
        import qrcode.image.svg

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
        buf = io.BytesIO()
        img.save(buf)
        svg_bytes = buf.getvalue()
        return Response(content=svg_bytes, media_type="image/svg+xml")
    except Exception as exc:
        logger.exception("QR-SVG: could not generate QR code for session %s", sid)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/sessions/{session_id}/export.csv")
async def export_session_csv(session_id: str):
    sid = session_id.strip().upper()
    session = SESSIONS.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail="Sessionen hittades inte.")

    threshold = get_session_threshold(session)
    output = io.StringIO()
    # Write a UTF-8 BOM so Microsoft Excel on Windows renders å, ä, ö correctly when opening the file directly
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";")

    writer.writerow(
        [
            "Risk #",
            "Beskrivning / Etikett",
            "Status",
            "Antal röster",
            "Medel Sannolikhet",
            "Medel Konsekvens",
            "Sannolikhet (1-4)",
            "Sannolikhet (Text)",
            "Konsekvens (1-4)",
            "Konsekvens (Text)",
            "Riskvärde (1-16)",
            "Risknivå",
            "Röstfördelning (Sannolikhet x Konsekvens: Antal)",
        ]
    )

    for r in session["risks"]:
        stats = compute_risk_stats(r, threshold)
        prob = stats["effective_probability"]
        cons = stats["effective_consequence"]
        score = stats["score"]
        level = stats["level"] or ""
        status_str = "Låst i sammanställning" if r["locked"] else ("Öppen / Visad" if stats["revealed"] else "Ej visad")

        dist_parts = []
        for cell_key, count in sorted(stats["cell_counts"].items()):
            sp, sc = cell_key.split("_")
            dist_parts.append(f"S{sp}xK{sc}: {count} st")

        writer.writerow(
            [
                f"#{r['number']}",
                r["label"],
                status_str,
                stats["vote_count"],
                str(stats["avg_probability"]).replace(".", ",") if stats["avg_probability"] is not None else "",
                str(stats["avg_consequence"]).replace(".", ",") if stats["avg_consequence"] is not None else "",
                prob or "",
                PROBABILITY_LABELS.get(prob, "") if prob else "",
                cons or "",
                CONSEQUENCE_LABELS.get(cons, "") if cons else "",
                score or "",
                level,
                ", ".join(dist_parts),
            ]
        )

    csv_bytes = output.getvalue().encode("utf-8")
    filename = f"riskmatris_{sid}.csv"
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Real-time WebSocket Communication
# ---------------------------------------------------------------------------


def _safe_int(msg: dict[str, Any], key: str, default: int, min_val: int = 0, max_val: int = 999) -> int | None:
    """Fetches an integer from a WS message with error handling and bounds checking."""
    raw = msg.get(key, default)
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return None
    if val < min_val or val > max_val:
        return None
    return val


async def _send_ws_error(websocket: WebSocket, message: str) -> None:
    """Sends an error message back to the client over WebSocket."""
    try:
        await websocket.send_json({"type": "error", "message": message})
    except Exception:
        pass


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    role: str = Query(default="participant"),
    client_id: str = Query(default=""),
    ticket: str = Query(default=""),
):
    sid = session_id.strip().upper()
    session = SESSIONS.get(sid)
    if not session:
        logger.warning("WebSocket: session %s not found – connection denied", sid)
        await websocket.close(code=4004, reason="Sessionen finns inte")
        return

    if manager.get_connection_count(sid) >= WS_MAX_CONNECTIONS_PER_SESSION:
        logger.warning(
            "WebSocket: session %s connection limit reached (%d) – rejecting client %s",
            sid,
            WS_MAX_CONNECTIONS_PER_SESSION,
            client_id,
        )
        await websocket.close(code=1013, reason="Sessionsgränsen för anslutningar är nådd")
        return

    # Admins authenticate with a one-time ticket instead of the long-lived
    # admin token, so no secret ever travels in the query string.
    is_admin = consume_ws_ticket(ticket, sid) if ticket else False
    effective_role = "admin" if (role == "admin" and is_admin) else "participant"
    if not client_id:
        client_id = f"anon_{secrets.token_hex(6)}"

    conn = ConnectionInfo(
        websocket=websocket,
        role=effective_role,
        client_id=client_id,
        is_admin=is_admin,
    )
    await manager.connect(sid, conn)
    logger.info(
        "WebSocket: %s connected to session %s (role: %s, client: %s)",
        "admin" if is_admin else "participant",
        sid,
        effective_role,
        client_id,
    )
    await manager.broadcast(session)

    try:
        while True:
            # --- Receive & basic validation ---
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                # The client has disconnected – let the outer exception handler clean
                # up and return. Must NOT be caught by the "except Exception" below:
                # receive_text would re-raise on every iteration, spinning the loop
                # forever without yielding to the event loop, deadlocking the server.
                raise
            except Exception:
                await _send_ws_error(websocket, "Ogiltigt meddelande.")
                continue
            if len(raw.encode("utf-8")) > WS_MAX_MESSAGE_BYTES:
                await _send_ws_error(websocket, "Meddelandet är för stort.")
                continue
            try:
                msg = json.loads(raw)
            except Exception:
                await _send_ws_error(websocket, "Ogiltigt JSON-meddelande.")
                continue

            if not isinstance(msg, dict):
                await _send_ws_error(websocket, "Meddelandet måste vara ett JSON-objekt.")
                continue

            action = msg.get("action")
            if not isinstance(action, str):
                await _send_ws_error(websocket, "Saknar giltig 'action'.")
                continue

            active_num = session["active_risk_number"]
            active_risk = next(
                (r for r in session["risks"] if r["number"] == active_num),
                session["risks"][-1],
            )

            # 1. Participant (or admin) votes on the active risk
            if action == "vote":
                prob = _safe_int(msg, "probability", 0, min_val=1, max_val=4)
                cons = _safe_int(msg, "consequence", 0, min_val=1, max_val=4)
                if prob is None or cons is None:
                    await _send_ws_error(websocket, "Sannolikhet och Konsekvens måste vara heltal 1–4.")
                    continue
                if active_risk["locked"]:
                    await _send_ws_error(websocket, "Denna risk är låst – röstning ej möjlig.")
                    continue
                active_risk["votes"][client_id] = {
                    "probability": prob,
                    "consequence": cons,
                    "updated_at": time.time(),
                }
                eff_thresh = get_session_threshold(session)
                if len(active_risk["votes"]) >= eff_thresh:
                    active_risk["revealed"] = True
                save_session_to_db(session)
                logger.info(
                    "Vote received: session %s, risk #%d, client %s -> P=%d, C=%d (%d votes, threshold %d)",
                    sid,
                    active_num,
                    client_id,
                    prob,
                    cons,
                    len(active_risk["votes"]),
                    eff_thresh,
                )
                await manager.broadcast(session)

            # The actions below require admin privileges
            elif is_admin:
                if action == "reveal_now":
                    active_risk["revealed"] = True
                    save_session_to_db(session)
                    logger.info("Admin: results revealed – session %s, risk #%d", sid, active_num)
                    await manager.broadcast(session)

                elif action == "set_label":
                    risk_num = _safe_int(msg, "number", active_num, min_val=1, max_val=9999)
                    if risk_num is None:
                        await _send_ws_error(websocket, "Ogiltigt risknummer.")
                        continue
                    label = sanitize_user_text(str(msg.get("label", "")), MAX_LABEL_LENGTH)
                    for r in session["risks"]:
                        if r["number"] == risk_num:
                            r["label"] = label
                            break
                    save_session_to_db(session)
                    await manager.broadcast(session)

                elif action == "set_title":
                    title = sanitize_user_text(str(msg.get("title", "")), MAX_TITLE_LENGTH)
                    if title:
                        session["title"] = title
                        save_session_to_db(session)
                        await manager.broadcast(session)
                    else:
                        await _send_ws_error(websocket, "Titel får inte vara tom.")

                elif action == "set_threshold":
                    new_t = _safe_int(msg, "threshold", 4, min_val=1, max_val=50)
                    if new_t is None:
                        await _send_ws_error(websocket, "Tröskelvärdet måste vara ett heltal 1–50.")
                        continue
                    session["threshold"] = new_t
                    eff_thresh = get_session_threshold(session)
                    if len(active_risk["votes"]) > 0 and len(active_risk["votes"]) >= eff_thresh:
                        active_risk["revealed"] = True
                    save_session_to_db(session)
                    await manager.broadcast(session)

                elif action == "lock_risk":
                    # Lock the final placement in the summary matrix
                    eff_thresh = get_session_threshold(session)
                    stats = compute_risk_stats(active_risk, eff_thresh)
                    prob_raw = msg.get("probability")
                    cons_raw = msg.get("consequence")
                    prob = (
                        _safe_int(msg, "probability", 0, min_val=1, max_val=4)
                        if prob_raw is not None
                        else (stats["effective_probability"] or 2)
                    )
                    cons = (
                        _safe_int(msg, "consequence", 0, min_val=1, max_val=4)
                        if cons_raw is not None
                        else (stats["effective_consequence"] or 2)
                    )
                    if prob is None or cons is None:
                        await _send_ws_error(websocket, "Sannolikhet och Konsekvens måste vara heltal 1–4.")
                        continue
                    active_risk["final_probability"] = prob
                    active_risk["final_consequence"] = cons
                    active_risk["revealed"] = True
                    active_risk["locked"] = True
                    save_session_to_db(session)
                    logger.info(
                        "Admin: risk #%d locked in session %s -> P=%d, C=%d (risk score %d)",
                        active_num,
                        sid,
                        prob,
                        cons,
                        prob * cons,
                    )
                    await manager.broadcast(session)

                elif action == "unlock_risk":
                    active_risk["locked"] = False
                    save_session_to_db(session)
                    await manager.broadcast(session)

                elif action == "set_final_cell":
                    # Admin clicks a cell in the matrix to adjust the suggested/locked placement
                    prob = _safe_int(msg, "probability", 0, min_val=1, max_val=4)
                    cons = _safe_int(msg, "consequence", 0, min_val=1, max_val=4)
                    if prob is None or cons is None:
                        await _send_ws_error(websocket, "Sannolikhet och Konsekvens måste vara heltal 1–4.")
                        continue
                    active_risk["final_probability"] = prob
                    active_risk["final_consequence"] = cons
                    active_risk["revealed"] = True
                    if msg.get("lock", False):
                        active_risk["locked"] = True
                    save_session_to_db(session)
                    await manager.broadcast(session)

                elif action == "next_risk":
                    # If the current risk has votes and auto_lock is sent, lock it at its suggestion/selection
                    if msg.get("auto_lock", True) and len(active_risk["votes"]) > 0 and not active_risk["locked"]:
                        eff_thresh = get_session_threshold(session)
                        stats = compute_risk_stats(active_risk, eff_thresh)
                        active_risk["final_probability"] = stats["effective_probability"]
                        active_risk["final_consequence"] = stats["effective_consequence"]
                        active_risk["revealed"] = True
                        active_risk["locked"] = True

                    max_num = max(r["number"] for r in session["risks"])
                    next_num = max_num + 1
                    next_label = sanitize_user_text(str(msg.get("label", "")), MAX_LABEL_LENGTH)
                    new_r = create_new_risk(next_num, next_label)
                    session["risks"].append(new_r)
                    session["active_risk_number"] = next_num
                    save_session_to_db(session)
                    logger.info(
                        "Admin: new risk #%d created in session %s (%d risks total)",
                        next_num,
                        sid,
                        len(session["risks"]),
                    )
                    await manager.broadcast(session)

                elif action == "select_risk":
                    target_num = _safe_int(msg, "number", 1, min_val=1, max_val=9999)
                    if target_num is None:
                        await _send_ws_error(websocket, "Ogiltigt risknummer.")
                        continue
                    if any(r["number"] == target_num for r in session["risks"]):
                        session["active_risk_number"] = target_num
                        save_session_to_db(session)
                        await manager.broadcast(session)
                    else:
                        await _send_ws_error(websocket, f"Risk #{target_num} finns inte.")

                elif action == "reset_votes":
                    active_risk["votes"] = {}
                    active_risk["revealed"] = False
                    active_risk["locked"] = False
                    active_risk["final_probability"] = None
                    active_risk["final_consequence"] = None
                    save_session_to_db(session)
                    await manager.broadcast(session)

                elif action == "delete_risk":
                    target_num = _safe_int(msg, "number", active_num, min_val=1, max_val=9999)
                    if target_num is None:
                        await _send_ws_error(websocket, "Ogiltigt risknummer.")
                        continue
                    if len(session["risks"]) > 1:
                        session["risks"] = [r for r in session["risks"] if r["number"] != target_num]
                        if session["active_risk_number"] == target_num:
                            session["active_risk_number"] = session["risks"][-1]["number"]
                        save_session_to_db(session)
                        await manager.broadcast(session)
                    else:
                        await _send_ws_error(websocket, "Kan inte ta bort den enda risken.")

                else:
                    await _send_ws_error(websocket, f"Okänd admin-action: {action}")

            else:
                # Non-admin attempting an admin action, or an unknown action
                if action != "vote":
                    await _send_ws_error(websocket, "Du saknar behörighet för denna åtgärd.")

    except WebSocketDisconnect:
        manager.disconnect(sid, websocket)
        logger.info("WebSocket: client %s disconnected from session %s", client_id, sid)
        await manager.broadcast(session)
    except Exception:
        logger.exception("WebSocket: unexpected error for client %s in session %s", client_id, sid)
        manager.disconnect(sid, websocket)
        await manager.broadcast(session)


# ---------------------------------------------------------------------------
# Frontend Routes (SPA / Direct Links for QR Codes & Sessions)
# ---------------------------------------------------------------------------

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
@app.get("/s/{session_id}", response_class=HTMLResponse)
async def serve_spa(request: Request, session_id: str | None = None):
    with open(os.path.join("static", "index.html"), encoding="utf-8") as f:
        return HTMLResponse(content=f.read())
