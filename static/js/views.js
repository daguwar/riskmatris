import { dom } from "./dom.js";
import { t } from "./i18n.js";
import { renderActiveRiskHeader } from "./render/header.js";
import { renderActiveRiskMatrix } from "./render/matrix.js";
import { renderSidebarRiskList } from "./render/sidebar.js";
import { renderSummaryMatrix, renderSummaryTable } from "./render/summary.js";
import { renderAdminVotingControls, renderVotingControls } from "./render/voting.js";
import { state } from "./state.js";
import { sendWsAction } from "./ws.js";

const VIEW_IDS = ["voteView", "presentView", "adminView"];
let currentPresentSub = "presentActive";

export function openQrModal() {
  dom.qrModal.classList.remove("hidden");
}

export function closeQrModal() {
  dom.qrModal.classList.add("hidden");
}

// The admin toggle "Visa QR i presentationsvyn" drives the shared QR modal:
// while qr_visible is set, the modal is shown in every presentation view.
// Manual open/close (top bar, share card, present view button) is tracked via
// state.qrModalFromRemote so a remote "hide" only closes a remotely opened modal.
function syncQrModal() {
  const remote = Boolean(state.sessionState && state.sessionState.qr_visible);
  if (remote && state.currentView === "presentView") {
    if (dom.qrModal.classList.contains("hidden")) {
      openQrModal();
    }
    state.qrModalFromRemote = true;
  } else if (!remote && state.qrModalFromRemote) {
    closeQrModal();
    state.qrModalFromRemote = false;
  }
}

export function switchView(viewId) {
  state.currentView = viewId;
  const viewButtons = { voteView: dom.tabBtnVote, presentView: dom.tabBtnPresent, adminView: dom.tabBtnAdmin };
  const viewContainers = { voteView: dom.voteView, presentView: dom.presentView, adminView: dom.adminView };

  VIEW_IDS.forEach((id) => {
    viewContainers[id].classList.toggle("hidden", id !== viewId);
    viewButtons[id].classList.toggle("active", id === viewId);
  });
  if (viewId === "presentView") switchPresentSub(currentPresentSub);
  syncQrModal();
}

export function switchPresentSub(subId) {
  currentPresentSub = subId;
  dom.presentActive.classList.toggle("hidden", subId !== "presentActive");
  dom.presentSummary.classList.toggle("hidden", subId !== "presentSummary");
  dom.tabBtnPresentActive.classList.toggle("active", subId === "presentActive");
  dom.tabBtnPresentSummary.classList.toggle("active", subId === "presentSummary");
}

export function computeShareUrl(lanIp) {
  let origin = state.customShareBaseUrl.trim() || window.location.origin;
  const host = window.location.hostname;
  if (!state.customShareBaseUrl && (host === "localhost" || host === "127.0.0.1") && lanIp && lanIp !== "127.0.0.1") {
    const port = window.location.port ? `:${window.location.port}` : "";
    origin = `${window.location.protocol}//${lanIp}${port}`;
    dom.lanIpHint.textContent = t("views.lanHint", { ip: lanIp });
    dom.lanIpHint.classList.remove("hidden");
  } else {
    dom.lanIpHint.classList.add("hidden");
  }
  return `${origin.replace(/\/$/, "")}/s/${state.currentSessionId}`;
}

export function updateShareUrlAndQr(lanIp) {
  const shareUrl = computeShareUrl(lanIp);
  dom.shareUrlInput.value = shareUrl;
  dom.modalShareUrl.textContent = shareUrl;
  if (!dom.customBaseUrlInput.value) {
    dom.customBaseUrlInput.value = shareUrl.replace(`/s/${state.currentSessionId}`, "");
  }

  const qrEndpoint = `/api/sessions/${state.currentSessionId}/qr.svg?url=${encodeURIComponent(shareUrl)}`;
  dom.sidebarQrContainer.innerHTML = `<img src="${qrEndpoint}" alt="${t("views.qrAlt", { sid: state.currentSessionId })}" />`;
  // Don't overwrite the modal QR while a handover QR is intentionally shown
  if (!state.showingHandoverQr) {
    dom.modalQrContainer.innerHTML = `<img src="${qrEndpoint}" alt="${t("views.qrAlt", { sid: state.currentSessionId })}" />`;
  }
}

