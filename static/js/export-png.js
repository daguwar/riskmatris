import { CONS_LABELS, PROB_LABELS } from "./constants.js";
import { drawRoundedRect, getCellMeta } from "./utils.js";

/**
 * High-resolution PNG Export of the Summary Matrix (for PowerPoint).
 */
export function exportSummaryMatrixAsPng(state) {
  const canvas = document.createElement("canvas");
  canvas.width = 1600;
  canvas.height = 1040;
  const ctx = canvas.getContext("2d");

  // Background
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Title
  ctx.fillStyle = "#0f172a";
  ctx.font = "bold 34px Segoe UI, Arial, sans-serif";
  ctx.fillText(`Riskmatris – ${state.title} (Session ${state.session_id})`, 70, 58);

  ctx.fillStyle = "#64748b";
  ctx.font = "20px Segoe UI, Arial, sans-serif";
  const dateStr = new Date().toLocaleDateString("sv-SE");
  ctx.fillText(`Sammanställning av bedömda risker • ${dateStr}`, 70, 92);

  // Matrix geometry
  const startX = 290;
  const startY = 125;
  const cellW = 295;
  const cellH = 165;
  const gap = 10;

  // Group risks per cell
  const cellRisksMap = {};
  state.risks.forEach((r) => {
    if ((r.locked || r.revealed) && r.effective_probability && r.effective_consequence) {
      const key = `${r.effective_probability}_${r.effective_consequence}`;
      if (!cellRisksMap[key]) cellRisksMap[key] = [];
      cellRisksMap[key].push(r);
    }
  });

  // Y-axis title (CONSEQUENCE)
  ctx.save();
  ctx.translate(45, startY + (cellH * 4 + gap * 3) / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillStyle = "#1e293b";
  ctx.font = "bold 22px Segoe UI, Arial, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("KONSEKVENS ↑", 0, 0);
  ctx.restore();

  // Rows: Consequence 4 -> 1
  for (let rowIdx = 0; rowIdx < 4; rowIdx++) {
    const cons = 4 - rowIdx;
    const y = startY + rowIdx * (cellH + gap);

    // Y-axis label box
    drawRoundedRect(ctx, 75, y, 200, cellH, 12, "#1e293b", "#1e293b");
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 28px Segoe UI, Arial, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(String(cons), 175, y + 72);
    ctx.font = "18px Segoe UI, Arial, sans-serif";
    ctx.fillStyle = "#e2e8f0";
    ctx.fillText(CONS_LABELS[cons], 175, y + 105);

    // Columns: Probability 1 -> 4
    for (let colIdx = 0; colIdx < 4; colIdx++) {
      const prob = colIdx + 1;
      const x = startX + colIdx * (cellW + gap);
      const meta = getCellMeta(prob, cons);
      const placed = cellRisksMap[`${prob}_${cons}`] || [];

      drawRoundedRect(ctx, x, y, cellW, cellH, 12, meta.hexBg, meta.hexBorder, 3);

      // Risk score (1-16) in the top-left corner
      ctx.fillStyle = meta.hexText;
      ctx.font = "bold 28px Segoe UI, Arial, sans-serif";
      ctx.textAlign = "left";
      ctx.fillText(String(meta.score), x + 16, y + 36);

      // Level in the bottom-right corner
      ctx.font = "bold 16px Segoe UI, Arial, sans-serif";
      ctx.textAlign = "right";
      ctx.fillText(meta.level, x + cellW - 14, y + cellH - 14);

      // Draw risk chips (#1, #2, #3...)
      let chipX = x + 16;
      let chipY = y + 54;
      placed.forEach((r) => {
        const text = `#${r.number}`;
        ctx.font = "bold 20px Segoe UI, Arial, sans-serif";
        const tw = ctx.measureText(text).width + 24;
        if (chipX + tw > x + cellW - 12) {
          chipX = x + 16;
          chipY += 40;
        }
        drawRoundedRect(ctx, chipX, chipY, tw, 34, 8, "#0f172a", "#ffffff", 2);
        ctx.fillStyle = "#ffffff";
        ctx.textAlign = "center";
        ctx.fillText(text, chipX + tw / 2, chipY + 24);
        chipX += tw + 8;
      });
    }
  }

  // X-axis labels (Probability 1 -> 4)
  const xHeaderY = startY + 4 * (cellH + gap);
  drawRoundedRect(ctx, 75, xHeaderY, 200, 80, 12, "#334155", "#334155");
  ctx.fillStyle = "#cbd5e1";
  ctx.font = "bold 16px Segoe UI, Arial, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("Konsekvens ↑", 175, xHeaderY + 34);
  ctx.fillText("Sannolikhet →", 175, xHeaderY + 58);

  for (let colIdx = 0; colIdx < 4; colIdx++) {
    const prob = colIdx + 1;
    const x = startX + colIdx * (cellW + gap);
    drawRoundedRect(ctx, x, xHeaderY, cellW, 80, 12, "#1e293b", "#1e293b");
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 26px Segoe UI, Arial, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(String(prob), x + cellW / 2, xHeaderY + 34);
    ctx.fillStyle = "#e2e8f0";
    ctx.font = "18px Segoe UI, Arial, sans-serif";
    ctx.fillText(PROB_LABELS[prob], x + cellW / 2, xHeaderY + 62);
  }

  // X-axis title
  ctx.fillStyle = "#1e293b";
  ctx.font = "bold 22px Segoe UI, Arial, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("SANNOLIKHET →", startX + (cellW * 4 + gap * 3) / 2, xHeaderY + 118);

  // Color legend at the bottom
  const legendItems = [
    { label: "1–2 Låg risk", color: "#86efac", border: "#16a34a" },
    { label: "3–6 Medelrisk", color: "#fde047", border: "#ca8a04" },
    { label: "8–9 Hög risk", color: "#fdba74", border: "#ea580c" },
    { label: "12–16 Mycket hög risk", color: "#fca5a5", border: "#dc2626" },
  ];
  let lx = 290;
  const ly = 985;
  legendItems.forEach((item) => {
    drawRoundedRect(ctx, lx, ly - 18, 24, 24, 5, item.color, item.border, 2);
    ctx.fillStyle = "#1e293b";
    ctx.font = "bold 18px Segoe UI, Arial, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(item.label, lx + 34, ly);
    lx += 260;
  });

  const link = document.createElement("a");
  link.download = `riskmatris_${state.session_id}.png`;
  link.href = canvas.toDataURL("image/png");
  link.click();
}
