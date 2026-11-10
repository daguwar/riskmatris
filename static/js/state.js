/**
 * Application client state.
 */

export const state = {
  currentSessionId: null,
  sessionState: null,
  ws: null,
  reconnectTimer: null,
  reconnectAttempts: 0,
  selectedProb: null,
  selectedCons: null,
  lastActiveRiskNum: null,
  adminWantsToVote: false,
  adminSelectedProb: null,
  adminSelectedCons: null,
  customShareBaseUrl: "",
  currentView: "voteView",
  pendingInitialView: null,
  // True when the page was opened with ?view=present (projector window):
  // presentation view only, no vote/admin tabs
  presentOnly: false,
  // True while the QR modal is open because of the remote admin toggle
  // (set_qr_visible) rather than a local button click
  qrModalFromRemote: false,
  // True while the QR modal is intentionally showing the admin-handover QR
  // (so session_state updates don't overwrite it with the share URL)
  showingHandoverQr: false,
};

