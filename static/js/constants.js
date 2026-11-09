import { t } from "./i18n.js";

/**
 * Label constants for Probability and Consequence.
 */

export function probLabel(n) {
  return t(`vote.prob${n}.short`);
}

export function consLabel(n) {
  return t(`vote.cons${n}.short`);
}

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

