/**
 * Riskmatris Live – Main Application Entry Point (ES Module).
 */

import { initDom } from "./js/dom.js";
import { bindInfoPopups, bindLandingEvents, bindSessionEvents, consumeHandoverToken, enterSession, renderRecentSessions } from "./js/events.js";
import { initI18n } from "./js/i18n.js";
import { state } from "./js/state.js";
import { initTheme } from "./js/theme.js";
import { handleSessionState } from "./js/views.js";

async function init() {
  await initI18n();
  initDom();
  initTheme();
  bindLandingEvents();
  bindSessionEvents();
  bindInfoPopups();
  renderRecentSessions();
  // Re-render dynamic content when the language changes
  window.addEventListener("langchange", () => {
    if (state.sessionState) handleSessionState(state.sessionState);
    renderRecentSessions();
  });

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
