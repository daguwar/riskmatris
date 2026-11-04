"""Real-time WebSocket communication endpoint."""

import json
import secrets
import urllib.parse

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

import riskmatris.config as config
import riskmatris.rate_limit as rate_limit
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
from riskmatris.ws_messages import format_validation_error, parse_ws_message

router = APIRouter()


def origin_matches_host(websocket: WebSocket) -> bool:
    """Returns True if the request's Origin header matches its Host (same site).

    Browsers do not enforce same-origin on WebSocket handshakes (RFC 6455
    puts the responsibility on the server), so without this check any webpage
    can open a participant socket and vote if it knows the session code
    (sakerhetsrapport A01-2). The browser always sends Origin; matching it
    against Host covers all legitimate usages of this app – the public domain
    in production, the LAN IP when the QR code points at the local network,
    and the separate projector window.

    Non-browser clients (scripts, curl) send no Origin header and are allowed
    through – a missing header cannot be verified anyway, and they are
    covered by connection/rate limits instead.
    """
    origin = websocket.headers.get("origin")
    if not isinstance(origin, str) or not origin:
        return True
    host = websocket.headers.get("host")
    if not isinstance(host, str) or not host:
        return True

    try:
        parts = urllib.parse.urlsplit(origin)
        origin_host = (parts.hostname or "").lower()
        # No port in the Origin -> derive it from the scheme (https=443, else 80)
        origin_port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        return False
    if not origin_host:
        return False

    # Host header: "example.com", "localhost:8000" or "[::1]:8000"
    if host.startswith("["):
        end = host.find("]")
        req_host = host[1:end].lower() if end > 0 else ""
        rest = host[end + 1 :] if end > 0 else ""
        req_port = int(rest[1:]) if rest.startswith(":") and rest[1:].isdigit() else None
    elif host.count(":") == 1:
        req_host, _, req_port_raw = host.partition(":")
        req_host = req_host.lower()
        req_port = int(req_port_raw) if req_port_raw.isdigit() else None
    else:
        req_host = host.lower()
        req_port = None

    if origin_host != req_host:
        return False
    # The Host header often omits the port (default port behind a proxy);
    # only compare ports when the client actually sent one.
    if req_port is not None and origin_port != req_port:
        return False
    return True


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
    client_ip = websocket.client.host if websocket.client else "unknown"
    # Read/probe rate limit also covers WS handshakes: the distinguishable
    # close codes (4004 = unknown session) would otherwise make session codes
    # enumerable by scripted connects (sakerhetsrapport A01-3).
    if not state.check_session_read_rate(client_ip):
        logger.warning("WebSocket: rate limit hit for client %s (connect to session %s)", client_ip, sid)
        await websocket.close(code=1013, reason="För många anslutningsförsök – försök igen om en stund")
        return

    session = state.sessions.get(sid)
    if not session:
        logger.warning("WebSocket: session %s not found – connection denied", sid)
        await websocket.close(code=4004, reason="Sessionen finns inte")
        return

    # Cross-site WebSocket hijacking: a foreign Origin must never reach the
    # session (vote manipulation and forced early reveal otherwise).
    if not origin_matches_host(websocket):
        origin = websocket.headers.get("origin")
        logger.warning(
            "WebSocket: blocked cross-site connection to session %s – origin %s not allowed (client %s)",
            sid,
            origin,
            client_ip,
        )
        await websocket.close(code=1008, reason="Origin är inte tillåten")
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

    # Per-IP and global connection caps (sakerhetsrapport A04-1/T-1): without
    # them one IP could fill every per-session slot with throwaway connections
    # and starve legitimate participants.
    per_ip_cap = getattr(config, "WS_MAX_CONNECTIONS_PER_IP", 20)
    if state.manager.count_connections_for_ip(client_ip) >= per_ip_cap:
        logger.warning(
            "WebSocket: per-IP connection limit (%d) reached for %s – rejecting",
            per_ip_cap,
            client_ip,
        )
        await websocket.close(code=1013, reason="För många anslutningar från denna adress")
        return
    total_cap = getattr(config, "WS_MAX_CONNECTIONS_TOTAL", 1000)
    if state.manager.total_connection_count() >= total_cap:
        logger.warning(
            "WebSocket: global connection limit (%d) reached – rejecting client %s",
            total_cap,
            client_ip,
        )
        await websocket.close(code=1013, reason="Serverns totala anslutningsgräns är nådd")
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
        client_ip=client_ip,
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

            # Per-connection message rate limit (A04-1): every vote triggers a
            # DB write + a broadcast to all connections, so an unthrottled
            # connection is an amplification vector.
            msg_limit = getattr(config, "WS_MESSAGE_RATE_LIMIT", 120)
            msg_window = getattr(config, "WS_MESSAGE_RATE_WINDOW_SECONDS", 60)
            if not rate_limit.check_connection_message_rate(conn.message_times, msg_limit, msg_window):
                logger.warning(
                    "WebSocket: message rate limit (%d/%ds) hit for client %s in session %s",
                    msg_limit,
                    msg_window,
                    client_id,
                    sid,
                )
                await send_ws_error(websocket, "För många meddelanden – sakta ner takten.")
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

            # Validate the message shape against the Pydantic model for this
            # action before dispatching (fas 7.4) – handlers re-check values
            # defensively, but this gives early, clear validation errors.
            try:
                parse_ws_message(action, msg)
            except ValidationError as exc:
                await send_ws_error(websocket, format_validation_error(exc))
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
