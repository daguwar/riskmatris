import { dom } from "./dom.js";
import { state } from "./state.js";
import { getAdminToken, getClientId } from "./utils.js";

let wsErrorTimer = null;

export function showWsError(message) {
  let banner = document.getElementById("wsErrorBanner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "wsErrorBanner";
    banner.className = "ws-error-banner";
    const main = document.querySelector(".session-main");
    if (main) main.insertBefore(banner, main.firstChild);
    else document.body.appendChild(banner);
  }
  banner.textContent = message;
  banner.classList.remove("hidden");
  if (wsErrorTimer) clearTimeout(wsErrorTimer);
  wsErrorTimer = setTimeout(() => banner.classList.add("hidden"), 4000);
}

export async function fetchWsTicket(sessionId, adminToken) {
  if (!adminToken) return "";
  try {
    const res = await fetch(`/api/sessions/${sessionId}/ws-ticket`, {
      headers: { "X-Admin-Token": adminToken },
    });
    if (!res.ok) return "";
    const data = await res.json();
    return data.ticket || "";
  } catch (_) {
    return "";
  }
}

export function sendWsAction(payload) {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify(payload));
  }
}

export async function connectWebSocket(onStateReceived) {
  if (state.ws) {
    try {
      state.ws.close();
    } catch (_) {}
  }
  if (state.reconnectTimer) {
    clearTimeout(state.reconnectTimer);
    state.reconnectTimer = null;
  }

  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const adminToken = getAdminToken(state.currentSessionId);
  const clientId = getClientId();
  const ticket = await fetchWsTicket(state.currentSessionId, adminToken);
  const role = adminToken && ticket ? "admin" : "participant";

  const wsUrl = `${proto}//${window.location.host}/ws/${state.currentSessionId}?role=${role}&client_id=${encodeURIComponent(clientId)}${ticket ? `&ticket=${encodeURIComponent(ticket)}` : ""}`;
  state.ws = new WebSocket(wsUrl);

  state.ws.onopen = () => {
    dom.wsStatusDot.classList.remove("disconnected");
    state.reconnectAttempts = 0;
  };

  state.ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "session_state") {
        onStateReceived(data);
      } else if (data.type === "error") {
        showWsError(data.message);
      }
    } catch (_) {}
  };

  state.ws.onclose = () => {
    dom.wsStatusDot.classList.add("disconnected");
    state.reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(2, state.reconnectAttempts - 1), 30000);
    state.reconnectTimer = setTimeout(() => {
      if (state.currentSessionId) connectWebSocket(onStateReceived);
    }, delay);
  };
}
