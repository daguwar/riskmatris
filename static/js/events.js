import { dom } from "./dom.js";
import { exportSummaryMatrixAsPng } from "./export-png.js";
import { renderAdminVotingControls, renderVotingControls } from "./render/voting.js";
import { state } from "./state.js";
import {
  copyTextToClipboard,
  getAdminToken,
  getClientId,
  saveRecentSession,
} from "./utils.js";
import {
  closeQrModal,
  handleSessionState,
  openQrModal,
  switchPresentSub,
  switchView,
  updateShareUrlAndQr,
} from "./views.js";
import { connectWebSocket, sendWsAction } from "./ws.js";

/** Reads a FastAPI error detail ("detail") from a failed response, with fallback. */
async function readErrorDetail(res, fallback) {
  try {
    const data = await res.json();
    if (data && typeof data.detail === "string" && data.detail) return data.detail;
  } catch (_) {}
  return `${fallback} (HTTP ${res.status})`;
}

export function renderRecentSessions() {
  try {
    const list = JSON.parse(localStorage.getItem("riskmatris_recent") || "[]");
    const box = document.getElementById("recentSessionsBox");
    const container = document.getElementById("recentSessionsList");
    if (!list.length) {
      box.classList.add("hidden");
      return;
    }
    box.classList.remove("hidden");
    container.innerHTML = "";
    list.forEach((item) => {
      const a = document.createElement("a");
      a.href = `/s/${item.session_id}`;
      a.className = "recent-chip";
      a.textContent = `${item.session_id} – ${item.title}${item.is_admin ? " (Admin)" : ""}`;
      container.appendChild(a);
    });
  } catch (_) {}
}

/** If the URL has ?handover=<token>, exchange it for the admin token (POST body,
 *  never logged) and strip it from the URL. Must run before enterSession(). */
export async function consumeHandoverToken(sid) {
  const params = new URLSearchParams(window.location.search);
  const token = params.get("handover");
  if (!token) return;
  // Always strip the token from the URL (browser history, logs)
  params.delete("handover");
  const qs = params.toString();
  window.history.replaceState({}, "", window.location.pathname + (qs ? `?${qs}` : ""));
  try {
    const res = await fetch(`/api/sessions/${sid}/consume-handover`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    if (!res.ok) {
      alert(await readErrorDetail(res, "Överlämningskoden är ogiltig eller har gått ut"));
      return;
    }
    const data = await res.json();
    localStorage.setItem(`riskmatris_admin_${sid}`, data.admin_token);
  } catch (err) {
    alert("Kunde inte hämta administratörsrollen: " + err.message);
  }
}

export async function enterSession(sessionId) {
  state.currentSessionId = sessionId.toUpperCase();
  const adminToken = getAdminToken(state.currentSessionId);
  const clientId = getClientId();

  try {
    const headers = { "Content-Type": "application/json" };
    if (adminToken) {
      headers["X-Admin-Token"] = adminToken;
    }
    const res = await fetch(
      `/api/sessions/${state.currentSessionId}?client_id=${encodeURIComponent(clientId)}`,
      { headers }
    );
    if (!res.ok) {
      if (res.status === 404) {
        alert(`Sessionen "${state.currentSessionId}" hittades inte. Kontrollera koden.`);
      } else {
        // e.g. 429 rate limited – show the server's message
        alert(await readErrorDetail(res, "Kunde inte ansluta till sessionen"));
      }
      window.history.pushState({}, "", "/");
      return;
    }
    const initialData = await res.json();
    dom.landingView.classList.add("hidden");
    dom.sessionView.classList.remove("hidden");
    dom.sessionHeaderControls.classList.remove("hidden");
    dom.sessionTitleDisplay.classList.remove("hidden");

    saveRecentSession(state.currentSessionId, initialData.title, initialData.is_admin);
    handleSessionState(initialData);
    updateShareUrlAndQr(initialData.lan_ip);
    connectWebSocket(handleSessionState);
  } catch (err) {
    alert("Kunde inte ansluta till sessionen: " + err.message);
  }
}

export function bindLandingEvents() {
  const createForm = document.getElementById("createSessionForm");
  createForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const title = document.getElementById("inputSessionTitle").value.trim() || "Riskanalys";
    const threshold = parseInt(document.getElementById("inputDefaultThreshold").value, 10) || 4;

    try {
      const res = await fetch("/api/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, threshold }),
      });
      if (!res.ok) {
        // e.g. 429 rate limit – show the server's message ("Too many sessions…")
        throw new Error(await readErrorDetail(res, "Kunde inte skapa sessionen"));
      }
      const data = await res.json();
      localStorage.setItem(`riskmatris_admin_${data.session_id}`, data.admin_token);
      saveRecentSession(data.session_id, data.title, true);
      window.history.pushState({}, "", `/s/${data.session_id}`);
      enterSession(data.session_id);
    } catch (err) {
      alert("Ett fel uppstod när sessionen skulle skapas: " + err.message);
    }
  });

  const joinForm = document.getElementById("joinSessionForm");
  joinForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const code = document.getElementById("inputJoinCode").value.trim().toUpperCase();
    if (!code) return;
    window.history.pushState({}, "", `/s/${code}`);
    enterSession(code);
  });
}

