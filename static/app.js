(() => {
  "use strict";

  const PROB_LABELS = {
    1: "Osannolik",
    2: "Möjlig",
    3: "Sannolik",
    4: "Mycket sannolik",
  };

  const CONS_LABELS = {
    1: "Försumbar",
    2: "Måttlig",
    3: "Allvarlig",
    4: "Mycket allvarlig",
  };

  function getCellMeta(prob, cons) {
    const score = prob * cons;
    if (score <= 2) {
      return { score, level: "Låg", colorClass: "cell-green", pillClass: "green", hexBg: "#86efac", hexBorder: "#16a34a", hexText: "#064e3b" };
    } else if (score <= 6) {
      return { score, level: "Medel", colorClass: "cell-yellow", pillClass: "yellow", hexBg: "#fde047", hexBorder: "#ca8a04", hexText: "#422006" };
    } else if (score <= 9) {
      return { score, level: "Hög", colorClass: "cell-orange", pillClass: "orange", hexBg: "#fdba74", hexBorder: "#ea580c", hexText: "#431407" };
    } else {
      return { score, level: "Mycket Hög", colorClass: "cell-red", pillClass: "red", hexBg: "#fca5a5", hexBorder: "#dc2626", hexText: "#450a0a" };
    }
  }

  // Get or create an anonymous client ID in the browser
  function getClientId() {
    let cid = localStorage.getItem("riskmatris_client_id");
    if (!cid) {
      cid = "c_" + Math.random().toString(36).substring(2, 10) + Date.now().toString(36);
      localStorage.setItem("riskmatris_client_id", cid);
    }
    return cid;
  }

  function getAdminToken(sessionId) {
    // Reads the admin token from localStorage only – never from the URL
    // (avoids leakage via browser history, server logs and the Referer header)
    return localStorage.getItem(`riskmatris_admin_${sessionId}`) || "";
  }

  function saveRecentSession(sessionId, title, isAdmin) {
    try {
      const raw = localStorage.getItem("riskmatris_recent") || "[]";
      let list = JSON.parse(raw).filter((x) => x.session_id !== sessionId);
      list.unshift({ session_id: sessionId, title: title || "Riskanalys", is_admin: isAdmin, ts: Date.now() });
      list = list.slice(0, 6);
      localStorage.setItem("riskmatris_recent", JSON.stringify(list));
    } catch (_) {}
  }

  // Application state
  let currentSessionId = null;
  let sessionState = null;
  let ws = null;
  let reconnectTimer = null;
  let reconnectAttempts = 0;
  let selectedProb = null;
  let selectedCons = null;
  let lastActiveRiskNum = null;
  let adminWantsToVote = false;
  let adminSelectedProb = null;
  let adminSelectedCons = null;
  let customShareBaseUrl = "";
  let currentView = "voteView";

  // DOM elements
  const landingView = document.getElementById("landingView");
  const sessionView = document.getElementById("sessionView");
  const sessionHeaderControls = document.getElementById("sessionHeaderControls");
  const sessionTitleDisplay = document.getElementById("sessionTitleDisplay");
  const wsStatusDot = document.getElementById("wsStatusDot");
  const participantCountText = document.getElementById("participantCountText");
  const headerSessionCode = document.getElementById("headerSessionCode");
  const sidebarSessionCode = document.getElementById("sidebarSessionCode");
  const modalSessionCode = document.getElementById("modalSessionCode");

  const sidebarQrContainer = document.getElementById("sidebarQrContainer");
  const modalQrContainer = document.getElementById("modalQrContainer");
  const shareUrlInput = document.getElementById("shareUrlInput");
  const modalShareUrl = document.getElementById("modalShareUrl");
  const lanIpHint = document.getElementById("lanIpHint");
  const customBaseUrlInput = document.getElementById("customBaseUrlInput");

  const riskListContainer = document.getElementById("riskListContainer");
  const riskCountBadge = document.getElementById("riskCountBadge");
  const adminNextRiskBox = document.getElementById("adminNextRiskBox");
  const btnNextRiskSidebar = document.getElementById("btnNextRiskSidebar");
  const adminSettingsCard = document.getElementById("adminSettingsCard");
  const adminThresholdInput = document.getElementById("adminThresholdInput");
  const thresholdInfo = document.getElementById("thresholdInfo");

  const tabBtnVote = document.getElementById("tabBtnVote");
  const tabBtnPresent = document.getElementById("tabBtnPresent");
  const tabBtnAdmin = document.getElementById("tabBtnAdmin");
  const tabActiveRiskNum = document.getElementById("tabActiveRiskNum");
  const tabLockedCount = document.getElementById("tabLockedCount");
  const voteView = document.getElementById("voteView");
  const presentView = document.getElementById("presentView");
  const adminView = document.getElementById("adminView");
  const presentActive = document.getElementById("presentActive");
  const presentSummary = document.getElementById("presentSummary");
  const tabBtnPresentActive = document.getElementById("tabBtnPresentActive");
  const tabBtnPresentSummary = document.getElementById("tabBtnPresentSummary");
  const adminVoteHint = document.getElementById("adminVoteHint");

  const adminSelfVoteToggleBox = document.getElementById("adminSelfVoteToggleBox");
  const btnToggleAdminVote = document.getElementById("btnToggleAdminVote");

  const activeRiskBadge = document.getElementById("activeRiskBadge");
  const adminRiskLabelInput = document.getElementById("adminRiskLabelInput");
  const participantRiskLabelDisplay = document.getElementById("participantRiskLabelDisplay");
  const activeRiskStatusTag = document.getElementById("activeRiskStatusTag");

  const currentVoteCountText = document.getElementById("currentVoteCountText");
  const currentThresholdText = document.getElementById("currentThresholdText");
  const totalVotesSubtext = document.getElementById("totalVotesSubtext");
  const voteProgressBar = document.getElementById("voteProgressBar");
  const adminRiskActions = document.getElementById("adminRiskActions");
  const btnRevealNow = document.getElementById("btnRevealNow");
  const btnResetVotes = document.getElementById("btnResetVotes");
  const btnLockRisk = document.getElementById("btnLockRisk");
  const btnSaveAndNext = document.getElementById("btnSaveAndNext");

  const votingPanelCard = document.getElementById("votingPanelCard");
  const votingCardRiskNum = document.getElementById("votingCardRiskNum");
  const myVoteSavedBadge = document.getElementById("myVoteSavedBadge");
  const probOptionsGroup = document.getElementById("probOptionsGroup");
  const consOptionsGroup = document.getElementById("consOptionsGroup");
  const mySelectionPreview = document.getElementById("mySelectionPreview");
  
  // Admin vote panel elements
  const adminVotePanel = document.getElementById("adminVotePanel");
  const adminVotingCardRiskNum = document.getElementById("adminVotingCardRiskNum");
  const adminMyVoteSavedBadge = document.getElementById("adminMyVoteSavedBadge");
  const adminProbOptionsGroup = document.getElementById("adminProbOptionsGroup");
  const adminConsOptionsGroup = document.getElementById("adminConsOptionsGroup");
  const adminMySelectionPreview = document.getElementById("adminMySelectionPreview");
  const adminLabelRiskNum = document.getElementById("adminLabelRiskNum");

  const activeMatrixHeading = document.getElementById("activeMatrixHeading");
  const activeMatrixSubtitle = document.getElementById("activeMatrixSubtitle");
  const activeStatsSummaryBox = document.getElementById("activeStatsSummaryBox");
  const statAvgProb = document.getElementById("statAvgProb");
  const statAvgCons = document.getElementById("statAvgCons");
  const statSuggestedCell = document.getElementById("statSuggestedCell");
  const matrixMaskedBanner = document.getElementById("matrixMaskedBanner");
  const activeMatrixWrapper = document.getElementById("activeMatrixWrapper");
  const activeMatrixGrid = document.getElementById("activeMatrixGrid");
  const adminClickMatrixHint = document.getElementById("adminClickMatrixHint");

  const summaryMatrixGrid = document.getElementById("summaryMatrixGrid");
  const summaryTableBody = document.getElementById("summaryTableBody");

  const qrModal = document.getElementById("qrModal");

  // -------------------------------------------------------------------------
  // Initialization & Routing
  // -------------------------------------------------------------------------
  function init() {
    bindLandingEvents();
    bindSessionEvents();
    renderRecentSessions();

    const pathMatch = window.location.pathname.match(/^\/s\/([A-Za-z0-9]+)/);
    if (pathMatch) {
      const sid = pathMatch[1].toUpperCase();
      enterSession(sid);
    }
  }

  function renderRecentSessions() {
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

  function bindLandingEvents() {
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
        if (!res.ok) throw new Error("Kunde inte skapa session");
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

  async function enterSession(sessionId) {
    currentSessionId = sessionId.toUpperCase();
    const adminToken = getAdminToken(currentSessionId);
    const clientId = getClientId();

    try {
      const headers = { "Content-Type": "application/json" };
      if (adminToken) {
        headers["X-Admin-Token"] = adminToken;
      }
      const res = await fetch(
        `/api/sessions/${currentSessionId}?client_id=${encodeURIComponent(clientId)}`,
        { headers }
      );
      if (!res.ok) {
        alert(`Sessionen "${currentSessionId}" hittades inte. Kontrollera koden.`);
        window.history.pushState({}, "", "/");
        return;
      }
      const initialData = await res.json();
      landingView.classList.add("hidden");
      sessionView.classList.remove("hidden");
      sessionHeaderControls.classList.remove("hidden");
      sessionTitleDisplay.classList.remove("hidden");

      saveRecentSession(currentSessionId, initialData.title, initialData.is_admin);
      handleSessionState(initialData);
      updateShareUrlAndQr(initialData.lan_ip);
      connectWebSocket();
    } catch (err) {
      alert("Kunde inte ansluta till sessionen: " + err.message);
    }
  }

  // -------------------------------------------------------------------------
  // QR Code & Share Link
  // -------------------------------------------------------------------------
  function computeShareUrl(lanIp) {
    let origin = customShareBaseUrl.trim() || window.location.origin;
    const host = window.location.hostname;
    if (!customShareBaseUrl && (host === "localhost" || host === "127.0.0.1") && lanIp && lanIp !== "127.0.0.1") {
      const port = window.location.port ? `:${window.location.port}` : "";
      origin = `${window.location.protocol}//${lanIp}${port}`;
      lanIpHint.textContent = `Tips: QR-koden pekar på datorns lokala IP (${lanIp}) så att mobiler på samma Wi-Fi kan ansluta.`;
      lanIpHint.classList.remove("hidden");
    } else {
      lanIpHint.classList.add("hidden");
    }
    return `${origin.replace(/\/$/, "")}/s/${currentSessionId}`;
  }

  function updateShareUrlAndQr(lanIp) {
    const shareUrl = computeShareUrl(lanIp);
    shareUrlInput.value = shareUrl;
    modalShareUrl.textContent = shareUrl;
    if (!customBaseUrlInput.value) {
      customBaseUrlInput.value = shareUrl.replace(`/s/${currentSessionId}`, "");
    }

    const qrEndpoint = `/api/sessions/${currentSessionId}/qr.svg?url=${encodeURIComponent(shareUrl)}`;
    sidebarQrContainer.innerHTML = `<img src="${qrEndpoint}" alt="QR-kod för session ${currentSessionId}" />`;
    modalQrContainer.innerHTML = `<img src="${qrEndpoint}" alt="QR-kod för session ${currentSessionId}" />`;
  }

  // -------------------------------------------------------------------------
  // WebSocket
  // -------------------------------------------------------------------------
  // Request a one-time admin connection ticket via an authenticated HTTP call,
  // so the long-lived admin token never appears in the WebSocket query string.
  async function fetchWsTicket(sessionId, adminToken) {
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

  async function connectWebSocket() {
    if (ws) {
      try {
        ws.close();
      } catch (_) {}
    }
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const adminToken = getAdminToken(currentSessionId);
    const clientId = getClientId();
    // Without a valid ticket we connect as a regular participant.
    const ticket = await fetchWsTicket(currentSessionId, adminToken);
    const role = adminToken && ticket ? "admin" : "participant";

    const wsUrl = `${proto}//${window.location.host}/ws/${currentSessionId}?role=${role}&client_id=${encodeURIComponent(clientId)}${ticket ? `&ticket=${encodeURIComponent(ticket)}` : ""}`;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      wsStatusDot.classList.remove("disconnected");
      reconnectAttempts = 0; // Reset backoff after a successful connection
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "session_state") {
          handleSessionState(data);
        } else if (data.type === "error") {
          showWsError(data.message);
        }
      } catch (_) {}
    };

    ws.onclose = () => {
      wsStatusDot.classList.add("disconnected");
      // Exponential backoff: 1s, 2s, 4s, 8s ... max 30s
      reconnectAttempts++;
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempts - 1), 30000);
      reconnectTimer = setTimeout(() => {
        if (currentSessionId) connectWebSocket();
      }, delay);
    };
  }

  function sendWsAction(payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
    }
  }

  // Show a temporary error message from the server (WebSocket validation)
  let wsErrorTimer = null;
  function showWsError(message) {
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

  // -------------------------------------------------------------------------
  // Handle & Render Session State
  // -------------------------------------------------------------------------
  function handleSessionState(state) {
    sessionState = state;
    const isAdmin = Boolean(state.is_admin);

    // Header & code
    sessionTitleDisplay.textContent = state.title;
    headerSessionCode.textContent = state.session_id;
    sidebarSessionCode.textContent = state.session_id;
    modalSessionCode.textContent = state.session_id;

    const pCount = state.participant_count || 0;
    participantCountText.textContent = `${pCount} ${pCount === 1 ? "deltagare" : "deltagare"}`;

    // Find the active risk
    const activeRisk =
      state.risks.find((r) => r.number === state.active_risk_number) ||
      state.risks[state.risks.length - 1];

    // If the active risk changed: sync the participant's selected buttons with any saved vote
    if (lastActiveRiskNum !== activeRisk.number) {
      lastActiveRiskNum = activeRisk.number;
      if (state.my_vote) {
        selectedProb = state.my_vote.probability;
        selectedCons = state.my_vote.consequence;
      } else {
        selectedProb = null;
        selectedCons = null;
      }
      // Also reset the admin's selected buttons on a new risk
      adminSelectedProb = null;
      adminSelectedCons = null;
    } else if (state.my_vote) {
      selectedProb = state.my_vote.probability;
      selectedCons = state.my_vote.consequence;
    } else if (activeRisk.vote_count === 0) {
      selectedProb = null;
      selectedCons = null;
    }

    // Tab counters
    tabActiveRiskNum.textContent = `#${activeRisk.number}`;
    const lockedCount = state.risks.filter((r) => r.locked).length;
    tabLockedCount.textContent = String(lockedCount);

    // Admin visibility
    adminNextRiskBox.classList.toggle("hidden", !isAdmin);
    adminSettingsCard.classList.toggle("hidden", !isAdmin);
    adminRiskActions.classList.toggle("hidden", !isAdmin);
    adminSelfVoteToggleBox.classList.toggle("hidden", !isAdmin);
    participantRiskLabelDisplay.classList.toggle("hidden", isAdmin);

    // View switcher: participants only see "Rösta" (Vote), admin sees "Presentation" and "Admin"
    tabBtnVote.classList.toggle("hidden", isAdmin);
    tabBtnPresent.classList.toggle("hidden", !isAdmin);
    tabBtnAdmin.classList.toggle("hidden", !isAdmin);
    if (!isAdmin) {
      switchView("voteView");
    } else {
      // Admin should start on adminView by default
      if (currentView !== "adminView" && currentView !== "presentView") {
        switchView("adminView");
      }
    }
    adminVoteHint.classList.toggle("hidden", true); // Always hidden now

    const maxNum = Math.max(...state.risks.map((r) => r.number));
    btnNextRiskSidebar.textContent = `+ Nästa risk (#${maxNum + 1})`;
    btnSaveAndNext.innerHTML = `Lås #${activeRisk.number} &amp; Nästa (#${maxNum + 1}) &rarr;`;

    if (isAdmin) {
      if (document.activeElement !== adminThresholdInput) {
        adminThresholdInput.value = state.threshold;
      }
      thresholdInfo.textContent = `Automatisk visning när ${state.threshold} röster kommit in (${pCount} anslutna deltagare)`;
      if (document.activeElement !== adminRiskLabelInput) {
        adminRiskLabelInput.value = activeRisk.label || "";
        adminRiskLabelInput.placeholder = `Valfri etikett för Risk #${activeRisk.number} (t.ex. från PowerPoint)...`;
      }
      // Update the risk number in the label field's label
      if (adminLabelRiskNum) {
        adminLabelRiskNum.textContent = activeRisk.number;
      }
      adminClickMatrixHint.textContent =
        "Tips för mötesledare: Klicka på valfri ruta i matrisen för att manuellt justera placeringen efter diskussion.";
    } else {
      participantRiskLabelDisplay.textContent = activeRisk.label
        ? `${activeRisk.label}`
        : `Fråga #${activeRisk.number} – Rösta på Sannolikhet & Konsekvens`;
      adminClickMatrixHint.textContent = "";
    }

    // Always show the voting card to participants
    votingPanelCard.classList.toggle("hidden", isAdmin);
    btnToggleAdminVote.textContent = adminWantsToVote ? "Dölj egen röstning" : "Rösta själv på denna risk";
    
    // Show the admin voting panel when the admin wants to vote
    if (adminVotePanel) {
      adminVotePanel.classList.toggle("hidden", !adminWantsToVote);
      if (adminWantsToVote && adminVotingCardRiskNum) {
        adminVotingCardRiskNum.textContent = `Risk #${activeRisk.number}`;
        renderAdminVotingControls(activeRisk, Boolean(state.my_vote));
      }
    }

    // Render the sidebar risk list
    renderSidebarRiskList(state.risks, activeRisk.number, isAdmin);

    // Render the active risk card & voting buttons
    renderActiveRiskHeader(activeRisk, state.threshold, isAdmin);
    renderVotingControls(activeRisk, Boolean(state.my_vote));

    // Render the 4x4 matrix for the active risk
    renderActiveRiskMatrix(activeRisk, state.threshold, isAdmin);

    // Render the summary matrix & table
    renderSummaryMatrix(state.risks, isAdmin);
    renderSummaryTable(state.risks);
  }

  function renderSidebarRiskList(risks, activeNum, isAdmin) {
    riskCountBadge.textContent = `${risks.length} st`;
    riskListContainer.innerHTML = "";

    risks.forEach((r) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "risk-list-item" + (r.number === activeNum ? " active" : "");

      const left = document.createElement("div");
      left.className = "risk-item-left";

      const numSpan = document.createElement("span");
      numSpan.className = "risk-item-num";
      numSpan.textContent = `#${r.number}`;

      const labelSpan = document.createElement("span");
      labelSpan.className = "risk-item-label";
      labelSpan.textContent = r.label || (r.locked ? "Bedömd" : "Pågår...");

      left.appendChild(numSpan);
      left.appendChild(labelSpan);

      const right = document.createElement("div");
      right.className = "risk-item-right";

      if (r.revealed && r.score) {
        const pill = document.createElement("span");
        pill.className = `mini-score-pill ${r.color}`;
        pill.textContent = `${r.score} (${r.level})`;
        right.appendChild(pill);
      } else {
        const votesBadge = document.createElement("span");
        votesBadge.className = "small-muted";
        votesBadge.textContent = `${r.vote_count} svar`;
        right.appendChild(votesBadge);
      }

      btn.appendChild(left);
      btn.appendChild(right);

      btn.addEventListener("click", () => {
        if (isAdmin) {
          sendWsAction({ action: "select_risk", number: r.number });
        }
        switchView("presentView");
      });

      riskListContainer.appendChild(btn);
    });
  }

  function renderActiveRiskHeader(risk, threshold, isAdmin) {
    activeRiskBadge.textContent = `Risk #${risk.number}`;
    votingCardRiskNum.textContent = `Risk #${risk.number}`;

    if (risk.locked) {
      activeRiskStatusTag.textContent = "Låst i sammanställning";
      activeRiskStatusTag.classList.add("locked");
    } else if (risk.revealed) {
      activeRiskStatusTag.textContent = "Resultat visas (öppen för fler svar)";
      activeRiskStatusTag.classList.remove("locked");
    } else {
      activeRiskStatusTag.textContent = "Öppen för röstning";
      activeRiskStatusTag.classList.remove("locked");
    }

    const vCount = risk.vote_count || 0;
    currentVoteCountText.textContent = String(Math.min(vCount, threshold));
    currentThresholdText.textContent = String(threshold);
    totalVotesSubtext.textContent = `(Totalt ${vCount} ${vCount === 1 ? "röst" : "röster"} inkomna)`;

    const pct = threshold > 0 ? Math.min(100, Math.round((vCount / threshold) * 100)) : 100;
    voteProgressBar.style.width = `${pct}%`;

    if (isAdmin) {
      btnRevealNow.classList.toggle("hidden", Boolean(risk.revealed));
      btnLockRisk.textContent = risk.locked ? "Uppdatera låst placering" : "Lås placering i sammanställning";
    }
  }

  function renderVotingControls(risk, hasVoted) {
    myVoteSavedBadge.classList.toggle("hidden", !hasVoted);

    probOptionsGroup.querySelectorAll(".vote-option-btn").forEach((btn) => {
      const p = parseInt(btn.getAttribute("data-prob"), 10);
      btn.classList.toggle("selected", p === selectedProb);
      btn.disabled = Boolean(risk.locked);
    });

    consOptionsGroup.querySelectorAll(".vote-option-btn").forEach((btn) => {
      const c = parseInt(btn.getAttribute("data-cons"), 10);
      btn.classList.toggle("selected", c === selectedCons);
      btn.disabled = Boolean(risk.locked);
    });

    if (risk.locked) {
      mySelectionPreview.textContent = "Omröstningen för denna risk är låst.";
    } else if (selectedProb && selectedCons) {
      const meta = getCellMeta(selectedProb, selectedCons);
      mySelectionPreview.innerHTML =
        `Ditt val: <strong>Sannolikhet ${selectedProb} (${PROB_LABELS[selectedProb]})</strong> &times; ` +
        `<strong>Konsekvens ${selectedCons} (${CONS_LABELS[selectedCons]})</strong> ` +
        `&rarr; Riskvärde <strong>${meta.score} (${meta.level})</strong>`;
    } else {
      mySelectionPreview.textContent = "Klicka på en Sannolikhet (1–4) och en Konsekvens (1–4) ovan för att rösta.";
    }
  }

  function renderAdminVotingControls(risk, hasVoted) {
    if (!adminMyVoteSavedBadge || !adminProbOptionsGroup || !adminConsOptionsGroup || !adminMySelectionPreview) return;
    
    adminMyVoteSavedBadge.classList.toggle("hidden", !hasVoted);

    adminProbOptionsGroup.querySelectorAll(".vote-option-btn").forEach((btn) => {
      const p = parseInt(btn.getAttribute("data-prob"), 10);
      btn.classList.toggle("selected", p === adminSelectedProb);
      btn.disabled = Boolean(risk.locked);
    });

    adminConsOptionsGroup.querySelectorAll(".vote-option-btn").forEach((btn) => {
      const c = parseInt(btn.getAttribute("data-cons"), 10);
      btn.classList.toggle("selected", c === adminSelectedCons);
      btn.disabled = Boolean(risk.locked);
    });

    if (risk.locked) {
      adminMySelectionPreview.textContent = "Omröstningen för denna risk är låst.";
    } else if (adminSelectedProb && adminSelectedCons) {
      const meta = getCellMeta(adminSelectedProb, adminSelectedCons);
      adminMySelectionPreview.innerHTML =
        `Ditt val: <strong>Sannolikhet ${adminSelectedProb} (${PROB_LABELS[adminSelectedProb]})</strong> &times; ` +
        `<strong>Konsekvens ${adminSelectedCons} (${CONS_LABELS[adminSelectedCons]})</strong> ` +
        `&rarr; Riskvärde <strong>${meta.score} (${meta.level})</strong>`;
    } else {
      adminMySelectionPreview.textContent = "Klicka på en Sannolikhet (1–4) och en Konsekvens (1–4) ovan för att rösta.";
    }
  }

  // -------------------------------------------------------------------------
  // Render the 4x4 Matrix for the Active Risk
  // -------------------------------------------------------------------------
  function renderActiveRiskMatrix(risk, threshold, isAdmin) {
    const titleSuffix = risk.label ? ` – ${risk.label}` : "";
    activeMatrixHeading.textContent = `Resultatmatris för Risk #${risk.number}${titleSuffix}`;

    if (!risk.revealed) {
      matrixMaskedBanner.classList.remove("hidden");
      activeMatrixWrapper.classList.add("hidden");
      activeStatsSummaryBox.classList.add("hidden");
      activeMatrixSubtitle.textContent = `Matrisen visas automatiskt när ${threshold} svar har kommit in.`;
      return;
    }

    matrixMaskedBanner.classList.add("hidden");
    activeMatrixWrapper.classList.remove("hidden");

    if (risk.vote_count > 0 || risk.effective_probability) {
      activeStatsSummaryBox.classList.remove("hidden");
      statAvgProb.textContent =
        risk.avg_probability !== null
          ? `${String(risk.avg_probability).replace(".", ",")} (→ ${risk.suggested_probability})`
          : "-";
      statAvgCons.textContent =
        risk.avg_consequence !== null
          ? `${String(risk.avg_consequence).replace(".", ",")} (→ ${risk.suggested_consequence})`
          : "-";

      const effP = risk.effective_probability;
      const effC = risk.effective_consequence;
      if (effP && effC) {
        const meta = getCellMeta(effP, effC);
        const modeLabel = risk.locked
          ? "Låst"
          : risk.final_probability
          ? "Manuellt vald"
          : "Förslag";
        statSuggestedCell.textContent = `${modeLabel}: S=${effP}, K=${effC} → Riskvärde ${meta.score} (${meta.level})`;
      } else {
        statSuggestedCell.textContent = "-";
      }
      activeMatrixSubtitle.textContent =
        "Rösterna är nu synliga och matrisen uppdateras i realtid om fler svar kommer in.";
    } else {
      activeStatsSummaryBox.classList.add("hidden");
      activeMatrixSubtitle.textContent = "Inga röster har registrerats ännu, men matrisen är öppen.";
    }

    activeMatrixGrid.innerHTML = "";

    // Rows: Consequence (Y axis), top to bottom 4 -> 1
    for (let cons = 4; cons >= 1; cons--) {
      // Y-axis label on the left
      const yHeader = document.createElement("div");
      yHeader.className = "matrix-axis-header";
      yHeader.innerHTML = `<span class="axis-num">${cons}</span><span class="axis-name">${CONS_LABELS[cons]}</span>`;
      activeMatrixGrid.appendChild(yHeader);

      // Columns: Probability (X axis), left to right 1 -> 4
      for (let prob = 1; prob <= 4; prob++) {
        const meta = getCellMeta(prob, cons);
        const key = `${prob}_${cons}`;
        const cellVotes = (risk.cell_counts && risk.cell_counts[key]) || 0;

        const isEffectiveTarget =
          risk.effective_probability === prob && risk.effective_consequence === cons;

        const cell = document.createElement("div");
        cell.className = `matrix-cell ${meta.colorClass}`;
        if (isAdmin) cell.classList.add("admin-clickable");
        if (isEffectiveTarget) {
          cell.classList.add(risk.locked ? "locked-cell" : "suggested-cell");
        }

        // Top row: risk score (1-16) + marker for Suggested / Locked
        const topRow = document.createElement("div");
        topRow.className = "cell-top-row";

        const scoreSpan = document.createElement("span");
        scoreSpan.className = "cell-score-number";
        scoreSpan.textContent = String(meta.score);
        topRow.appendChild(scoreSpan);

        if (isEffectiveTarget) {
          const badge = document.createElement("span");
          badge.className =
            "cell-target-badge" + (risk.locked ? "" : " badge-suggested");
          badge.textContent = risk.locked
            ? `Låst #${risk.number}`
            : risk.final_probability
            ? `Vald #${risk.number}`
            : `Förslag #${risk.number}`;
          topRow.appendChild(badge);
        }

        // Middle: vote dots and vote count
        const votesArea = document.createElement("div");
        votesArea.className = "cell-votes-area";
        if (cellVotes > 0) {
          const dotsRow = document.createElement("div");
          dotsRow.className = "vote-dots-row";
          const maxDots = Math.min(cellVotes, 12);
          for (let i = 0; i < maxDots; i++) {
            const dot = document.createElement("span");
            dot.className = "vote-dot";
            dotsRow.appendChild(dot);
          }
          votesArea.appendChild(dotsRow);

          const countPill = document.createElement("span");
          countPill.className = "vote-count-pill";
          countPill.textContent = `${cellVotes} ${cellVotes === 1 ? "röst" : "röster"}`;
          votesArea.appendChild(countPill);
        }

        // Bottom row: level text
        const bottomRow = document.createElement("div");
        bottomRow.className = "cell-bottom-row";
        bottomRow.textContent = meta.level;

        cell.appendChild(topRow);
        cell.appendChild(votesArea);
        cell.appendChild(bottomRow);

        if (isAdmin) {
          cell.title = `Klicka för att placera Risk #${risk.number} i S=${prob} (${PROB_LABELS[prob]}), K=${cons} (${CONS_LABELS[cons]})`;
          cell.addEventListener("click", () => {
            sendWsAction({
              action: "set_final_cell",
              probability: prob,
              consequence: cons,
              lock: risk.locked,
            });
          });
        }

        activeMatrixGrid.appendChild(cell);
      }
    }

    // Bottom row: X-axis headers (Probability 1 -> 4)
    const corner = document.createElement("div");
    corner.className = "matrix-axis-header corner-cell";
    corner.innerHTML = `<span>Konsekvens &uarr;</span><span>Sannolikhet &rarr;</span>`;
    activeMatrixGrid.appendChild(corner);

    for (let prob = 1; prob <= 4; prob++) {
      const xHeader = document.createElement("div");
      xHeader.className = "matrix-axis-header";
      xHeader.innerHTML = `<span class="axis-num">${prob}</span><span class="axis-name">${PROB_LABELS[prob]}</span>`;
      activeMatrixGrid.appendChild(xHeader);
    }
  }

  // -------------------------------------------------------------------------
  // Render the Summary Matrix (all risks #1, #2, #3...)
  // -------------------------------------------------------------------------
  function renderSummaryMatrix(risks, isAdmin) {
    summaryMatrixGrid.innerHTML = "";

    // Group risks per cell (include all locked risks, plus revealed risks that have a suggestion)
    const cellRisksMap = {};
    risks.forEach((r) => {
      if ((r.locked || r.revealed) && r.effective_probability && r.effective_consequence) {
        const key = `${r.effective_probability}_${r.effective_consequence}`;
        if (!cellRisksMap[key]) cellRisksMap[key] = [];
        cellRisksMap[key].push(r);
      }
    });

    for (let cons = 4; cons >= 1; cons--) {
      const yHeader = document.createElement("div");
      yHeader.className = "matrix-axis-header";
      yHeader.innerHTML = `<span class="axis-num">${cons}</span><span class="axis-name">${CONS_LABELS[cons]}</span>`;
      summaryMatrixGrid.appendChild(yHeader);

      for (let prob = 1; prob <= 4; prob++) {
        const meta = getCellMeta(prob, cons);
        const key = `${prob}_${cons}`;
        const placedRisks = cellRisksMap[key] || [];

        const cell = document.createElement("div");
        cell.className = `matrix-cell ${meta.colorClass}`;

        const topRow = document.createElement("div");
        topRow.className = "cell-top-row";
        const scoreSpan = document.createElement("span");
        scoreSpan.className = "cell-score-number";
        scoreSpan.textContent = String(meta.score);
        topRow.appendChild(scoreSpan);

        const chipsContainer = document.createElement("div");
        chipsContainer.className = "summary-risk-chips";

        placedRisks.forEach((r) => {
          const chip = document.createElement("button");
          chip.type = "button";
          chip.className = "summary-risk-chip" + (r.locked ? "" : " unconfirmed");
          chip.textContent = `#${r.number}`;
          chip.title = r.label
            ? `Risk #${r.number}: ${r.label} (Riskvärde ${meta.score} – ${meta.level})`
            : `Risk #${r.number} (Riskvärde ${meta.score} – ${meta.level})`;
          chip.addEventListener("click", () => {
            if (isAdmin) {
              sendWsAction({ action: "select_risk", number: r.number });
            }
            switchView("presentView");
          });
          chipsContainer.appendChild(chip);
        });

        const bottomRow = document.createElement("div");
        bottomRow.className = "cell-bottom-row";
        bottomRow.textContent = meta.level;

        cell.appendChild(topRow);
        cell.appendChild(chipsContainer);
        cell.appendChild(bottomRow);
        summaryMatrixGrid.appendChild(cell);
      }
    }

    const corner = document.createElement("div");
    corner.className = "matrix-axis-header corner-cell";
    corner.innerHTML = `<span>Konsekvens &uarr;</span><span>Sannolikhet &rarr;</span>`;
    summaryMatrixGrid.appendChild(corner);

    for (let prob = 1; prob <= 4; prob++) {
      const xHeader = document.createElement("div");
      xHeader.className = "matrix-axis-header";
      xHeader.innerHTML = `<span class="axis-num">${prob}</span><span class="axis-name">${PROB_LABELS[prob]}</span>`;
      summaryMatrixGrid.appendChild(xHeader);
    }
  }

  function renderSummaryTable(risks) {
    summaryTableBody.innerHTML = "";
    risks.forEach((r) => {
      const tr = document.createElement("tr");
      const effP = r.effective_probability;
      const effC = r.effective_consequence;
      const avgStr =
        r.avg_probability !== null && r.avg_consequence !== null
          ? `S: ${String(r.avg_probability).replace(".", ",")} / K: ${String(r.avg_consequence).replace(".", ",")}`
          : "-";

      const statusText = r.locked
        ? "Låst i sammanställning"
        : r.revealed
        ? "Visad (ej låst)"
        : "Pågår / Dold";

      tr.innerHTML = `
        <td><strong>#${r.number}</strong></td>
        <td>${escapeHtml(r.label || "-")}</td>
        <td>${r.vote_count} st</td>
        <td>${avgStr}</td>
        <td>${effP ? `${effP} – ${PROB_LABELS[effP]}` : "-"}</td>
        <td>${effC ? `${effC} – ${CONS_LABELS[effC]}` : "-"}</td>
        <td><strong>${r.score || "-"}</strong></td>
        <td>${r.level ? `<span class="mini-score-pill ${r.color}">${r.level}</span>` : "-"}</td>
        <td>${statusText}</td>
      `;
      summaryTableBody.appendChild(tr);
    });
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // -------------------------------------------------------------------------
  // Event Bindings in the Session View
  // -------------------------------------------------------------------------
  const VIEW_IDS = ["voteView", "presentView", "adminView"];
  const viewButtons = { voteView: tabBtnVote, presentView: tabBtnPresent, adminView: tabBtnAdmin };
  const viewContainers = { voteView: voteView, presentView: presentView, adminView: adminView };
  let currentPresentSub = "presentActive";

  function switchView(viewId) {
    VIEW_IDS.forEach((id) => {
      viewContainers[id].classList.toggle("hidden", id !== viewId);
      viewButtons[id].classList.toggle("active", id === viewId);
    });
    if (viewId === "presentView") switchPresentSub(currentPresentSub);
  }

  function switchPresentSub(subId) {
    currentPresentSub = subId;
    presentActive.classList.toggle("hidden", subId !== "presentActive");
    presentSummary.classList.toggle("hidden", subId !== "presentSummary");
    tabBtnPresentActive.classList.toggle("active", subId === "presentActive");
    tabBtnPresentSummary.classList.toggle("active", subId === "presentSummary");
  }

  // Copy text to the clipboard. navigator.clipboard is only available in a
  // secure context (HTTPS or localhost) – when accessed over a LAN IP with
  // plain HTTP the API is missing entirely, so we fall back to execCommand,
  // which works everywhere.
  async function copyTextToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch (err) {
        // Fall through to the execCommand fallback below.
      }
    }
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch (err) {
      return false;
    }
  }

  function bindSessionEvents() {
    document.querySelectorAll("#viewSwitcher .tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => switchView(btn.getAttribute("data-view")));
    });
    document.querySelectorAll("#presentSubTabs .tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => switchPresentSub(btn.getAttribute("data-subview")));
    });

    // Probability voting buttons (1-4)
    probOptionsGroup.querySelectorAll(".vote-option-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        selectedProb = parseInt(btn.getAttribute("data-prob"), 10);
        submitVoteIfComplete();
      });
    });

    // Consequence voting buttons (1-4)
    consOptionsGroup.querySelectorAll(".vote-option-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        selectedCons = parseInt(btn.getAttribute("data-cons"), 10);
        submitVoteIfComplete();
      });
    });

    // Admin: toggle own voting
    btnToggleAdminVote.addEventListener("click", () => {
      adminWantsToVote = !adminWantsToVote;
      // Show/hide the voting panel immediately without switching views
      if (adminVotePanel) {
        adminVotePanel.classList.toggle("hidden", !adminWantsToVote);
      }
      if (adminWantsToVote && sessionState) {
        const activeRisk = sessionState.risks.find((r) => r.number === sessionState.active_risk_number) ||
          sessionState.risks[sessionState.risks.length - 1];
        if (adminVotingCardRiskNum) {
          adminVotingCardRiskNum.textContent = `Risk #${activeRisk.number}`;
        }
        renderAdminVotingControls(activeRisk, Boolean(sessionState.my_vote));
      }
    });

    // Admin's probability voting buttons (1-4)
    if (adminProbOptionsGroup) {
      adminProbOptionsGroup.querySelectorAll(".vote-option-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          adminSelectedProb = parseInt(btn.getAttribute("data-prob"), 10);
          submitAdminVoteIfComplete();
        });
      });
    }

    // Admin's consequence voting buttons (1-4)
    if (adminConsOptionsGroup) {
      adminConsOptionsGroup.querySelectorAll(".vote-option-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          adminSelectedCons = parseInt(btn.getAttribute("data-cons"), 10);
          submitAdminVoteIfComplete();
        });
      });
    }

    // Admin: change risk label
    let labelDebounce = null;
    adminRiskLabelInput.addEventListener("input", () => {
      clearTimeout(labelDebounce);
      labelDebounce = setTimeout(() => {
        if (!sessionState) return;
        sendWsAction({
          action: "set_label",
          number: sessionState.active_risk_number,
          label: adminRiskLabelInput.value,
        });
      }, 300);
    });

    // Admin: change the threshold
    adminThresholdInput.addEventListener("change", () => {
      const val = parseInt(adminThresholdInput.value, 10) || 4;
      sendWsAction({ action: "set_threshold", threshold: val });
    });

    // Admin: reveal results now
    btnRevealNow.addEventListener("click", () => {
      sendWsAction({ action: "reveal_now" });
    });

    // Admin: reset votes
    btnResetVotes.addEventListener("click", () => {
      if (confirm("Vill du nollställa alla röster på denna risk?")) {
        sendWsAction({ action: "reset_votes" });
      }
    });

    // Admin: lock placement
    btnLockRisk.addEventListener("click", () => {
      sendWsAction({ action: "lock_risk" });
    });

    // Admin: save & next risk
    btnSaveAndNext.addEventListener("click", () => {
      sendWsAction({ action: "next_risk", auto_lock: true });
    });

    btnNextRiskSidebar.addEventListener("click", () => {
      sendWsAction({ action: "next_risk", auto_lock: true });
      switchView("voteView");
    });

    // Copy share link
    const btnCopyShareUrl = document.getElementById("btnCopyShareUrl");
    btnCopyShareUrl.addEventListener("click", async () => {
      const ok = await copyTextToClipboard(shareUrlInput.value);
      const old = btnCopyShareUrl.textContent;
      if (ok) {
        btnCopyShareUrl.textContent = "Kopierad!";
      } else {
        // Automatic copy was denied – select the link so the user can
        // copy it manually with Ctrl+C.
        shareUrlInput.focus();
        shareUrlInput.select();
        btnCopyShareUrl.textContent = "Kunde inte kopiera";
      }
      setTimeout(() => (btnCopyShareUrl.textContent = old), 1500);
    });

    // QR modal
    const openQrModal = () => qrModal.classList.remove("hidden");
    const closeQrModal = () => qrModal.classList.add("hidden");
    document.getElementById("btnExpandQr").addEventListener("click", openQrModal);
    document.getElementById("qrPreviewWrapper").addEventListener("click", openQrModal);
    document.getElementById("topSessionCodeBox").addEventListener("click", openQrModal);
    document.getElementById("btnCloseQrModal").addEventListener("click", closeQrModal);
    qrModal.addEventListener("click", (e) => {
      if (e.target === qrModal) closeQrModal();
    });

    document.getElementById("btnApplyCustomUrl").addEventListener("click", () => {
      customShareBaseUrl = customBaseUrlInput.value.trim();
      updateShareUrlAndQr(sessionState ? sessionState.lan_ip : "");
    });

    // Export CSV
    document.getElementById("btnExportCsv").addEventListener("click", () => {
      if (!currentSessionId) return;
      window.location.href = `/api/sessions/${currentSessionId}/export.csv`;
    });

    // Export PNG (PowerPoint-ready image of the 4x4 summary matrix)
    document.getElementById("btnExportPng").addEventListener("click", () => {
      if (!sessionState) return;
      exportSummaryMatrixAsPng(sessionState);
    });
  }

  function submitVoteIfComplete() {
    if (sessionState) {
      const activeRisk =
        sessionState.risks.find((r) => r.number === sessionState.active_risk_number) ||
        sessionState.risks[sessionState.risks.length - 1];
      renderVotingControls(activeRisk, Boolean(sessionState.my_vote));
    }
    if (selectedProb && selectedCons) {
      sendWsAction({
        action: "vote",
        probability: selectedProb,
        consequence: selectedCons,
      });
    }
  }

  function submitAdminVoteIfComplete() {
    if (sessionState) {
      const activeRisk =
        sessionState.risks.find((r) => r.number === sessionState.active_risk_number) ||
        sessionState.risks[sessionState.risks.length - 1];
      renderAdminVotingControls(activeRisk, Boolean(sessionState.my_vote));
    }
    if (adminSelectedProb && adminSelectedCons) {
      sendWsAction({
        action: "vote",
        probability: adminSelectedProb,
        consequence: adminSelectedCons,
      });
    }
  }

  // -------------------------------------------------------------------------
  // High-resolution PNG Export of the Summary Matrix (for PowerPoint)
  // -------------------------------------------------------------------------
  function exportSummaryMatrixAsPng(state) {
    const canvas = document.createElement("canvas");
    canvas.width = 1600;
    canvas.height = 1040;
    const ctx = canvas.getContext("2d");

    // Background
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Title
    ctx.fillStyle = "#0f172a";
    ctx.font = "bold 34px Segoe UI, Arial, sans-serif";
    ctx.fillText(`Riskmatris – ${state.title} (Session ${state.session_id})`, 70, 58);

    ctx.fillStyle = "#64748b";
    ctx.font = "20px Segoe UI, Arial, sans-serif";
    const dateStr = new Date().toLocaleDateString("sv-SE");
    ctx.fillText(`Sammanställning av bedömda risker • ${dateStr}`, 70, 92);

    // Matrix geometry
    const startX = 290;
    const startY = 125;
    const cellW = 295;
    const cellH = 165;
    const gap = 10;

    // Group risks per cell
    const cellRisksMap = {};
    state.risks.forEach((r) => {
      if ((r.locked || r.revealed) && r.effective_probability && r.effective_consequence) {
        const key = `${r.effective_probability}_${r.effective_consequence}`;
        if (!cellRisksMap[key]) cellRisksMap[key] = [];
        cellRisksMap[key].push(r);
      }
    });

    // Y-axis title (CONSEQUENCE)
    ctx.save();
    ctx.translate(45, startY + (cellH * 4 + gap * 3) / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillStyle = "#1e293b";
    ctx.font = "bold 22px Segoe UI, Arial, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("KONSEKVENS ↑", 0, 0);
    ctx.restore();

    // Rows: Consequence 4 -> 1
    for (let rowIdx = 0; rowIdx < 4; rowIdx++) {
      const cons = 4 - rowIdx;
      const y = startY + rowIdx * (cellH + gap);

      // Y-axis label box
      drawRoundedRect(ctx, 75, y, 200, cellH, 12, "#1e293b", "#1e293b");
      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 28px Segoe UI, Arial, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(String(cons), 175, y + 72);
      ctx.font = "18px Segoe UI, Arial, sans-serif";
      ctx.fillStyle = "#e2e8f0";
      ctx.fillText(CONS_LABELS[cons], 175, y + 105);

      // Columns: Probability 1 -> 4
      for (let colIdx = 0; colIdx < 4; colIdx++) {
        const prob = colIdx + 1;
        const x = startX + colIdx * (cellW + gap);
        const meta = getCellMeta(prob, cons);
        const placed = cellRisksMap[`${prob}_${cons}`] || [];

        drawRoundedRect(ctx, x, y, cellW, cellH, 12, meta.hexBg, meta.hexBorder, 3);

        // Risk score (1-16) in the top-left corner
        ctx.fillStyle = meta.hexText;
        ctx.font = "bold 28px Segoe UI, Arial, sans-serif";
        ctx.textAlign = "left";
        ctx.fillText(String(meta.score), x + 16, y + 36);

        // Level in the bottom-right corner
        ctx.font = "bold 16px Segoe UI, Arial, sans-serif";
        ctx.textAlign = "right";
        ctx.fillText(meta.level, x + cellW - 14, y + cellH - 14);

        // Draw risk chips (#1, #2, #3...)
        let chipX = x + 16;
        let chipY = y + 54;
        placed.forEach((r) => {
          const text = `#${r.number}`;
          ctx.font = "bold 20px Segoe UI, Arial, sans-serif";
          const tw = ctx.measureText(text).width + 24;
          if (chipX + tw > x + cellW - 12) {
            chipX = x + 16;
            chipY += 40;
          }
          drawRoundedRect(ctx, chipX, chipY, tw, 34, 8, "#0f172a", "#ffffff", 2);
          ctx.fillStyle = "#ffffff";
          ctx.textAlign = "center";
          ctx.fillText(text, chipX + tw / 2, chipY + 24);
          chipX += tw + 8;
        });
      }
    }

    // X-axis labels (Probability 1 -> 4)
    const xHeaderY = startY + 4 * (cellH + gap);
    drawRoundedRect(ctx, 75, xHeaderY, 200, 80, 12, "#334155", "#334155");
    ctx.fillStyle = "#cbd5e1";
    ctx.font = "bold 16px Segoe UI, Arial, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("Konsekvens ↑", 175, xHeaderY + 34);
    ctx.fillText("Sannolikhet →", 175, xHeaderY + 58);

    for (let colIdx = 0; colIdx < 4; colIdx++) {
      const prob = colIdx + 1;
      const x = startX + colIdx * (cellW + gap);
      drawRoundedRect(ctx, x, xHeaderY, cellW, 80, 12, "#1e293b", "#1e293b");
      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 26px Segoe UI, Arial, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(String(prob), x + cellW / 2, xHeaderY + 34);
      ctx.fillStyle = "#e2e8f0";
      ctx.font = "18px Segoe UI, Arial, sans-serif";
      ctx.fillText(PROB_LABELS[prob], x + cellW / 2, xHeaderY + 62);
    }

    // X-axis title
    ctx.fillStyle = "#1e293b";
    ctx.font = "bold 22px Segoe UI, Arial, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("SANNOLIKHET →", startX + (cellW * 4 + gap * 3) / 2, xHeaderY + 118);

    // Color legend at the bottom
    const legendItems = [
      { label: "1–2 Låg risk", color: "#86efac", border: "#16a34a" },
      { label: "3–6 Medelrisk", color: "#fde047", border: "#ca8a04" },
      { label: "8–9 Hög risk", color: "#fdba74", border: "#ea580c" },
      { label: "12–16 Mycket hög risk", color: "#fca5a5", border: "#dc2626" },
    ];
    let lx = 290;
    const ly = 985;
    legendItems.forEach((item) => {
      drawRoundedRect(ctx, lx, ly - 18, 24, 24, 5, item.color, item.border, 2);
      ctx.fillStyle = "#1e293b";
      ctx.font = "bold 18px Segoe UI, Arial, sans-serif";
      ctx.textAlign = "left";
      ctx.fillText(item.label, lx + 34, ly);
      lx += 260;
    });

    const link = document.createElement("a");
    link.download = `riskmatris_${state.session_id}.png`;
    link.href = canvas.toDataURL("image/png");
    link.click();
  }

  function drawRoundedRect(ctx, x, y, w, h, r, fill, stroke, lineWidth = 1) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.fill();
    if (stroke) {
      ctx.lineWidth = lineWidth;
      ctx.strokeStyle = stroke;
      ctx.stroke();
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();

