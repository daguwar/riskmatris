/**
 * Theme (dark/light) handling. The initial theme is applied by theme-init.js
 * before first paint; this module handles the toggle and system changes.
 */

import { dom } from "./dom.js";

const THEME_KEY = "riskmatris_theme";

// Inline SVG icons (crisply centered, unlike emoji whose glyph box sits low)
const ICONS = {
  dark: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
  light:
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/></svg>',
};

export function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  if (dom.btnThemeToggle) {
    dom.btnThemeToggle.innerHTML = ICONS[theme] || ICONS.light;
    dom.btnThemeToggle.title = theme === "dark" ? "Växla till ljust tema" : "Växla till mörkt tema";
    dom.btnThemeToggle.setAttribute("aria-label", dom.btnThemeToggle.title);
  }
}

export function initTheme() {
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  const saved = localStorage.getItem(THEME_KEY);
  applyTheme(saved || (media.matches ? "dark" : "light"));

  dom.btnThemeToggle.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch (_) {}
    applyTheme(next);
  });

  // Follow the OS theme only while the user hasn't chosen explicitly
  media.addEventListener("change", (e) => {
    if (!localStorage.getItem(THEME_KEY)) {
      applyTheme(e.matches ? "dark" : "light");
    }
  });
}
