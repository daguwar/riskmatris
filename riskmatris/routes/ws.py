"""Real-time WebSocket communication endpoint."""

import json
import secrets
import time

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

import riskmatris.db as db
from riskmatris.config import (
    MAX_CLIENT_ID_LENGTH,
    MAX_LABEL_LENGTH,
    MAX_TITLE_LENGTH,
    WS_MAX_CONNECTIONS_PER_SESSION,
    WS_MAX_MESSAGE_BYTES,
    logger,
)
from riskmatris.session import (
    compute_risk_stats,
    create_new_risk,
    get_session_threshold,
)
from riskmatris.utils import _safe_int, sanitize_user_text
from riskmatris.ws_manager import ConnectionInfo, manager
from riskmatris.ws_tickets import consume_ws_ticket

router = APIRouter()


async def _send_ws_error(websocket: WebSocket, message: str) -> None:
    """Sends an error message back to the client over WebSocket."""
    try:
        await websocket.send_json({"type": "error", "message": message})
    except Exception:
        pass


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    role: str = Query(default="participant"),
    client_id: str = Query(default=""),
    ticket: str = Query(default=""),
):
    sid = session_id.strip().upper()
    session = db.SESSIONS.get(sid)
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
    # Clamp/sanitize the client id – it is unbounded query input otherwise
    client_id = sanitize_user_text(client_id, MAX_CLIENT_ID_LENGTH)
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
                db.save_session_to_db(session)
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
                    db.save_session_to_db(session)
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
                    db.save_session_to_db(session)
                    await manager.broadcast(session)

                elif action == "set_title":
                    title = sanitize_user_text(str(msg.get("title", "")), MAX_TITLE_LENGTH)
                    if title:
                        session["title"] = title
                        db.save_session_to_db(session)
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
                    db.save_session_to_db(session)
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
                    db.save_session_to_db(session)
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
                    db.save_session_to_db(session)
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
                    db.save_session_to_db(session)
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
                    db.save_session_to_db(session)
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
                        db.save_session_to_db(session)
                        await manager.broadcast(session)
                    else:
                        await _send_ws_error(websocket, f"Risk #{target_num} finns inte.")

                elif action == "reset_votes":
                    active_risk["votes"] = {}
                    active_risk["revealed"] = False
                    active_risk["locked"] = False
                    active_risk["final_probability"] = None
                    active_risk["final_consequence"] = None
                    db.save_session_to_db(session)
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
                        db.save_session_to_db(session)
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
