/**
 * General helper utilities for risk matrix calculation, storage, and DOM formatting.
 */

export function getCellMeta(prob, cons) {
  const score = prob * cons;
  if (score <= 2) {
    return {
      score,
      level: "Låg",
      colorClass: "cell-green",
      pillClass: "green",
      hexBg: "#86efac",
      hexBorder: "#16a34a",
      hexText: "#064e3b",
    };
  } else if (score <= 6) {
    return {
      score,
      level: "Medel",
      colorClass: "cell-yellow",
      pillClass: "yellow",
      hexBg: "#fde047",
      hexBorder: "#ca8a04",
      hexText: "#422006",
    };
  } else if (score <= 9) {
    return {
      score,
      level: "Hög",
      colorClass: "cell-orange",
      pillClass: "orange",
      hexBg: "#fdba74",
      hexBorder: "#ea580c",
      hexText: "#431407",
    };
  } else {
    return {
      score,
      level: "Mycket Hög",
      colorClass: "cell-red",
      pillClass: "red",
      hexBg: "#fca5a5",
      hexBorder: "#dc2626",
      hexText: "#450a0a",
    };
  }
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
