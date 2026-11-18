import { t } from "./i18n.js";

/**
 * Label constants for Probability and Consequence, per matrix size.
 * Size 4 keeps the classic vote.probN / vote.consN keys; sizes 3 and 5 use
 * vote.p<size>.<n> / vote.c<size>.<n> (short label on the button, full text
 * for the aria-label). All wordings follow common Swedish/English risk-matrix
 * scales (MSB-style for 5x5, low/medium/high for 3x3).
 */

export function probLabel(n, size = 4) {
  return t(size === 4 ? `vote.prob${n}.short` : `vote.p${size}.${n}.short`);
}

export function consLabel(n, size = 4) {
  return t(size === 4 ? `vote.cons${n}.short` : `vote.c${size}.${n}.short`);
}

export function probLabelFull(n, size = 4) {
  return t(size === 4 ? `vote.prob${n}.full` : `vote.p${size}.${n}.full`);
}

export function consLabelFull(n, size = 4) {
  return t(size === 4 ? `vote.cons${n}.full` : `vote.c${size}.${n}.full`);
}

export function probLabelKey(n, size = 4) {
  return size === 4 ? `vote.prob${n}.short` : `vote.p${size}.${n}.short`;
}

export function consLabelKey(n, size = 4) {
  return size === 4 ? `vote.cons${n}.short` : `vote.c${size}.${n}.short`;
}

export function probLabelFullKey(n, size = 4) {
  return size === 4 ? `vote.prob${n}.full` : `vote.p${size}.${n}.full`;
}

export function consLabelFullKey(n, size = 4) {
  return size === 4 ? `vote.cons${n}.full` : `vote.c${size}.${n}.full`;
}

/**
 * Risk-level thresholds per matrix size – mirror of the server's
 * utils.LEVEL_THRESHOLDS: [greenMax, yellowMax, orangeMax]; above orangeMax
 * is red ("Very high"). Score = probability x consequence (1..size^2).
 */
export const LEVEL_THRESHOLDS = {
  3: [2, 4, 6], // score 1..9
  4: [2, 6, 9], // score 1..16 (unchanged default)
  5: [4, 9, 15], // score 1..25
};

/**
 * Presentation mapping for risk colors (color name -> CSS classes / hex values
 * for canvas export). The color itself is decided server-side and arrives in
 * the session payload's cell_meta – this table only maps it to styling.
 */
export const COLOR_STYLES = {
  green: { colorClass: "cell-green", pillClass: "green", hexBg: "#86efac", hexBorder: "#16a34a", hexText: "#064e3b" },
  yellow: {
    colorClass: "cell-yellow",
    pillClass: "yellow",
    hexBg: "#fde047",
    hexBorder: "#ca8a04",
    hexText: "#422006",
  },
  orange: {
    colorClass: "cell-orange",
    pillClass: "orange",
    hexBg: "#fdba74",
    hexBorder: "#ea580c",
    hexText: "#431407",
  },
  red: { colorClass: "cell-red", pillClass: "red", hexBg: "#fca5a5", hexBorder: "#dc2626", hexText: "#450a0a" },
};

