/**
 * Riskmatris Live – Main Application Entry Point (ES Module).
 */

import { initDom } from "./js/dom.js";
import { bindLandingEvents, bindSessionEvents, consumeHandoverToken, enterSession, renderRecentSessions } from "./js/events.js";
import { state } from "./js/state.js";
import { initTheme } from "./js/theme.js";

async function init() {
  initDom();
  initTheme();
  bindLandingEvents();
  bindSessionEvents();
  renderRecentSessions();

  const pathMatch = window.location.pathname.match(/^\/s\/([A-Za-z0-9]+)/);
  if (pathMatch) {
    if (new URLSearchParams(window.location.search).get("view") === "present") {
      state.pendingInitialView = "presentView";
    }
    const sid = pathMatch[1].toUpperCase();
    await consumeHandoverToken(sid); // stores admin token if ?handover= is present
    enterSession(sid);
  }
}

document.addEventListener("DOMContentLoaded", init);
