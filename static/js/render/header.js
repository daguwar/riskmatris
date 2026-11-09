import { dom } from "../dom.js";
import { t } from "../i18n.js";

export function renderActiveRiskHeader(risk, threshold, isAdmin) {
  dom.activeRiskBadge.textContent = `Risk #${risk.number}`;
  dom.votingCardRiskNum.textContent = `Risk #${risk.number}`;

  if (risk.locked) {
    dom.activeRiskStatusTag.textContent = t("vote.statusLocked");
    dom.activeRiskStatusTag.classList.add("locked");
  } else if (risk.revealed) {
    dom.activeRiskStatusTag.textContent = t("vote.statusRevealed");
    dom.activeRiskStatusTag.classList.remove("locked");
  } else {
    dom.activeRiskStatusTag.textContent = t("vote.statusOpen");
    dom.activeRiskStatusTag.classList.remove("locked");
  }

  const vCount = risk.vote_count || 0;
  dom.currentVoteCountText.textContent = String(Math.min(vCount, threshold));
  dom.currentThresholdText.textContent = String(threshold);
  dom.totalVotesSubtext.textContent = t("vote.totalVotes", { count: vCount });

  const pct = threshold > 0 ? Math.min(100, Math.round((vCount / threshold) * 100)) : 100;
  dom.voteProgressBar.style.width = `${pct}%`;
  // WCAG 1.3.1: expose the progress bar to assistive technology
  dom.voteProgressBar.setAttribute("aria-valuemax", String(threshold));
  dom.voteProgressBar.setAttribute("aria-valuenow", String(Math.min(vCount, threshold)));
  dom.voteProgressBar.setAttribute("aria-valuetext", t("vote.progressText", { count: Math.min(vCount, threshold), total: threshold }));

  if (isAdmin) {
    dom.btnRevealNow.classList.toggle("hidden", Boolean(risk.revealed));
    dom.btnLockRisk.textContent = risk.locked ? t("vote.lockUpdate") : t("vote.lockInSummary");
  }
}