export function handleSessionState(newState) {
  state.sessionState = newState;
  const isAdmin = Boolean(newState.is_admin);

  // Header & code
  dom.sessionTitleDisplay.textContent = newState.title;
  dom.headerSessionCode.textContent = newState.session_id;
  dom.sidebarSessionCode.textContent = newState.session_id;
  dom.modalSessionCode.textContent = newState.session_id;

  // Admin toggle button label for the presentation QR modal
  const qrVisible = Boolean(newState.qr_visible);
  dom.btnTogglePresentQr.textContent = qrVisible ? t("views.hideQrPresent") : t("share.presentQr");

  const pCount = newState.participant_count || 0;
  dom.participantCountText.textContent = t("views.participantCount", { count: pCount });

  // Find the active risk
  const activeRisk =
    newState.risks.find((r) => r.number === newState.active_risk_number) ||
    newState.risks[newState.risks.length - 1];

  // If the active risk changed: sync the participant's selected buttons with any saved vote
  if (state.lastActiveRiskNum !== activeRisk.number) {
    state.lastActiveRiskNum = activeRisk.number;
    if (newState.my_vote) {
      state.selectedProb = newState.my_vote.probability;
      state.selectedCons = newState.my_vote.consequence;
    } else {
      state.selectedProb = null;
      state.selectedCons = null;
    }
    state.adminSelectedProb = null;
    state.adminSelectedCons = null;
  } else if (newState.my_vote) {
    state.selectedProb = newState.my_vote.probability;
    state.selectedCons = newState.my_vote.consequence;
  } else if (activeRisk.vote_count === 0) {
    state.selectedProb = null;
    state.selectedCons = null;
  }

  // Tab counters
  dom.tabActiveRiskNum.textContent = `#${activeRisk.number}`;
  const lockedCount = newState.risks.filter((r) => r.locked).length;
  dom.tabLockedCount.textContent = String(lockedCount);

  // Admin visibility
  dom.adminNextRiskBox.classList.toggle("hidden", !isAdmin);
  dom.adminSettingsCard.classList.toggle("hidden", !isAdmin);
  dom.adminRiskActions.classList.toggle("hidden", !isAdmin);
  dom.adminSelfVoteToggleBox.classList.toggle("hidden", !isAdmin);
  dom.participantRiskLabelDisplay.classList.toggle("hidden", isAdmin);

  // View switcher
  dom.tabBtnVote.classList.toggle("hidden", isAdmin);
  dom.tabBtnPresent.classList.toggle("hidden", !isAdmin);
  dom.tabBtnAdmin.classList.toggle("hidden", !isAdmin);

  if (!isAdmin) {
    switchView("voteView");
  } else {
    if (state.pendingInitialView) {
      switchView(state.pendingInitialView);
      state.pendingInitialView = null;
    } else if (state.currentView !== "adminView" && state.currentView !== "presentView") {
      switchView("adminView");
    }
  }
  dom.adminVoteHint.classList.toggle("hidden", true);

  const maxNum = Math.max(...newState.risks.map((r) => r.number));
  dom.btnNextRiskSidebar.textContent = t("views.nextRisk", { num: maxNum + 1 });
  dom.btnSaveAndNext.innerHTML = t("views.saveAndNext", { num: activeRisk.number, next: maxNum + 1 });

  if (isAdmin) {
    if (document.activeElement !== dom.adminThresholdInput) {
      dom.adminThresholdInput.value = newState.threshold;
    }
    if (document.activeElement !== dom.adminTitleInput) {
      dom.adminTitleInput.value = newState.title || "";
    }
    dom.thresholdInfo.textContent = t("views.thresholdInfo", { threshold: newState.threshold, count: pCount });
    if (document.activeElement !== dom.adminRiskLabelInput) {
      dom.adminRiskLabelInput.value = activeRisk.label || "";
      dom.adminRiskLabelInput.placeholder = t("views.labelPlaceholderRisk", { num: activeRisk.number });
    }
    if (dom.adminLabelRiskNum) {
      dom.adminLabelRiskNum.textContent = activeRisk.number;
    }
    dom.adminClickMatrixHint.textContent = t("views.adminMatrixHint");
  } else {
    dom.participantRiskLabelDisplay.textContent = activeRisk.label
      ? `${activeRisk.label}`
      : t("views.participantQuestion", { num: activeRisk.number });
    dom.adminClickMatrixHint.textContent = "";
  }

  // Voting cards
  dom.votingPanelCard.classList.toggle("hidden", isAdmin);
  dom.btnToggleAdminVote.textContent = state.adminWantsToVote ? t("views.hideOwnVote") : t("admin.selfVote");

  if (dom.adminVotePanel) {
    dom.adminVotePanel.classList.toggle("hidden", !state.adminWantsToVote);
    if (state.adminWantsToVote && dom.adminVotingCardRiskNum) {
      dom.adminVotingCardRiskNum.textContent = `Risk #${activeRisk.number}`;
      renderAdminVotingControls(activeRisk, Boolean(newState.my_vote));
    }
  }

  const onSelectRisk = (riskNumber) => {
    if (isAdmin) {
      sendWsAction({ action: "select_risk", number: riskNumber });
    }
    // Selecting a risk from the admin view must keep the admin in it (issue #18)
    if (state.currentView !== "adminView") {
      switchView("presentView");
      // A chip click means "show this risk's details" – switch to the
      // active-risk subtab, otherwise the click stays on the summary the
      // chip lives in and appears to do nothing
      switchPresentSub("presentActive");
    }
  };

  const onSetFinalCell = (prob, cons, isLocked) => {
    sendWsAction({
      action: "set_final_cell",
      probability: prob,
      consequence: cons,
      lock: isLocked,
    });
  };

  renderSidebarRiskList(newState.risks, activeRisk.number, isAdmin, onSelectRisk);
  renderActiveRiskHeader(activeRisk, newState.threshold, isAdmin);
  renderVotingControls(activeRisk, Boolean(newState.my_vote));
  renderActiveRiskMatrix(activeRisk, newState.threshold, isAdmin, onSetFinalCell);
  renderSummaryMatrix(newState.risks, isAdmin, onSelectRisk);
  renderSummaryTable(newState.risks);
  syncQrModal();
}

