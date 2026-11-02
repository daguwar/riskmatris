"""WebSocket action handlers for participants and admins."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from fastapi import WebSocket

import riskmatris.db as db
from riskmatris.config import MAX_LABEL_LENGTH, MAX_TITLE_LENGTH, logger
from riskmatris.session import compute_risk_stats, create_new_risk, get_session_threshold
from riskmatris.utils import _safe_int, sanitize_user_text
from riskmatris.ws_manager import ConnectionInfo

if TYPE_CHECKING:
    from riskmatris.state import AppState

ActionHandler = Callable[
    [dict[str, Any], dict[str, Any], dict[str, Any], ConnectionInfo, Any],
    Awaitable[bool],
]


async def send_ws_error(websocket: WebSocket, message: str) -> None:
    """Sends an error message back to the client over WebSocket."""
    try:
        await websocket.send_json({"type": "error", "message": message})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Participant Actions
# ---------------------------------------------------------------------------


async def handle_vote(
    session: dict[str, Any],
    active_risk: dict[str, Any],
    msg: dict[str, Any],
    conn: ConnectionInfo,
    state: AppState | None = None,
) -> bool:
    """Participant or admin votes on the active risk."""
    prob = _safe_int(msg, "probability", 0, min_val=1, max_val=4)
    cons = _safe_int(msg, "consequence", 0, min_val=1, max_val=4)
    if prob is None or cons is None:
        await send_ws_error(conn.websocket, "Sannolikhet och Konsekvens måste vara heltal 1–4.")
        return False
    if active_risk["locked"]:
        await send_ws_error(conn.websocket, "Denna risk är låst – röstning ej möjlig.")
        return False

    active_risk["votes"][conn.client_id] = {
        "probability": prob,
        "consequence": cons,
        "updated_at": time.time(),
    }
    eff_thresh = get_session_threshold(session)
    if len(active_risk["votes"]) >= eff_thresh:
        active_risk["revealed"] = True
    await db.save_session_to_db_async(session)
    logger.info(
        "Vote received: session %s, risk #%d, client %s -> P=%d, C=%d (%d votes, threshold %d)",
        session["session_id"],
        session["active_risk_number"],
        conn.client_id,
        prob,
        cons,
        len(active_risk["votes"]),
        eff_thresh,
    )
    return True


# ---------------------------------------------------------------------------
# Admin Actions
# ---------------------------------------------------------------------------


async def handle_reveal_now(
    session: dict[str, Any],
    active_risk: dict[str, Any],
    msg: dict[str, Any],
    conn: ConnectionInfo,
    state: AppState | None = None,
) -> bool:
    """Reveals the results for the active risk immediately."""
    active_risk["revealed"] = True
    await db.save_session_to_db_async(session)
    logger.info("Admin: results revealed – session %s, risk #%d", session["session_id"], session["active_risk_number"])
    return True


async def handle_set_label(
    session: dict[str, Any],
    active_risk: dict[str, Any],
    msg: dict[str, Any],
    conn: ConnectionInfo,
    state: AppState | None = None,
) -> bool:
    """Updates the label for a risk."""
    active_num = session["active_risk_number"]
    risk_num = _safe_int(msg, "number", active_num, min_val=1, max_val=9999)
    if risk_num is None:
        await send_ws_error(conn.websocket, "Ogiltigt risknummer.")
        return False
    label = sanitize_user_text(str(msg.get("label", "")), MAX_LABEL_LENGTH)
    for r in session["risks"]:
        if r["number"] == risk_num:
            r["label"] = label
            break
    await db.save_session_to_db_async(session)
    return True


async def handle_set_title(
    session: dict[str, Any],
    active_risk: dict[str, Any],
    msg: dict[str, Any],
    conn: ConnectionInfo,
    state: AppState | None = None,
) -> bool:
    """Updates the session title."""
    title = sanitize_user_text(str(msg.get("title", "")), MAX_TITLE_LENGTH)
    if title:
        session["title"] = title
        await db.save_session_to_db_async(session)
        return True
    await send_ws_error(conn.websocket, "Titel får inte vara tom.")
    return False


async def handle_set_threshold(
    session: dict[str, Any],
    active_risk: dict[str, Any],
    msg: dict[str, Any],
    conn: ConnectionInfo,
    state: AppState | None = None,
) -> bool:
    """Sets the vote threshold for automatic revealing."""
    new_t = _safe_int(msg, "threshold", 4, min_val=1, max_val=50)
    if new_t is None:
        await send_ws_error(conn.websocket, "Tröskelvärdet måste vara ett heltal 1–50.")
        return False
    session["threshold"] = new_t
    eff_thresh = get_session_threshold(session)
    if len(active_risk["votes"]) > 0 and len(active_risk["votes"]) >= eff_thresh:
        active_risk["revealed"] = True
    await db.save_session_to_db_async(session)
    return True


async def handle_lock_risk(
    session: dict[str, Any],
    active_risk: dict[str, Any],
    msg: dict[str, Any],
    conn: ConnectionInfo,
    state: AppState | None = None,
) -> bool:
    """Locks the final placement in the summary matrix."""
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
        await send_ws_error(conn.websocket, "Sannolikhet och Konsekvens måste vara heltal 1–4.")
        return False

    active_risk["final_probability"] = prob
    active_risk["final_consequence"] = cons
    active_risk["revealed"] = True
    active_risk["locked"] = True
    await db.save_session_to_db_async(session)
    logger.info(
        "Admin: risk #%d locked in session %s -> P=%d, C=%d (risk score %d)",
        session["active_risk_number"],
        session["session_id"],
        prob,
        cons,
        prob * cons,
    )
    return True


async def handle_unlock_risk(
    session: dict[str, Any],
    active_risk: dict[str, Any],
    msg: dict[str, Any],
    conn: ConnectionInfo,
    state: AppState | None = None,
) -> bool:
    """Unlocks a locked risk."""
    active_risk["locked"] = False
    await db.save_session_to_db_async(session)
    return True


async def handle_set_final_cell(
    session: dict[str, Any],
    active_risk: dict[str, Any],
    msg: dict[str, Any],
    conn: ConnectionInfo,
    state: AppState | None = None,
) -> bool:
    """Admin clicks a cell in the matrix to adjust suggested/locked placement."""
    prob = _safe_int(msg, "probability", 0, min_val=1, max_val=4)
    cons = _safe_int(msg, "consequence", 0, min_val=1, max_val=4)
    if prob is None or cons is None:
        await send_ws_error(conn.websocket, "Sannolikhet och Konsekvens måste vara heltal 1–4.")
        return False
    active_risk["final_probability"] = prob
    active_risk["final_consequence"] = cons
    active_risk["revealed"] = True
    if msg.get("lock", False):
        active_risk["locked"] = True
    await db.save_session_to_db_async(session)
    return True


async def handle_next_risk(
    session: dict[str, Any],
    active_risk: dict[str, Any],
    msg: dict[str, Any],
    conn: ConnectionInfo,
    state: AppState | None = None,
) -> bool:
    """Locks current risk if auto_lock is set, and creates the next risk."""
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
    await db.save_session_to_db_async(session)
    logger.info(
        "Admin: new risk #%d created in session %s (%d risks total)",
        next_num,
        session["session_id"],
        len(session["risks"]),
    )
    return True


async def handle_select_risk(
    session: dict[str, Any],
    active_risk: dict[str, Any],
    msg: dict[str, Any],
    conn: ConnectionInfo,
    state: AppState | None = None,
) -> bool:
    """Switches the active risk to the specified number."""
    target_num = _safe_int(msg, "number", 1, min_val=1, max_val=9999)
    if target_num is None:
        await send_ws_error(conn.websocket, "Ogiltigt risknummer.")
        return False
    if any(r["number"] == target_num for r in session["risks"]):
        session["active_risk_number"] = target_num
        await db.save_session_to_db_async(session)
        return True
    await send_ws_error(conn.websocket, f"Risk #{target_num} finns inte.")
    return False


async def handle_reset_votes(
    session: dict[str, Any],
    active_risk: dict[str, Any],
    msg: dict[str, Any],
    conn: ConnectionInfo,
    state: AppState | None = None,
) -> bool:
    """Resets all votes and placement for the active risk."""
    active_risk["votes"] = {}
    active_risk["revealed"] = False
    active_risk["locked"] = False
    active_risk["final_probability"] = None
    active_risk["final_consequence"] = None
    await db.save_session_to_db_async(session)
    return True


async def handle_delete_risk(
    session: dict[str, Any],
    active_risk: dict[str, Any],
    msg: dict[str, Any],
    conn: ConnectionInfo,
    state: AppState | None = None,
) -> bool:
    """Deletes a risk if more than one exists."""
    active_num = session["active_risk_number"]
    target_num = _safe_int(msg, "number", active_num, min_val=1, max_val=9999)
    if target_num is None:
        await send_ws_error(conn.websocket, "Ogiltigt risknummer.")
        return False
    if len(session["risks"]) > 1:
        session["risks"] = [r for r in session["risks"] if r["number"] != target_num]
        if session["active_risk_number"] == target_num:
            session["active_risk_number"] = session["risks"][-1]["number"]
        await db.save_session_to_db_async(session)
        return True
    await send_ws_error(conn.websocket, "Kan inte ta bort den enda risken.")
    return False


async def handle_set_qr_visible(
    session: dict[str, Any],
    active_risk: dict[str, Any],
    msg: dict[str, Any],
    conn: ConnectionInfo,
    state: AppState | None = None,
) -> bool:
    """Shows/hides the large QR overlay in the session's presentation views.

    The flag lives on the session so every connected presentation view
    (including the projector window) follows it in real time, and so it
    survives a reload of the projector window.
    """
    session["qr_visible"] = bool(msg.get("visible", True))
    await db.save_session_to_db_async(session)
    return True


# ---------------------------------------------------------------------------
# Dispatch Tables
# ---------------------------------------------------------------------------

PARTICIPANT_ACTIONS: dict[str, ActionHandler] = {
    "vote": handle_vote,
}

ADMIN_ACTIONS: dict[str, ActionHandler] = {
    "reveal_now": handle_reveal_now,
    "set_label": handle_set_label,
    "set_title": handle_set_title,
    "set_threshold": handle_set_threshold,
    "lock_risk": handle_lock_risk,
    "unlock_risk": handle_unlock_risk,
    "set_final_cell": handle_set_final_cell,
    "next_risk": handle_next_risk,
    "select_risk": handle_select_risk,
    "reset_votes": handle_reset_votes,
    "delete_risk": handle_delete_risk,
    "set_qr_visible": handle_set_qr_visible,
}
