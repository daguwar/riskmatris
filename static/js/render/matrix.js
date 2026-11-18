import { LEVEL_THRESHOLDS, consLabel, probLabel } from "../constants.js";
import { t } from "../i18n.js";
import { dom } from "../dom.js";
import { getCellMeta, matrixSize } from "../utils.js";

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

  // Pure NxN color board (N = session matrix size): rows = Consequence (Y axis)
  // top to bottom N -> 1, columns = Probability (X axis) left to right 1 -> N.
  // Cells carry no text (only their color plus vote dots); the axis titles and
  // the legend outside the grid explain axes and colors.
  const size = matrixSize();
  for (let cons = size; cons >= 1; cons--) {
    for (let prob = 1; prob <= size; prob++) {
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
        const actionLabel = t("cell.actionPlace", { num: risk.number, p: prob, plabel: probLabel(prob, size), c: cons, clabel: consLabel(cons, size) });
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

/**
 * Renders the color legend for the session's matrix size into the given
 * container (keeps an existing .legend-hint child, e.g. the admin hint and
 * the reset-placement button). Score bands mirror the server's
 * LEVEL_THRESHOLDS: 1..green / green+1..yellow / yellow+1..orange / rest red.
 */
export function renderMatrixLegend(el, size = matrixSize()) {
  if (!el) return;
  const keep = Array.from(el.children).filter((c) => !c.classList.contains("legend-item"));
  el.innerHTML = "";
  keep.forEach((c) => el.appendChild(c));
  const [greenMax, yellowMax, orangeMax] = LEVEL_THRESHOLDS[size] || LEVEL_THRESHOLDS[4];
  const max = size * size;
  const bands = [
    [1, greenMax, "level.low", "swatch-green"],
    [greenMax + 1, yellowMax, "level.medium", "swatch-yellow"],
    [yellowMax + 1, orangeMax, "level.high", "swatch-orange"],
    [orangeMax + 1, max, "level.veryHigh", "swatch-red"],
  ];
  for (const [from, to, key, swatch] of bands) {
    const item = document.createElement("span");
    item.className = "legend-item";
    const sw = document.createElement("span");
    sw.className = `legend-swatch ${swatch}`;
    const label = document.createElement("span");
    label.textContent = `${from}–${to} ${t(key)}`;
    item.appendChild(sw);
    item.appendChild(label);
    el.appendChild(item);
  }
}

