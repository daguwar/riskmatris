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
};
