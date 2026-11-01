"""Real-time WebSocket communication endpoint."""

import json
import secrets

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from riskmatris.config import (
    MAX_CLIENT_ID_LENGTH,
    WS_MAX_CONNECTIONS_PER_SESSION,
    WS_MAX_MESSAGE_BYTES,
    logger,
)
from riskmatris.state import AppState, get_ws_app_state
from riskmatris.utils import sanitize_user_text
from riskmatris.ws_actions import (
    ADMIN_ACTIONS,
    PARTICIPANT_ACTIONS,
    send_ws_error,
)
from riskmatris.ws_manager import ConnectionInfo

router = APIRouter()


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    role: str = Query(default="participant"),
    client_id: str = Query(default=""),
    ticket: str = Query(default=""),
    state: AppState = Depends(get_ws_app_state),
):
    # Fallback if invoked directly in unit tests without FastAPI dependency runner
    if state is None or not isinstance(state, AppState):
        state = get_ws_app_state(websocket)

    sid = session_id.strip().upper()
    session = state.sessions.get(sid)
    if not session:
        logger.warning("WebSocket: session %s not found – connection denied", sid)
        await websocket.close(code=4004, reason="Sessionen finns inte")
        return

    if state.manager.get_connection_count(sid) >= WS_MAX_CONNECTIONS_PER_SESSION:
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
    is_admin = state.consume_ws_ticket(ticket, sid) if ticket else False
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
    await state.manager.connect(sid, conn)
    logger.info(
        "WebSocket: %s connected to session %s (role: %s, client: %s)",
        "admin" if is_admin else "participant",
        sid,
        effective_role,
        client_id,
    )
    await state.manager.broadcast(session)

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
                await send_ws_error(websocket, "Ogiltigt meddelande.")
                continue

            if len(raw.encode("utf-8")) > WS_MAX_MESSAGE_BYTES:
                await send_ws_error(websocket, "Meddelandet är för stort.")
                continue

            try:
                msg = json.loads(raw)
            except Exception:
                await send_ws_error(websocket, "Ogiltigt JSON-meddelande.")
                continue

            if not isinstance(msg, dict):
                await send_ws_error(websocket, "Meddelandet måste vara ett JSON-objekt.")
                continue

            action = msg.get("action")
            if not isinstance(action, str):
                await send_ws_error(websocket, "Saknar giltig 'action'.")
                continue

            active_num = session["active_risk_number"]
            active_risk = next(
                (r for r in session["risks"] if r["number"] == active_num),
                session["risks"][-1],
            )

            # Action dispatching
            handler = PARTICIPANT_ACTIONS.get(action)
            if handler:
                should_broadcast = await handler(session, active_risk, msg, conn, state)
            elif is_admin:
                admin_handler = ADMIN_ACTIONS.get(action)
                if admin_handler:
                    should_broadcast = await admin_handler(session, active_risk, msg, conn, state)
                else:
                    await send_ws_error(websocket, f"Okänd admin-action: {action}")
                    should_broadcast = False
            else:
                await send_ws_error(websocket, "Du saknar behörighet för denna åtgärd.")
                should_broadcast = False

            if should_broadcast:
                await state.manager.broadcast(session)

    except WebSocketDisconnect:
        state.manager.disconnect(sid, websocket)
        logger.info("WebSocket: client %s disconnected from session %s", client_id, sid)
        await state.manager.broadcast(session)
    except Exception:
        logger.exception("WebSocket: unexpected error for client %s in session %s", client_id, sid)
        state.manager.disconnect(sid, websocket)
        await state.manager.broadcast(session)