export function submitVoteIfComplete() {
  if (state.sessionState) {
    const activeRisk =
      state.sessionState.risks.find((r) => r.number === state.sessionState.active_risk_number) ||
      state.sessionState.risks[state.sessionState.risks.length - 1];
    renderVotingControls(activeRisk, Boolean(state.sessionState.my_vote));
  }
  if (state.selectedProb && state.selectedCons) {
    sendWsAction({
      action: "vote",
      probability: state.selectedProb,
      consequence: state.selectedCons,
    });
  }
}

export function submitAdminVoteIfComplete() {
  if (state.sessionState) {
    const activeRisk =
      state.sessionState.risks.find((r) => r.number === state.sessionState.active_risk_number) ||
      state.sessionState.risks[state.sessionState.risks.length - 1];
    renderAdminVotingControls(activeRisk, Boolean(state.sessionState.my_vote));
  }
  if (state.adminSelectedProb && state.adminSelectedCons) {
    sendWsAction({
      action: "vote",
      probability: state.adminSelectedProb,
      consequence: state.adminSelectedCons,
    });
  }
}

export function bindSessionEvents() {
  document.querySelectorAll("#viewSwitcher .tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchView(btn.getAttribute("data-view")));
  });
  document.querySelectorAll("#presentSubTabs .tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchPresentSub(btn.getAttribute("data-subview")));
  });

  // Probability voting buttons (1-4)
  dom.probOptionsGroup.querySelectorAll(".vote-option-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.selectedProb = parseInt(btn.getAttribute("data-prob"), 10);
      submitVoteIfComplete();
    });
  });

  // Consequence voting buttons (1-4)
  dom.consOptionsGroup.querySelectorAll(".vote-option-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.selectedCons = parseInt(btn.getAttribute("data-cons"), 10);
      submitVoteIfComplete();
    });
  });

  // Admin: toggle own voting
  dom.btnToggleAdminVote.addEventListener("click", () => {
    state.adminWantsToVote = !state.adminWantsToVote;
    if (dom.adminVotePanel) {
      dom.adminVotePanel.classList.toggle("hidden", !state.adminWantsToVote);
    }
    if (state.adminWantsToVote && state.sessionState) {
      const activeRisk =
        state.sessionState.risks.find((r) => r.number === state.sessionState.active_risk_number) ||
        state.sessionState.risks[state.sessionState.risks.length - 1];
      if (dom.adminVotingCardRiskNum) {
        dom.adminVotingCardRiskNum.textContent = `Risk #${activeRisk.number}`;
      }
      renderAdminVotingControls(activeRisk, Boolean(state.sessionState.my_vote));
    }
  });

  // Admin's probability voting buttons (1-4)
  if (dom.adminProbOptionsGroup) {
    dom.adminProbOptionsGroup.querySelectorAll(".vote-option-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.adminSelectedProb = parseInt(btn.getAttribute("data-prob"), 10);
        submitAdminVoteIfComplete();
      });
    });
  }

  // Admin's consequence voting buttons (1-4)
  if (dom.adminConsOptionsGroup) {
    dom.adminConsOptionsGroup.querySelectorAll(".vote-option-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.adminSelectedCons = parseInt(btn.getAttribute("data-cons"), 10);
        submitAdminVoteIfComplete();
      });
    });
  }

  // Admin: change session title (debounced; empty titles are rejected server-side)
  let titleDebounce = null;
  dom.adminTitleInput.addEventListener("input", () => {
    clearTimeout(titleDebounce);
    titleDebounce = setTimeout(() => {
      const title = dom.adminTitleInput.value.trim();
      if (title) {
        sendWsAction({ action: "set_title", title });
      }
    }, 400);
  });

  // Admin: change risk label
  let labelDebounce = null;
  dom.adminRiskLabelInput.addEventListener("input", () => {
    clearTimeout(labelDebounce);
    labelDebounce = setTimeout(() => {
      if (!state.sessionState) return;
      sendWsAction({
        action: "set_label",
        number: state.sessionState.active_risk_number,
        label: dom.adminRiskLabelInput.value,
      });
    }, 300);
  });

  // Admin: change threshold
  dom.adminThresholdInput.addEventListener("change", () => {
    const val = parseInt(dom.adminThresholdInput.value, 10) || 4;
    sendWsAction({ action: "set_threshold", threshold: val });
  });

  // Admin: reveal results now
  dom.btnRevealNow.addEventListener("click", () => {
    sendWsAction({ action: "reveal_now" });
  });

  // Admin: reset votes
  dom.btnResetVotes.addEventListener("click", () => {
    if (confirm("Vill du nollställa alla röster på denna risk?")) {
      sendWsAction({ action: "reset_votes" });
    }
  });

  // Admin: lock placement
  dom.btnLockRisk.addEventListener("click", () => {
    sendWsAction({ action: "lock_risk" });
  });

  // Admin: save & next risk
  dom.btnSaveAndNext.addEventListener("click", () => {
    sendWsAction({ action: "next_risk", auto_lock: true });
  });

  dom.btnNextRiskSidebar.addEventListener("click", () => {
    sendWsAction({ action: "next_risk", auto_lock: true });
    switchView("voteView");
  });

  // Copy share link
  const btnCopyShareUrl = document.getElementById("btnCopyShareUrl");
  btnCopyShareUrl.addEventListener("click", async () => {
    const ok = await copyTextToClipboard(dom.shareUrlInput.value);
    const old = btnCopyShareUrl.textContent;
    if (ok) {
      btnCopyShareUrl.textContent = "Kopierad!";
    } else {
      dom.shareUrlInput.focus();
      dom.shareUrlInput.select();
      btnCopyShareUrl.textContent = "Kunde inte kopiera";
    }
    setTimeout(() => (btnCopyShareUrl.textContent = old), 1500);
  });

  // QR modal: manual open from top bar / share card / presentation view button
  const openQrManually = () => {
    state.qrModalFromRemote = false;
    openQrModal();
  };
  document.getElementById("btnExpandQr").addEventListener("click", openQrManually);
  document.getElementById("qrPreviewWrapper").addEventListener("click", openQrManually);
  document.getElementById("topSessionCodeBox").addEventListener("click", openQrManually);
  document.getElementById("btnPresentQr").addEventListener("click", openQrManually);

  // Closing the QR modal hides it locally; if it was opened by the remote
  // presentation-QR toggle (admin view), also tell the server so the modal
  // closes in every connected presentation window.
  const closeQr = () => {
    const wasRemote = state.qrModalFromRemote;
    state.qrModalFromRemote = false;
    state.showingHandoverQr = false;
    closeQrModal();
    if (wasRemote && state.sessionState && state.sessionState.qr_visible) {
      sendWsAction({ action: "set_qr_visible", visible: false });
    }
  };
  document.getElementById("btnCloseQrModal").addEventListener("click", closeQr);
  dom.qrModal.addEventListener("click", (e) => {
    if (e.target === dom.qrModal) closeQr();
  });

  // Presentation view: separate projector window
  document.getElementById("btnPresentWindow").addEventListener("click", () => {
    window.open(`${window.location.pathname}?view=present`, "_blank", "width=1280,height=860");
  });

  document.getElementById("btnApplyCustomUrl").addEventListener("click", () => {
    state.customShareBaseUrl = dom.customBaseUrlInput.value.trim();
    updateShareUrlAndQr(state.sessionState ? state.sessionState.lan_ip : "");
  });

  // Admin: hand over admin rights to another device via a one-time QR code
  dom.btnHandoverAdmin.addEventListener("click", async () => {
    if (!state.currentSessionId) return;
    try {
      const res = await fetch(`/api/sessions/${state.currentSessionId}/admin-handover`, {
        method: "POST",
        headers: { "X-Admin-Token": getAdminToken(state.currentSessionId) },
      });
      if (!res.ok) throw new Error(await readErrorDetail(res, "Kunde inte skapa överlämningskod"));
      const data = await res.json();
      const handoverUrl = `${window.location.origin}/s/${state.currentSessionId}?handover=${encodeURIComponent(data.ticket)}`;
      const qrEndpoint = `/api/sessions/${state.currentSessionId}/qr.svg?url=${encodeURIComponent(handoverUrl)}`;
      state.showingHandoverQr = true;
      dom.modalQrContainer.innerHTML = `<img src="${qrEndpoint}" alt="QR-kod för överlämning av admin" />`;
      dom.modalSessionCode.textContent = state.currentSessionId;
      dom.modalShareUrl.textContent = `Skanna från den nya enheten inom ${Math.round(data.expires_in / 60)} min – koden kan bara användas en gång.`;
      openQrModal();
    } catch (err) {
      alert(err.message);
    }
  });

  // Admin: show/hide the QR modal in the session's presentation views
  dom.btnTogglePresentQr.addEventListener("click", () => {
    const visible = !(state.sessionState && state.sessionState.qr_visible);
    sendWsAction({ action: "set_qr_visible", visible });
  });

  // Export CSV
  document.getElementById("btnExportCsv").addEventListener("click", () => {
    if (!state.currentSessionId) return;
    window.location.href = `/api/sessions/${state.currentSessionId}/export.csv`;
  });

  // Export PNG
  document.getElementById("btnExportPng").addEventListener("click", () => {
    if (!state.sessionState) return;
    exportSummaryMatrixAsPng(state.sessionState);
  });
}

