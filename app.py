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
from contextlib import asynccontextmanager
from functools import cache
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Loggning
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("riskmatris")

# ---------------------------------------------------------------------------
# Konfiguration & Konstanter
# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("RISKMATRIS_DB_PATH", os.path.join("data", "riskmatris.db"))
# Skapa data-katalogen om den inte finns (för lokal körning utan Docker)
os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
SESSION_TTL_SECONDS = int(os.environ.get("RISKMATRIS_TTL_HOURS", "48")) * 3600
SESSION_CLEANUP_INTERVAL = int(os.environ.get("RISKMATRIS_CLEANUP_INTERVAL", "3600"))  # 1 timme default

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


def round_half_up(value: float) -> int:
    """Avrundar enligt försiktighetsprincipen (.5 avrundas uppåt) till heltal 1..4."""
    rounded = int(math.floor(value + 0.5))
    return max(1, min(4, rounded))


def get_risk_level(score: int) -> dict[str, str]:
    """
    Riskvärde = Sannolikhet (1-4) x Konsekvens (1-4) -> 1..16
    Grön (1-2 Låg), Gul (3-6 Medel), Orange (8-9 Hög), Röd (12-16 Mycket Hög)
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
    """Hämtar datorns lokala nätverks-IP (cachad – beräknas bara en gång per process)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                logger.info("Lokal LAN-IP: %s", ip)
                return ip
    except Exception:
        pass
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        if ip and not ip.startswith("127."):
            logger.info("Lokal LAN-IP (via hostname %s): %s", hostname, ip)
            return ip
    except Exception:
        pass
    logger.info("Kunde inte hitta LAN-IP – använder 127.0.0.1")
    return "127.0.0.1"


# ---------------------------------------------------------------------------
# Databas & Sessionslagring (SQLite + RAM-cache)
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
        logger.info("Rensade %d utgångna sessioner: %s", len(expired_ids), expired_ids)


async def _periodic_cleanup() -> None:
    """Bakgrundsloop som rensar utgångna sessioner med jämna intervall."""
    while True:
        await asyncio.sleep(SESSION_CLEANUP_INTERVAL)
        try:
            cleanup_expired_sessions()
        except Exception:
            logger.exception("Fel vid periodisk städning av sessioner")


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
                logger.warning("Kunde inte ladda session %s från DB – hoppar över", sid)
                continue
    logger.info("Laddade %d sessioner från DB vid uppstart", len(loaded))
    return loaded


SESSIONS: dict[str, dict[str, Any]] = {}


def generate_session_id() -> str:
    """Genererar en lättläst 6-teckens kod (utan förväxlingsbara tecken som 0/O, 1/I)."""
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


