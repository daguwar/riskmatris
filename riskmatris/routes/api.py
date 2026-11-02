"""REST API endpoints: sessions, QR codes, CSV export, health check."""

import csv
import io
import secrets
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

import riskmatris.config as config
import riskmatris.db as db
from riskmatris.config import (
    CONSEQUENCE_LABELS,
    MAX_CLIENT_ID_LENGTH,
    MAX_QR_URL_LENGTH,
    MAX_TITLE_LENGTH,
    PROBABILITY_LABELS,
    logger,
)
from riskmatris.models import CreateSessionRequest, CreateSessionResponse, HealthResponse, WsTicketResponse
from riskmatris.session import (
    compute_risk_stats,
    create_new_risk,
    generate_session_id,
    get_session_threshold,
)
from riskmatris.state import AppState, get_app_state
from riskmatris.utils import get_local_lan_ip, sanitize_user_text
from riskmatris.ws_manager import ConnectionInfo

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check(state: AppState = Depends(get_app_state)):
    """Health check for Docker HEALTHCHECK, Kubernetes and cloud platforms."""
    return {
        "status": "ok",
        "active_sessions": len(state.sessions),
        "db_path": getattr(config, "DB_PATH", "data/riskmatris.db"),
    }


@router.post("/api/sessions", response_model=CreateSessionResponse)
async def create_session(
    req: CreateSessionRequest,
    request: Request,
    state: AppState = Depends(get_app_state),
):
    client_ip = request.client.host if request.client else "unknown"
    if not state.check_session_create_rate(client_ip):
        logger.warning("Session creation rate limit hit for client %s", client_ip)
        raise HTTPException(status_code=429, detail="För många sessioner skapade. Försök igen om en stund.")
    await state.cleanup_expired_sessions_async()
    session_id = generate_session_id(state.sessions)
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
    state.sessions[session_id] = session
    await db.save_session_to_db_async(session)
    logger.info("New session created: %s – '%s' (threshold: %d)", session_id, title, threshold)
    return {
        "session_id": session_id,
        "admin_token": admin_token,
        "title": title,
        "threshold": threshold,
        "lan_ip": get_local_lan_ip(),
    }


@router.get("/api/sessions/{session_id}")
async def get_session_info(
    session_id: str,
    request: Request,
    admin_token: str | None = Query(default=None),
    client_id: str | None = Query(default=None),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    state: AppState = Depends(get_app_state),
):
    sid = session_id.strip().upper()
    session = state.sessions.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail="Sessionen hittades inte.")
    # Prefer the header over the query param (avoids token in URLs/logs/history)
    token = x_admin_token or admin_token
    is_admin = bool(token and secrets.compare_digest(token, session["admin_token"]))
    # Clamp/sanitize the client id – it is unbounded query input otherwise
    client_id = sanitize_user_text(client_id or "", MAX_CLIENT_ID_LENGTH)
    dummy_conn = ConnectionInfo(
        websocket=None,  # type: ignore
        role="admin" if is_admin else "participant",
        client_id=client_id or "",
        is_admin=is_admin,
    )
    return await state.manager.build_client_payload_async(session, dummy_conn)


@router.get("/api/sessions/{session_id}/ws-ticket", response_model=WsTicketResponse)
async def get_ws_ticket(
    session_id: str,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    state: AppState = Depends(get_app_state),
):
    """Issues a one-time, short-lived ticket for admin WebSocket authentication.

    This keeps the long-lived admin token out of the WebSocket query string.
    """
    sid = session_id.strip().upper()
    session = state.sessions.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail="Sessionen hittades inte.")
    if not x_admin_token or not secrets.compare_digest(x_admin_token, session["admin_token"]):
        raise HTTPException(status_code=401, detail="Ogiltig administratörs-token.")
    return {"ticket": state.create_ws_ticket(sid), "expires_in": config.WS_TICKET_TTL_SECONDS}


@router.get("/api/sessions/{session_id}/qr.svg")
async def get_session_qr_svg(
    session_id: str,
    url: str = Query(...),
    state: AppState = Depends(get_app_state),
):
    sid = session_id.strip().upper()
    if sid not in state.sessions:
        raise HTTPException(status_code=404, detail="Sessionen hittades inte.")
    # Cap the URL: a huge value would produce an enormous QR code (CPU/memory)
    # in a fully public endpoint
    if len(url) > MAX_QR_URL_LENGTH:
        raise HTTPException(status_code=400, detail="URL:en är för lång.")
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


@router.get("/api/sessions/{session_id}/export.csv")
async def export_session_csv(
    session_id: str,
    state: AppState = Depends(get_app_state),
):
    sid = session_id.strip().upper()
    session = state.sessions.get(sid)
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
