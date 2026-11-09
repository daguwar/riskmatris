import { consLabel, probLabel } from "../constants.js";
import { t } from "../i18n.js";
import { dom } from "../dom.js";
import { escapeHtml, getCellMeta } from "../utils.js";

export function renderSummaryMatrix(risks, isAdmin, onSelectRisk) {
  dom.summaryMatrixGrid.innerHTML = "";

  const cellRisksMap = {};
  risks.forEach((r) => {
    if ((r.locked || r.revealed) && r.effective_probability && r.effective_consequence) {
      const key = `${r.effective_probability}_${r.effective_consequence}`;
      if (!cellRisksMap[key]) cellRisksMap[key] = [];
      cellRisksMap[key].push(r);
    }
  });

  for (let cons = 4; cons >= 1; cons--) {
    const yHeader = document.createElement("div");
    yHeader.className = "matrix-axis-header";
    yHeader.innerHTML = `<span class="axis-num">${cons}</span><span class="axis-name">${consLabel(cons)}</span>`;
    dom.summaryMatrixGrid.appendChild(yHeader);

    for (let prob = 1; prob <= 4; prob++) {
      const meta = getCellMeta(prob, cons);
      const key = `${prob}_${cons}`;
      const placedRisks = cellRisksMap[key] || [];

      const cell = document.createElement("div");
      cell.className = `matrix-cell ${meta.colorClass}`;

      const topRow = document.createElement("div");
      topRow.className = "cell-top-row";
      const scoreSpan = document.createElement("span");
      scoreSpan.className = "cell-score-number";
      scoreSpan.textContent = String(meta.score);
      topRow.appendChild(scoreSpan);

      const chipsContainer = document.createElement("div");
      chipsContainer.className = "summary-risk-chips";

      placedRisks.forEach((r) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "summary-risk-chip" + (r.locked ? "" : " unconfirmed");
        chip.textContent = `#${r.number}`;
        chip.title = r.label
          ? t("summary.chipWithLabel", { num: r.number, label: r.label, score: meta.score, level: meta.level })
          : t("summary.chipNoLabel", { num: r.number, score: meta.score, level: meta.level });
        chip.addEventListener("click", () => {
          onSelectRisk(r.number);
        });
        chipsContainer.appendChild(chip);
      });

      const bottomRow = document.createElement("div");
      bottomRow.className = "cell-bottom-row";
      bottomRow.textContent = meta.level;

      cell.appendChild(topRow);
      cell.appendChild(chipsContainer);
      cell.appendChild(bottomRow);
      dom.summaryMatrixGrid.appendChild(cell);
    }
  }

  const corner = document.createElement("div");
  corner.className = "matrix-axis-header corner-cell";
  corner.innerHTML = `<span>${t("present.axisY")}</span><span>${t("present.axisX")}</span>`;
  dom.summaryMatrixGrid.appendChild(corner);

  for (let prob = 1; prob <= 4; prob++) {
    const xHeader = document.createElement("div");
    xHeader.className = "matrix-axis-header";
    xHeader.innerHTML = `<span class="axis-num">${prob}</span><span class="axis-name">${probLabel(prob)}</span>`;
    dom.summaryMatrixGrid.appendChild(xHeader);
  }
}

export function renderSummaryTable(risks) {
  dom.summaryTableBody.innerHTML = "";
  risks.forEach((r) => {
    const tr = document.createElement("tr");
    const effP = r.effective_probability;
    const effC = r.effective_consequence;
    const avgStr =
      r.avg_probability !== null && r.avg_consequence !== null
        ? `S: ${String(r.avg_probability).replace(".", ",")} / K: ${String(r.avg_consequence).replace(".", ",")}`
        : "-";

    const statusText = r.locked
      ? t("vote.statusLocked")
      : r.revealed
      ? t("summary.statusShown")
      : t("summary.statusOngoing");

    tr.innerHTML = `
      <td><strong>#${r.number}</strong></td>
      <td>${escapeHtml(r.label || "-")}</td>
      <td>${t("summary.votesSt", { count: r.vote_count })}</td>
      <td>${avgStr}</td>
      <td>${effP ? `${effP} – ${probLabel(effP)}` : "-"}</td>
      <td>${effC ? `${effC} – ${consLabel(effC)}` : "-"}</td>
      <td><strong>${r.score || "-"}</strong></td>
      <td>${r.level ? `<span class="mini-score-pill ${r.color}">${r.level}</span>` : "-"}</td>
      <td>${statusText}</td>
    `;
    dom.summaryTableBody.appendChild(tr);
  });
}

