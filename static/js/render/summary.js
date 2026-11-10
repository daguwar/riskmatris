import { consLabel, probLabel } from "../constants.js";
import { t } from "../i18n.js";
import { dom } from "../dom.js";
import { escapeHtml, getCellMeta } from "../utils.js";

export function renderSummaryMatrix() {
  dom.summaryMatrixGrid.innerHTML = "";

  // Static 4x4 color board (rows: Consequence 4 -> 1, columns: Probability
  // 1 -> 4). Cells carry no text – per-risk details live in the summary table
  // below and in the PNG export, which draws its own labeled matrix.
  for (let cons = 4; cons >= 1; cons--) {
    for (let prob = 1; prob <= 4; prob++) {
      const meta = getCellMeta(prob, cons);
      const cell = document.createElement("div");
      cell.className = `matrix-cell ${meta.colorClass}`;
      dom.summaryMatrixGrid.appendChild(cell);
    }
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

