import { consLabel, probLabel } from "../constants.js";
import { t } from "../i18n.js";
import { dom } from "../dom.js";
import { state } from "../state.js";
import { getCellMeta } from "../utils.js";

export function renderVotingControls(risk, hasVoted) {
  dom.myVoteSavedBadge.classList.toggle("hidden", !hasVoted);

  dom.probOptionsGroup.querySelectorAll(".vote-option-btn").forEach((btn) => {
    const p = parseInt(btn.getAttribute("data-prob"), 10);
    btn.classList.toggle("selected", p === state.selectedProb);
    btn.disabled = Boolean(risk.locked);
  });

  dom.consOptionsGroup.querySelectorAll(".vote-option-btn").forEach((btn) => {
    const c = parseInt(btn.getAttribute("data-cons"), 10);
    btn.classList.toggle("selected", c === state.selectedCons);
    btn.disabled = Boolean(risk.locked);
  });

  if (risk.locked) {
    dom.mySelectionPreview.textContent = t("voting.locked");
  } else if (state.selectedProb && state.selectedCons) {
    const meta = getCellMeta(state.selectedProb, state.selectedCons);
    dom.mySelectionPreview.innerHTML =
      `${t("voting.yourChoice")} <strong>${t("vote.probAxis")} ${state.selectedProb} (${probLabel(state.selectedProb)})</strong> &times; ` +
      `<strong>${t("vote.consAxis")} ${state.selectedCons} (${consLabel(state.selectedCons)})</strong> ` +
      t("voting.previewScore", { score: meta.score, level: meta.level });
  } else {
    dom.mySelectionPreview.textContent = t("voting.hintVote");
  }
}

export function renderAdminVotingControls(risk, hasVoted) {
  if (
    !dom.adminMyVoteSavedBadge ||
    !dom.adminProbOptionsGroup ||
    !dom.adminConsOptionsGroup ||
    !dom.adminMySelectionPreview
  )
    return;

  dom.adminMyVoteSavedBadge.classList.toggle("hidden", !hasVoted);

  dom.adminProbOptionsGroup.querySelectorAll(".vote-option-btn").forEach((btn) => {
    const p = parseInt(btn.getAttribute("data-prob"), 10);
    btn.classList.toggle("selected", p === state.adminSelectedProb);
    btn.disabled = Boolean(risk.locked);
  });

  dom.adminConsOptionsGroup.querySelectorAll(".vote-option-btn").forEach((btn) => {
    const c = parseInt(btn.getAttribute("data-cons"), 10);
    btn.classList.toggle("selected", c === state.adminSelectedCons);
    btn.disabled = Boolean(risk.locked);
  });

  if (risk.locked) {
    dom.adminMySelectionPreview.textContent = t("voting.locked");
  } else if (state.adminSelectedProb && state.adminSelectedCons) {
    const meta = getCellMeta(state.adminSelectedProb, state.adminSelectedCons);
    dom.adminMySelectionPreview.innerHTML =
      `${t("voting.yourChoice")} <strong>${t("vote.probAxis")} ${state.adminSelectedProb} (${probLabel(state.adminSelectedProb)})</strong> &times; ` +
      `<strong>${t("vote.consAxis")} ${state.adminSelectedCons} (${consLabel(state.adminSelectedCons)})</strong> ` +
      t("voting.previewScore", { score: meta.score, level: meta.level });
  } else {
    dom.adminMySelectionPreview.textContent = t("voting.hintVote");
  }
}

