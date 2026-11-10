import { consLabel, probLabel } from "../constants.js";
import { t } from "../i18n.js";
import { dom } from "../dom.js";
import { getCellMeta } from "../utils.js";

export function renderActiveRiskMatrix(risk, threshold, isAdmin, onSetFinalCell) {
  const titleSuffix = risk.label ? ` – ${risk.label}` : "";
  dom.activeMatrixHeading.textContent = t("present.matrixTitle", { num: risk.number }) + titleSuffix;

  if (!risk.revealed) {
    dom.matrixMaskedBanner.classList.remove("hidden");
    dom.activeMatrixWrapper.classList.add("hidden");
    dom.activeStatsSummaryBox.classList.add("hidden");
    dom.activeMatrixSubtitle.textContent = t("present.matrixSubThreshold", { threshold });
    return;
  }

  dom.matrixMaskedBanner.classList.add("hidden");
  dom.activeMatrixWrapper.classList.remove("hidden");

  if (risk.vote_count > 0 || risk.effective_probability) {
    dom.activeStatsSummaryBox.classList.remove("hidden");
    dom.statAvgProb.textContent =
      risk.avg_probability !== null
        ? `${String(risk.avg_probability).replace(".", ",")} (→ ${risk.suggested_probability})`
        : "-";
    dom.statAvgCons.textContent =
      risk.avg_consequence !== null
        ? `${String(risk.avg_consequence).replace(".", ",")} (→ ${risk.suggested_consequence})`
        : "-";

    const effP = risk.effective_probability;
    const effC = risk.effective_consequence;
    if (effP && effC) {
      const meta = getCellMeta(effP, effC);
      const modeLabel = risk.locked ? t("stat.modeLocked") : risk.final_probability ? t("stat.modeManual") : t("stat.modeSuggested");
      dom.statSuggestedCell.textContent = t("stat.suggestedCell", { mode: modeLabel, p: effP, c: effC, score: meta.score, level: meta.level });
    } else {
      dom.statSuggestedCell.textContent = "-";
    }
    dom.activeMatrixSubtitle.textContent =
      t("present.matrixSubVisible");
  } else {
    dom.activeStatsSummaryBox.classList.add("hidden");
    dom.activeMatrixSubtitle.textContent = t("present.matrixSubEmpty");
  }

  dom.activeMatrixGrid.innerHTML = "";

  // Pure 4x4 color board: rows = Consequence (Y axis) top to bottom 4 -> 1,
  // columns = Probability (X axis) left to right 1 -> 4. Cells carry no text
  // (only their color plus vote dots); the axis titles and the legend outside
  // the grid explain axes and colors.
  for (let cons = 4; cons >= 1; cons--) {
    for (let prob = 1; prob <= 4; prob++) {
      const meta = getCellMeta(prob, cons);
      const key = `${prob}_${cons}`;
      const cellVotes = (risk.cell_counts && risk.cell_counts[key]) || 0;

      const isEffectiveTarget = risk.effective_probability === prob && risk.effective_consequence === cons;

      const cell = document.createElement("div");
      cell.className = `matrix-cell ${meta.colorClass}`;
      if (isAdmin) cell.classList.add("admin-clickable");
      if (isEffectiveTarget) {
        cell.classList.add(risk.locked ? "locked-cell" : "suggested-cell");
      }

      // Vote dots – purely graphical, no text in cells
      if (cellVotes > 0) {
        const votesArea = document.createElement("div");
        votesArea.className = "cell-votes-area";
        const dotsRow = document.createElement("div");
        dotsRow.className = "vote-dots-row";
        const maxDots = Math.min(cellVotes, 12);
        for (let i = 0; i < maxDots; i++) {
          const dot = document.createElement("span");
          dot.className = "vote-dot";
          dotsRow.appendChild(dot);
        }
        votesArea.appendChild(dotsRow);
        cell.appendChild(votesArea);
      }

      if (isAdmin) {
        // WCAG 2.1 AA: clickable cells must also be keyboard operable.
        // Cells have no visible text anymore, so the accessible name comes
        // from the title attribute (name-from-title); role="button" carries
        // the action.
        const actionLabel = t("cell.actionPlace", { num: risk.number, p: prob, plabel: probLabel(prob), c: cons, clabel: consLabel(cons) });
        cell.title = t("cell.clickTitle", { action: actionLabel });
        cell.tabIndex = 0;
        cell.setAttribute("role", "button");
        cell.addEventListener("click", () => {
          onSetFinalCell(prob, cons, risk.locked);
        });
        cell.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onSetFinalCell(prob, cons, risk.locked);
          }
        });
      }

      dom.activeMatrixGrid.appendChild(cell);
    }
  }
}

