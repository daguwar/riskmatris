"""REST API endpoints: sessions, QR codes, CSV export, snapshots, health check."""

import csv
import io
import json
import secrets
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import ValidationError

import riskmatris.config as config
import riskmatris.db as db
from riskmatris.config import (
    MAX_CLIENT_ID_LENGTH,
    MAX_QR_URL_LENGTH,
    MAX_TITLE_LENGTH,
    logger,
)
from riskmatris.i18n import SUPPORTED_LANGS, csv_texts, level_key_for_score
from riskmatris.models import (
    ConsumeHandoverRequest,
    CreateSessionRequest,
    CreateSessionResponse,
    HandoverConsumeResponse,
    HealthResponse,
    WsTicketResponse,
)
from riskmatris.session import (
    compute_risk_stats,
    create_new_risk,
    generate_session_id,
    get_session_threshold,
)
from riskmatris.snapshot import SnapshotFile, build_snapshot, risks_from_snapshot
from riskmatris.state import AppState, get_app_state
from riskmatris.utils import get_local_lan_ip, sanitize_csv_cell, sanitize_user_text
from riskmatris.ws_manager import ConnectionInfo

router = APIRouter()


def _enforce_read_rate_limit(request: Request, state: AppState) -> None:
    """Per-IP rate limit on the public read endpoints.

    Session info, WS ticket, QR and CSV export are all keyed by the session
    code and answer 404 for unknown codes – without a limit, a scripted client
    could enumerate active session codes. The limit is generous enough for a
    whole meeting behind one shared NAT.
    """
    client_ip = request.client.host if request.client else "unknown"
    if not state.check_session_read_rate(client_ip):
        logger.warning("Read rate limit hit for client %s on %s", client_ip, request.url.path)
        raise HTTPException(status_code=429, detail="too_many_requests")


@router.get("/health", response_model=HealthResponse)
async def health_check(state: AppState = Depends(get_app_state)):
    """Health check for Docker HEALTHCHECK, Kubernetes and cloud platforms."""
    return {
        "status": "ok",
        "active_sessions": len(state.sessions),
        # Fixed relative path on purpose: the configured absolute DB path would
        # leak the server layout.
        "db_path": "data/riskmatris.db",
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
        raise HTTPException(status_code=429, detail="too_many_sessions")
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
    client_id: str | None = Query(default=None),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    state: AppState = Depends(get_app_state),
):
    _enforce_read_rate_limit(request, state)
    sid = session_id.strip().upper()
    session = state.sessions.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail="session_not_found")
    # Only the X-Admin-Token header is accepted – a token in the query string
    # would leak into proxy logs, browser history and the Referer header
    token = x_admin_token
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
    request: Request,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    state: AppState = Depends(get_app_state),
):
    """Issues a one-time, short-lived ticket for admin WebSocket authentication.

    This keeps the long-lived admin token out of the WebSocket query string.
    """
    _enforce_read_rate_limit(request, state)
    sid = session_id.strip().upper()
    session = state.sessions.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail="session_not_found")
    if not x_admin_token or not secrets.compare_digest(x_admin_token, session["admin_token"]):
        raise HTTPException(status_code=401, detail="invalid_admin_token")
    return {"ticket": state.create_ws_ticket(sid), "expires_in": config.WS_TICKET_TTL_SECONDS}


@router.post("/api/sessions/{session_id}/admin-handover", response_model=WsTicketResponse)
async def create_admin_handover(
    session_id: str,
    request: Request,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    state: AppState = Depends(get_app_state),
):
    """Issues a one-time, short-lived token for handing admin rights to another
    device (shown as a QR code pointing at ``/s/{sid}?handover={token}``)."""
    _enforce_read_rate_limit(request, state)
    sid = session_id.strip().upper()
    session = state.sessions.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail="session_not_found")
    if not x_admin_token or not secrets.compare_digest(x_admin_token, session["admin_token"]):
        raise HTTPException(status_code=401, detail="invalid_admin_token")
    return {"ticket": state.create_handover_token(sid), "expires_in": config.ADMIN_HANDOVER_TTL_SECONDS}


@router.post("/api/sessions/{session_id}/consume-handover", response_model=HandoverConsumeResponse)
async def consume_handover(
    session_id: str,
    req: ConsumeHandoverRequest,
    request: Request,
    state: AppState = Depends(get_app_state),
):
    """Exchanges a valid one-time handover token for the session's admin token.

    The admin token is returned in the POST body, never in a URL, so it stays
    out of proxy/access logs. A failed attempt burns the token (no replay).
    """
    _enforce_read_rate_limit(request, state)
    sid = session_id.strip().upper()
    session = state.sessions.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail="session_not_found")
    if not state.consume_handover_token(req.token, sid):
        raise HTTPException(status_code=401, detail="invalid_handover")
    return {"admin_token": session["admin_token"]}


