/**
 * Entry point for standalone pages (e.g. /about) that need the shared chrome
 * (i18n, theme toggle) but not the session logic from app.js.
 */

import { initDom } from "./dom.js";
import { initI18n } from "./i18n.js";
import { initTheme } from "./theme.js";

async function init() {
  await initI18n();
  initDom();
  initTheme();
}

document.addEventListener("DOMContentLoaded", init);
