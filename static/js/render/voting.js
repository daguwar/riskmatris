import { CONS_LABELS, PROB_LABELS } from "../constants.js";
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
    dom.mySelectionPreview.textContent = "Omröstningen för denna risk är låst.";
  } else if (state.selectedProb && state.selectedCons) {
    const meta = getCellMeta(state.selectedProb, state.selectedCons);
    dom.mySelectionPreview.innerHTML =
      `Ditt val: <strong>Sannolikhet ${state.selectedProb} (${PROB_LABELS[state.selectedProb]})</strong> &times; ` +
      `<strong>Konsekvens ${state.selectedCons} (${CONS_LABELS[state.selectedCons]})</strong> ` +
      `&rarr; Riskvärde <strong>${meta.score} (${meta.level})</strong>`;
  } else {
    dom.mySelectionPreview.textContent = "Klicka på en Sannolikhet (1–4) och en Konsekvens (1–4) ovan för att rösta.";
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
    dom.adminMySelectionPreview.textContent = "Omröstningen för denna risk är låst.";
  } else if (state.adminSelectedProb && state.adminSelectedCons) {
    const meta = getCellMeta(state.adminSelectedProb, state.adminSelectedCons);
    dom.adminMySelectionPreview.innerHTML =
      `Ditt val: <strong>Sannolikhet ${state.adminSelectedProb} (${PROB_LABELS[state.adminSelectedProb]})</strong> &times; ` +
      `<strong>Konsekvens ${state.adminSelectedCons} (${CONS_LABELS[state.adminSelectedCons]})</strong> ` +
      `&rarr; Riskvärde <strong>${meta.score} (${meta.level})</strong>`;
  } else {
    dom.adminMySelectionPreview.textContent =
      "Klicka på en Sannolikhet (1–4) och en Konsekvens (1–4) ovan för att rösta.";
  }
}