def compute_risk_stats(risk: dict[str, Any], effective_threshold: int) -> dict[str, Any]:
    """Beräknar statistik för en risk utan sidoeffekter (ren funktion).

    Returnerar även ``threshold_reached`` så att anroparen kan uppdatera
    ``risk['revealed']`` explicit vid behov.
    """
    votes_list = list(risk["votes"].values())
    vote_count = len(votes_list)

    # Tröskeln är nådd om röster finns och antalet >= tröskeln (och risken inte redan är revealed)
    threshold_reached = (
        vote_count > 0
        and vote_count >= effective_threshold
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


# ---------------------------------------------------------------------------
# WebSocket Connection Manager
# ---------------------------------------------------------------------------


class ConnectionInfo:
    def __init__(self, websocket: WebSocket, role: str, client_id: str, is_admin: bool):
        self.websocket = websocket
        self.role = role  # "admin" eller "participant"
        self.client_id = client_id
        self.is_admin = is_admin


class SessionConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[str, list[ConnectionInfo]] = {}

    async def connect(self, session_id: str, conn: ConnectionInfo) -> None:
        await conn.websocket.accept()
        if session_id not in self.connections:
            self.connections[session_id] = []
        # Ta bort ev. tidigare anslutning med samma websocket
        self.connections[session_id] = [c for c in self.connections[session_id] if c.websocket != conn.websocket]
        self.connections[session_id].append(conn)

    def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        if session_id in self.connections:
            self.connections[session_id] = [c for c in self.connections[session_id] if c.websocket != websocket]
            if not self.connections[session_id]:
                del self.connections[session_id]

    def get_participant_count(self, session_id: str) -> int:
        """Antal unika anslutna deltagare (exklusive administratören)."""
        conns = self.connections.get(session_id, [])
        participant_ids: set[str] = {c.client_id for c in conns if c.role == "participant" and c.client_id}
        return len(participant_ids)

    def get_effective_threshold(self, session: dict[str, Any]) -> int:
        configured = max(1, int(session.get("threshold", 4)))
        participant_count = self.get_participant_count(session["session_id"])
        if participant_count > 0:
            return min(configured, participant_count)
        return configured

    def build_client_payload(self, session: dict[str, Any], conn: ConnectionInfo | None = None) -> dict[str, Any]:
        sid = session["session_id"]
        participant_count = self.get_participant_count(sid)
        effective_threshold = self.get_effective_threshold(session)

        # Beräkna statistik för alla risker (och uppdatera revealed vid tröskel)
        risks_summary: list[dict[str, Any]] = []
        active_num = session["active_risk_number"]
        state_changed = False

        for r in session["risks"]:
            r_stats = compute_risk_stats(r, effective_threshold)
            # Uppdatera revealed explicit baserat på threshold_reached (ingen sidoeffekt i compute_risk_stats)
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
            "effective_threshold": effective_threshold,
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
    logger.info("Startar Riskmatris Live – laddar sessioner från DB (%s)", DB_PATH)
    SESSIONS = load_sessions_from_db()
    logger.info("Servern är redo. %d aktiva sessioner.", len(SESSIONS))

    # Starta bakgrundsrensning av utgångna sessioner (varje timme)
    cleanup_task = asyncio.create_task(_periodic_cleanup())
    logger.info("Periodisk städning schemalagd (intervall: %d sekunder).", SESSION_CLEANUP_INTERVAL)

    yield

    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    logger.info("Stänger ner – sessioner sparade i DB.")


app = FastAPI(title="Riskmatris Live", lifespan=lifespan)


@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    """Sätter Cache-Control beroende på sökväg.

    Statiska filer (CSS/JS): 1 dag (innehållsbaserad versionering via ombyggnad).
    SPA-rutter (HTML): no-cache (måste alltid hämta senaste index.html).
    API-rutter: no-store (standard, känslig data).
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
    """Hälsokontroll för Docker HEALTHCHECK, Kubernetes och molnplattformar."""
    return {
        "status": "ok",
        "active_sessions": len(SESSIONS),
        "db_path": DB_PATH,
    }


@app.post("/api/sessions")
async def create_session(req: CreateSessionRequest):
    cleanup_expired_sessions()
    session_id = generate_session_id()
    admin_token = secrets.token_urlsafe(24)
    now = time.time()
    threshold = max(1, min(50, req.threshold or 4))
    title = (req.title or "Riskanalys").strip() or "Riskanalys"

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
    logger.info("Ny session skapad: %s – '%s' (tröskel: %d)", session_id, title, threshold)
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
    # Prioritera header över query-param (undviker token i URL/loggar/historik)
    token = x_admin_token or admin_token
    is_admin = bool(token and secrets.compare_digest(token, session["admin_token"]))
    dummy_conn = ConnectionInfo(
        websocket=None,  # type: ignore
        role="admin" if is_admin else "participant",
        client_id=client_id or "",
        is_admin=is_admin,
    )
    return manager.build_client_payload(session, dummy_conn)


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
        logger.exception("QR-SVG: kunde inte generera QR-kod för session %s", sid)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/sessions/{session_id}/export.csv")
async def export_session_csv(session_id: str):
    sid = session_id.strip().upper()
    session = SESSIONS.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail="Sessionen hittades inte.")

    effective_threshold = manager.get_effective_threshold(session)
    output = io.StringIO()
    # Skriv UTF-8 BOM så att Microsoft Excel i Windows visar å, ä, ö korrekt direkt vid dubbelklick
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
        stats = compute_risk_stats(r, effective_threshold)
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
# WebSocket-kommunikation i realtid
# ---------------------------------------------------------------------------


def _safe_int(msg: dict[str, Any], key: str, default: int, min_val: int = 0, max_val: int = 999) -> int | None:
    """Hämtar ett heltal från ett WS-meddelande med felhantering och gränskontroll."""
    raw = msg.get(key, default)
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return None
    if val < min_val or val > max_val:
        return None
    return val


async def _send_ws_error(websocket: WebSocket, message: str) -> None:
    """Skickar ett felmeddelande tillbaka till klienten över WebSocket."""
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
    admin_token: str = Query(default=""),
):
    sid = session_id.strip().upper()
    session = SESSIONS.get(sid)
    if not session:
        logger.warning("WebSocket: session %s hittades inte – nekad anslutning", sid)
        await websocket.close(code=4004, reason="Sessionen finns inte")
        return

    is_admin = bool(admin_token and secrets.compare_digest(admin_token, session["admin_token"]))
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
        "WebSocket: %s ansluten till session %s (roll: %s, klient: %s)",
        "admin" if is_admin else "deltagare",
        sid,
        effective_role,
        client_id,
    )
    await manager.broadcast(session)

    try:
        while True:
            # --- Mottagning & grundvalidering ---
            try:
                msg = await websocket.receive_json()
            except WebSocketDisconnect:
                # Klienten har kopplat från – låt den yttre except-handlern städa upp
                # och avsluta. Får INTE fångas av "except Exception" nedan: då kastar
                # receive_json direkt igen på varje varv och loopen snurrar för evigt
                # utan att släppa event-loopen, vilket låser hela servern.
                raise
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

            # 1. Deltagare (eller admin) röstar på aktiv risk
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
                eff_thresh = manager.get_effective_threshold(session)
                if len(active_risk["votes"]) >= eff_thresh:
                    active_risk["revealed"] = True
                save_session_to_db(session)
                logger.info(
                    "Röst mottagen: session %s, risk #%d, klient %s -> S=%d, K=%d (%d röster, tröskel %d)",
                    sid,
                    active_num,
                    client_id,
                    prob,
                    cons,
                    len(active_risk["votes"]),
                    eff_thresh,
                )
                await manager.broadcast(session)

            # Nedanstående åtgärder kräver admin-behörighet
            elif is_admin:
                if action == "reveal_now":
                    active_risk["revealed"] = True
                    save_session_to_db(session)
                    logger.info("Admin: resultat visat nu – session %s, risk #%d", sid, active_num)
                    await manager.broadcast(session)

                elif action == "set_label":
                    risk_num = _safe_int(msg, "number", active_num, min_val=1, max_val=9999)
                    if risk_num is None:
                        await _send_ws_error(websocket, "Ogiltigt risknummer.")
                        continue
                    label = str(msg.get("label", "")).strip()[:120]
                    for r in session["risks"]:
                        if r["number"] == risk_num:
                            r["label"] = label
                            break
                    save_session_to_db(session)
                    await manager.broadcast(session)

                elif action == "set_title":
                    title = str(msg.get("title", "")).strip()[:100]
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
                    eff_thresh = manager.get_effective_threshold(session)
                    if len(active_risk["votes"]) > 0 and len(active_risk["votes"]) >= eff_thresh:
                        active_risk["revealed"] = True
                    save_session_to_db(session)
                    await manager.broadcast(session)

                elif action == "lock_risk":
                    # Lås fast slutgiltig placering i sammanställningsmatrisen
                    eff_thresh = manager.get_effective_threshold(session)
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
                        "Admin: risk #%d låst i session %s -> S=%d, K=%d (riskvärde %d)",
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
                    # Administratören klickar i matrisen för att justera föreslagen/låst ruta
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
                    # Om nuvarande risk har röster och auto_lock skickas med, lås den på sitt förslag/val
                    if msg.get("auto_lock", True) and len(active_risk["votes"]) > 0 and not active_risk["locked"]:
                        eff_thresh = manager.get_effective_threshold(session)
                        stats = compute_risk_stats(active_risk, eff_thresh)
                        active_risk["final_probability"] = stats["effective_probability"]
                        active_risk["final_consequence"] = stats["effective_consequence"]
                        active_risk["revealed"] = True
                        active_risk["locked"] = True

                    max_num = max(r["number"] for r in session["risks"])
                    next_num = max_num + 1
                    next_label = str(msg.get("label", "")).strip()[:120]
                    new_r = create_new_risk(next_num, next_label)
                    session["risks"].append(new_r)
                    session["active_risk_number"] = next_num
                    save_session_to_db(session)
                    logger.info(
                        "Admin: ny risk #%d skapad i session %s (totalt %d risker)",
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
                # Icke-admin som försöker admin-action, eller okänd action
                if action != "vote":
                    await _send_ws_error(websocket, "Du saknar behörighet för denna åtgärd.")

    except WebSocketDisconnect:
        manager.disconnect(sid, websocket)
        logger.info("WebSocket: klient %s frånkopplad från session %s", client_id, sid)
        await manager.broadcast(session)
    except Exception:
        logger.exception("WebSocket: oväntat fel för klient %s i session %s", client_id, sid)
        manager.disconnect(sid, websocket)
        await manager.broadcast(session)


# ---------------------------------------------------------------------------
# Frontend-rutter (SPA / Direktlänkar för QR-kod & Sessioner)
# ---------------------------------------------------------------------------

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
@app.get("/s/{session_id}", response_class=HTMLResponse)
async def serve_spa(request: Request, session_id: str | None = None):
    with open(os.path.join("static", "index.html"), encoding="utf-8") as f:
        return HTMLResponse(content=f.read())
