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

  // Rows: Consequence (Y axis), top to bottom 4 -> 1
  for (let cons = 4; cons >= 1; cons--) {
    const yHeader = document.createElement("div");
    yHeader.className = "matrix-axis-header";
    yHeader.innerHTML = `<span class="axis-num">${cons}</span><span class="axis-name">${consLabel(cons)}</span>`;
    dom.activeMatrixGrid.appendChild(yHeader);

    // Columns: Probability (X axis), left to right 1 -> 4
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

      // Top row: risk score (1-16) + marker for Suggested / Locked
      const topRow = document.createElement("div");
      topRow.className = "cell-top-row";

      const scoreSpan = document.createElement("span");
      scoreSpan.className = "cell-score-number";
      scoreSpan.textContent = String(meta.score);
      topRow.appendChild(scoreSpan);

      if (isEffectiveTarget) {
        const badge = document.createElement("span");
        badge.className = "cell-target-badge" + (risk.locked ? "" : " badge-suggested");
        badge.textContent = risk.locked
          ? t("cell.badgeLocked", { num: risk.number })
          : risk.final_probability
          ? t("cell.badgeChosen", { num: risk.number })
          : t("cell.badgeSuggested", { num: risk.number });
        topRow.appendChild(badge);
      }

      // Middle: vote dots and vote count
      const votesArea = document.createElement("div");
      votesArea.className = "cell-votes-area";
      if (cellVotes > 0) {
        const dotsRow = document.createElement("div");
        dotsRow.className = "vote-dots-row";
        const maxDots = Math.min(cellVotes, 12);
        for (let i = 0; i < maxDots; i++) {
          const dot = document.createElement("span");
          dot.className = "vote-dot";
          dotsRow.appendChild(dot);
        }
        votesArea.appendChild(dotsRow);

        const countPill = document.createElement("span");
        countPill.className = "vote-count-pill";
        countPill.textContent = t("cell.votes", { count: cellVotes });
        votesArea.appendChild(countPill);
      }

      // Bottom row: level text
      const bottomRow = document.createElement("div");
      bottomRow.className = "cell-bottom-row";
      bottomRow.textContent = meta.level;

      cell.appendChild(topRow);
      cell.appendChild(votesArea);
      cell.appendChild(bottomRow);

      if (isAdmin) {
        // WCAG 2.1 AA: clickable cells must also be keyboard operable.
        // No custom aria-label on purpose: IBM's label-in-name check (2.5.3)
        // string-matches the accessible name against the exact textContent,
        // which a readable label can never match for a grid cell. With no
        // aria-label the name IS the visible text; role="button" + title
        // carry the action.
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

  // Bottom row: X-axis headers (Probability 1 -> 4)
  const corner = document.createElement("div");
  corner.className = "matrix-axis-header corner-cell";
  corner.innerHTML = `<span>Konsekvens &uarr;</span><span>Sannolikhet &rarr;</span>`;
  dom.activeMatrixGrid.appendChild(corner);

  for (let prob = 1; prob <= 4; prob++) {
    const xHeader = document.createElement("div");
    xHeader.className = "matrix-axis-header";
    xHeader.innerHTML = `<span class="axis-num">${prob}</span><span class="axis-name">${probLabel(prob)}</span>`;
    dom.activeMatrixGrid.appendChild(xHeader);
  }
}

