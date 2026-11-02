/**
 * General helper utilities for risk matrix calculation, storage, and DOM formatting.
 */

import { COLOR_STYLES } from "./constants.js";
import { state } from "./state.js";

/**
 * Cell metadata (score/level/color) comes from the server payload
 * (state.sessionState.cell_meta) so the risk-level thresholds exist in exactly
 * one place – the backend. This function only attaches presentation styles.
 */
export function getCellMeta(prob, cons) {
  const meta = state.sessionState?.cell_meta?.[`${prob}_${cons}`] || {
    score: prob * cons,
    level: "",
    color: "green",
  };
  const styles = COLOR_STYLES[meta.color] || COLOR_STYLES.green;
  return {
    score: meta.score,
    level: meta.level,
    colorClass: styles.colorClass,
    pillClass: styles.pillClass,
    hexBg: styles.hexBg,
    hexBorder: styles.hexBorder,
    hexText: styles.hexText,
  };
}

export function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function getClientId() {
  let cid = localStorage.getItem("riskmatris_client_id");
  if (!cid) {
    cid = "c_" + Math.random().toString(36).substring(2, 10) + Date.now().toString(36);
    localStorage.setItem("riskmatris_client_id", cid);
  }
  return cid;
}

export function getAdminToken(sessionId) {
  // Reads admin token from localStorage only – never from URL
  return localStorage.getItem(`riskmatris_admin_${sessionId}`) || "";
}

export function saveRecentSession(sessionId, title, isAdmin) {
  try {
    const raw = localStorage.getItem("riskmatris_recent") || "[]";
    let list = JSON.parse(raw).filter((x) => x.session_id !== sessionId);
    list.unshift({
      session_id: sessionId,
      title: title || "Riskanalys",
      is_admin: isAdmin,
      ts: Date.now(),
    });
    list = list.slice(0, 6);
    localStorage.setItem("riskmatris_recent", JSON.stringify(list));
  } catch (_) {}
}

export async function copyTextToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_) {
      // Fall through to execCommand
    }
  }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch (_) {
    return false;
  }
}

export function drawRoundedRect(ctx, x, y, w, h, r, fill, stroke, lineWidth = 1) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
  ctx.fillStyle = fill;
  ctx.fill();
  if (stroke) {
    ctx.lineWidth = lineWidth;
    ctx.strokeStyle = stroke;
    ctx.stroke();
  }
}

