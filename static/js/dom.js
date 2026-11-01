/**
 * DOM element references.
 */

export const dom = {};

export function initDom() {
  dom.landingView = document.getElementById("landingView");
  dom.sessionView = document.getElementById("sessionView");
  dom.sessionHeaderControls = document.getElementById("sessionHeaderControls");
  dom.sessionTitleDisplay = document.getElementById("sessionTitleDisplay");
  dom.wsStatusDot = document.getElementById("wsStatusDot");
  dom.participantCountText = document.getElementById("participantCountText");
  dom.headerSessionCode = document.getElementById("headerSessionCode");
  dom.sidebarSessionCode = document.getElementById("sidebarSessionCode");
  dom.modalSessionCode = document.getElementById("modalSessionCode");

  dom.sidebarQrContainer = document.getElementById("sidebarQrContainer");
  dom.modalQrContainer = document.getElementById("modalQrContainer");
  dom.shareUrlInput = document.getElementById("shareUrlInput");
  dom.modalShareUrl = document.getElementById("modalShareUrl");
  dom.lanIpHint = document.getElementById("lanIpHint");
  dom.customBaseUrlInput = document.getElementById("customBaseUrlInput");

  dom.riskListContainer = document.getElementById("riskListContainer");
  dom.riskCountBadge = document.getElementById("riskCountBadge");
  dom.adminNextRiskBox = document.getElementById("adminNextRiskBox");
  dom.btnNextRiskSidebar = document.getElementById("btnNextRiskSidebar");
  dom.adminSettingsCard = document.getElementById("adminSettingsCard");
  dom.adminThresholdInput = document.getElementById("adminThresholdInput");
  dom.thresholdInfo = document.getElementById("thresholdInfo");

  dom.tabBtnVote = document.getElementById("tabBtnVote");
  dom.tabBtnPresent = document.getElementById("tabBtnPresent");
  dom.tabBtnAdmin = document.getElementById("tabBtnAdmin");
  dom.tabActiveRiskNum = document.getElementById("tabActiveRiskNum");
  dom.tabLockedCount = document.getElementById("tabLockedCount");
  dom.voteView = document.getElementById("voteView");
  dom.presentView = document.getElementById("presentView");
  dom.adminView = document.getElementById("adminView");
  dom.presentActive = document.getElementById("presentActive");
  dom.presentSummary = document.getElementById("presentSummary");
  dom.tabBtnPresentActive = document.getElementById("tabBtnPresentActive");
  dom.tabBtnPresentSummary = document.getElementById("tabBtnPresentSummary");
  dom.adminVoteHint = document.getElementById("adminVoteHint");

  dom.adminSelfVoteToggleBox = document.getElementById("adminSelfVoteToggleBox");
  dom.btnToggleAdminVote = document.getElementById("btnToggleAdminVote");

  dom.activeRiskBadge = document.getElementById("activeRiskBadge");
  dom.adminRiskLabelInput = document.getElementById("adminRiskLabelInput");
  dom.participantRiskLabelDisplay = document.getElementById("participantRiskLabelDisplay");
  dom.activeRiskStatusTag = document.getElementById("activeRiskStatusTag");

  dom.currentVoteCountText = document.getElementById("currentVoteCountText");
  dom.currentThresholdText = document.getElementById("currentThresholdText");
  dom.totalVotesSubtext = document.getElementById("totalVotesSubtext");
  dom.voteProgressBar = document.getElementById("voteProgressBar");
  dom.adminRiskActions = document.getElementById("adminRiskActions");
  dom.btnRevealNow = document.getElementById("btnRevealNow");
  dom.btnResetVotes = document.getElementById("btnResetVotes");
  dom.btnLockRisk = document.getElementById("btnLockRisk");
  dom.btnSaveAndNext = document.getElementById("btnSaveAndNext");

  dom.votingPanelCard = document.getElementById("votingPanelCard");
  dom.votingCardRiskNum = document.getElementById("votingCardRiskNum");
  dom.myVoteSavedBadge = document.getElementById("myVoteSavedBadge");
  dom.probOptionsGroup = document.getElementById("probOptionsGroup");
  dom.consOptionsGroup = document.getElementById("consOptionsGroup");
  dom.mySelectionPreview = document.getElementById("mySelectionPreview");

  dom.adminVotePanel = document.getElementById("adminVotePanel");
  dom.adminVotingCardRiskNum = document.getElementById("adminVotingCardRiskNum");
  dom.adminMyVoteSavedBadge = document.getElementById("adminMyVoteSavedBadge");
  dom.adminProbOptionsGroup = document.getElementById("adminProbOptionsGroup");
  dom.adminConsOptionsGroup = document.getElementById("adminConsOptionsGroup");
  dom.adminMySelectionPreview = document.getElementById("adminMySelectionPreview");
  dom.adminLabelRiskNum = document.getElementById("adminLabelRiskNum");

  dom.activeMatrixHeading = document.getElementById("activeMatrixHeading");
  dom.activeMatrixSubtitle = document.getElementById("activeMatrixSubtitle");
  dom.activeStatsSummaryBox = document.getElementById("activeStatsSummaryBox");
  dom.statAvgProb = document.getElementById("statAvgProb");
  dom.statAvgCons = document.getElementById("statAvgCons");
  dom.statSuggestedCell = document.getElementById("statSuggestedCell");
  dom.matrixMaskedBanner = document.getElementById("matrixMaskedBanner");
  dom.activeMatrixWrapper = document.getElementById("activeMatrixWrapper");
  dom.activeMatrixGrid = document.getElementById("activeMatrixGrid");
  dom.adminClickMatrixHint = document.getElementById("adminClickMatrixHint");

  dom.summaryMatrixGrid = document.getElementById("summaryMatrixGrid");
  dom.summaryTableBody = document.getElementById("summaryTableBody");

  dom.qrModal = document.getElementById("qrModal");
}