@router.get("/api/sessions/{session_id}/qr.svg")
async def get_session_qr_svg(
    session_id: str,
    request: Request,
    url: str = Query(...),
    state: AppState = Depends(get_app_state),
):
    _enforce_read_rate_limit(request, state)
    sid = session_id.strip().upper()
    if sid not in state.sessions:
        raise HTTPException(status_code=404, detail="session_not_found")
    # Cap the URL: a huge value would produce an enormous QR code (CPU/memory)
    # in a fully public endpoint
    if len(url) > MAX_QR_URL_LENGTH:
        raise HTTPException(status_code=400, detail="url_too_long")
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
    except Exception:
        # Full traceback in the log; the client gets a generic message –
        # str(exc) could leak internal paths.
        logger.exception("QR-SVG: could not generate QR code for session %s", sid)
        raise HTTPException(status_code=500, detail="Kunde inte generera QR-koden – kontrollera URL:en.")


@router.get("/api/sessions/{session_id}/snapshot.json")
async def export_session_snapshot(
    session_id: str,
    request: Request,
    state: AppState = Depends(get_app_state),
):
    """Exports the full session state as a JSON snapshot (issue #15).

    Same visibility as the CSV export: anyone with the session code. The file
    never contains the admin token.
    """
    _enforce_read_rate_limit(request, state)
    sid = session_id.strip().upper()
    session = state.sessions.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail="session_not_found")
    payload = json.dumps(build_snapshot(session), ensure_ascii=False)
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="riskmatris_{sid}_snapshot.json"'},
    )


@router.post("/api/sessions/import", response_model=CreateSessionResponse)
async def import_session_snapshot(
    request: Request,
    include_votes: bool = Query(default=False),
    state: AppState = Depends(get_app_state),
):
    """Creates a NEW session from a snapshot file (issue #15).

    The snapshot is strictly validated (Pydantic, size cap, no unknown fields)
    and all user text is sanitized. Rate-limited like session creation.
    Votes are only imported when include_votes=true.
    """
    client_ip = request.client.host if request.client else "unknown"
    if not state.check_session_create_rate(client_ip):
        raise HTTPException(status_code=429, detail="too_many_sessions")
    body = await request.body()
    if len(body) > config.MAX_SNAPSHOT_BYTES:
        raise HTTPException(status_code=413, detail="snapshot_too_large")
    try:
        data = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_snapshot_json")
    try:
        snap = SnapshotFile.model_validate(data)
    except ValidationError:
        raise HTTPException(status_code=400, detail="invalid_snapshot")

    session_id = generate_session_id(state.sessions)
    admin_token = secrets.token_urlsafe(24)
    now = time.time()
    risks = risks_from_snapshot(snap, include_votes)
    if not risks:
        risks = [create_new_risk(1, "")]
    session = {
        "session_id": session_id,
        "admin_token": admin_token,
        "title": sanitize_user_text(snap.title, MAX_TITLE_LENGTH) or "Riskanalys",
        "threshold": snap.threshold,
        "created_at": now,
        "updated_at": now,
        "active_risk_number": risks[0]["number"],
        "risks": risks,
    }
    state.sessions[session_id] = session
    await db.save_session_to_db_async(session)
    logger.info("Session %s created from snapshot (%d risks, votes=%s)", session_id, len(risks), include_votes)
    return {
        "session_id": session_id,
        "admin_token": admin_token,
        "title": session["title"],
        "threshold": session["threshold"],
        "lan_ip": get_local_lan_ip(),
    }


@router.get("/api/sessions/{session_id}/export.csv")
async def export_session_csv(
    session_id: str,
    request: Request,
    lang: str = Query(default="sv"),
    state: AppState = Depends(get_app_state),
):
    _enforce_read_rate_limit(request, state)
    sid = session_id.strip().upper()
    session = state.sessions.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail="session_not_found")
    if lang not in SUPPORTED_LANGS:
        raise HTTPException(status_code=400, detail="invalid_lang")
    texts = csv_texts(lang)

    threshold = get_session_threshold(session)
    output = io.StringIO()
    # Write a UTF-8 BOM so Microsoft Excel on Windows renders å, ä, ö correctly when opening the file directly
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";")

    def write_row(cells: list) -> None:
        # Every cell is escaped against CSV formula injection (A03-1): labels and
        # titles are user-controlled and a leading = + - @ (or tab/CR) would be
        # evaluated as a formula when the file is opened in Excel/LibreOffice.
        writer.writerow([sanitize_csv_cell(c) for c in cells])

    write_row(list(texts["headers"]))

    for r in session["risks"]:
        stats = compute_risk_stats(r, threshold)
        prob = stats["effective_probability"]
        cons = stats["effective_consequence"]
        score = stats["score"]
        level = texts["levels"][level_key_for_score(score)] if score else ""
        status_str = (
            texts["status_locked"]
            if r["locked"]
            else (texts["status_open"] if stats["revealed"] else texts["status_hidden"])
        )

        dist_parts = []
        for cell_key, count in sorted(stats["cell_counts"].items()):
            sp, sc = cell_key.split("_")
            dist_parts.append(texts["distribution"].format(p=sp, c=sc, count=count))

        write_row(
            [
                f"#{r['number']}",
                r["label"],
                status_str,
                stats["vote_count"],
                str(stats["avg_probability"]).replace(".", ",") if stats["avg_probability"] is not None else "",
                str(stats["avg_consequence"]).replace(".", ",") if stats["avg_consequence"] is not None else "",
                prob or "",
                texts["prob_labels"].get(prob, "") if prob else "",
                cons or "",
                texts["cons_labels"].get(cons, "") if cons else "",
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
