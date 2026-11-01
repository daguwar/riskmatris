import { dom } from "../dom.js";

export function renderSidebarRiskList(risks, activeNum, isAdmin, onSelectRisk) {
  dom.riskCountBadge.textContent = `${risks.length} st`;
  dom.riskListContainer.innerHTML = "";

  risks.forEach((r) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "risk-list-item" + (r.number === activeNum ? " active" : "");

    const left = document.createElement("div");
    left.className = "risk-item-left";

    const numSpan = document.createElement("span");
    numSpan.className = "risk-item-num";
    numSpan.textContent = `#${r.number}`;

    const labelSpan = document.createElement("span");
    labelSpan.className = "risk-item-label";
    labelSpan.textContent = r.label || (r.locked ? "Bedömd" : "Pågår...");

    left.appendChild(numSpan);
    left.appendChild(labelSpan);

    const right = document.createElement("div");
    right.className = "risk-item-right";

    if (r.revealed && r.score) {
      const pill = document.createElement("span");
      pill.className = `mini-score-pill ${r.color}`;
      pill.textContent = `${r.score} (${r.level})`;
      right.appendChild(pill);
    } else {
      const votesBadge = document.createElement("span");
      votesBadge.className = "small-muted";
      votesBadge.textContent = `${r.vote_count} svar`;
      right.appendChild(votesBadge);
    }

    btn.appendChild(left);
    btn.appendChild(right);

    btn.addEventListener("click", () => {
      onSelectRisk(r.number);
    });

    dom.riskListContainer.appendChild(btn);
  });
}
