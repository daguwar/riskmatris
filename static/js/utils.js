/**
 * General helper utilities for risk matrix calculation, storage, and DOM formatting.
 */

import { COLOR_STYLES } from "./constants.js";
import { t } from "./i18n.js";
import { state } from "./state.js";

/**
 * Cell metadata (score/level/color) comes from the server payload
 * (state.sessionState.cell_meta) so the risk-level thresholds exist in exactly
 * one place – the backend. This function only attaches presentation styles.
 */
export function levelLabel(score) {
  if (score <= 2) return t("level.low");
  if (score <= 6) return t("level.medium");
  if (score <= 9) return t("level.high");
  return t("level.veryHigh");
}

export function getCellMeta(prob, cons) {
  const meta = state.sessionState?.cell_meta?.[`${prob}_${cons}`] || {
    score: prob * cons,
    level: "",
    color: "green",
  };
  const styles = COLOR_STYLES[meta.color] || COLOR_STYLES.green;
  return {
    score: meta.score,
    level: levelLabel(meta.score),
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
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
    .replace(/`/g, "&#96;");
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

const RECENT_KEY = "riskmatris_recent";

export function readRecentSessions() {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
  } catch (_) {
    return [];
  }
}

function writeRecentSessions(list) {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, 6)));
  } catch (_) {}
}

export function saveRecentSession(sessionId, title, isAdmin, expiresAt = null) {
  try {
    let list = readRecentSessions().filter((x) => x.session_id !== sessionId);
    list.unshift({
      session_id: sessionId,
      title: title || t("default.title"),
      is_admin: isAdmin,
      ts: Date.now(),
      // Absolute expiry (epoch seconds) from the server: updated_at + TTL.
      // Refreshed on activity, so busy sessions stay in the list longer.
      expires_at: typeof expiresAt === "number" ? expiresAt : null,
    });
    writeRecentSessions(list);
  } catch (_) {}
}

/** Refreshes expiry/title of a stored recent session from live session state. */
export function touchRecentSession(sessionId, expiresAt, title) {
  try {
    const list = readRecentSessions();
    const item = list.find((x) => x.session_id === sessionId);
    if (!item) return;
    if (typeof expiresAt === "number") item.expires_at = expiresAt;
    if (title) item.title = title;
    writeRecentSessions(list);
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

