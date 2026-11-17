import {
  consLabel,
  consLabelFull,
  consLabelFullKey,
  consLabelKey,
  probLabel,
  probLabelFull,
  probLabelFullKey,
  probLabelKey,
} from "../constants.js";
import { t } from "../i18n.js";
import { dom } from "../dom.js";
import { state } from "../state.js";
import { getCellMeta, matrixSize } from "../utils.js";

function buildVoteGroup(group, kind, size) {
  if (!group || Number(group.dataset.size) === size) return;
  group.dataset.size = String(size);
  group.style.setProperty("--vote-n", String(size));
  group.innerHTML = "";
  for (let n = 1; n <= size; n++) {
    const isProb = kind === "prob";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "vote-option-btn";
    btn.setAttribute(isProb ? "data-prob" : "data-cons", String(n));
    const shortKey = isProb ? probLabelKey(n, size) : consLabelKey(n, size);
    const fullKey = isProb ? probLabelFullKey(n, size) : consLabelFullKey(n, size);
    // data-i18n-* so a language switch re-translates the generated buttons too
    btn.setAttribute("data-i18n-title", shortKey);
    btn.setAttribute("data-i18n-aria-label", fullKey);
    btn.title = isProb ? probLabel(n, size) : consLabel(n, size);
    btn.setAttribute("aria-label", isProb ? probLabelFull(n, size) : consLabelFull(n, size));
    const num = document.createElement("span");
    num.className = "vote-num";
    num.textContent = String(n);
    btn.appendChild(num);
    group.appendChild(btn);
  }
}

/** (Re)builds the 1..N voting buttons in all option groups for the matrix size. */
export function renderVoteOptionButtons(size = matrixSize()) {
  buildVoteGroup(dom.probOptionsGroup, "prob", size);
  buildVoteGroup(dom.consOptionsGroup, "cons", size);
  buildVoteGroup(dom.adminProbOptionsGroup, "prob", size);
  buildVoteGroup(dom.adminConsOptionsGroup, "cons", size);
}

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
      `${t("voting.yourChoice")} <strong>${t("vote.probAxis")} ${state.selectedProb} (${probLabel(state.selectedProb, matrixSize())})</strong> &times; ` +
      `<strong>${t("vote.consAxis")} ${state.selectedCons} (${consLabel(state.selectedCons, matrixSize())})</strong> ` +
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
      `${t("voting.yourChoice")} <strong>${t("vote.probAxis")} ${state.adminSelectedProb} (${probLabel(state.adminSelectedProb, matrixSize())})</strong> &times; ` +
      `<strong>${t("vote.consAxis")} ${state.adminSelectedCons} (${consLabel(state.adminSelectedCons, matrixSize())})</strong> ` +
      t("voting.previewScore", { score: meta.score, level: meta.level });
  } else {
    dom.adminMySelectionPreview.textContent = t("voting.hintVote");
  }
}

