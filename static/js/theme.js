/**
 * Theme (dark/light) handling. The initial theme is applied by theme-init.js
 * before first paint; this module handles the toggle and system changes.
 */

import { dom } from "./dom.js";

const THEME_KEY = "riskmatris_theme";

export function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  if (dom.btnThemeToggle) {
    dom.btnThemeToggle.textContent = theme === "dark" ? "☀️" : "🌙";
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
