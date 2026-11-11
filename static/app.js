/**
 * Riskmatris Live – Main Application Entry Point (ES Module).
 */

import { initDom } from "./js/dom.js";
import { bindInfoPopups, bindLandingEvents, bindSessionEvents, consumeHandoverToken, enterSession, probeRecentSessions, renderRecentSessions } from "./js/events.js";
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
  // Validate recent sessions against the server once, then re-render the
  // countdown locally every minute (expired entries drop out automatically)
  probeRecentSessions();
  setInterval(renderRecentSessions, 60_000);
  // Re-render dynamic content when the language changes
  window.addEventListener("langchange", () => {
    if (state.sessionState) handleSessionState(state.sessionState);
    renderRecentSessions();
  });

  const pathMatch = window.location.pathname.match(/^\/s\/([A-Za-z0-9]+)/);
  if (pathMatch) {
    if (new URLSearchParams(window.location.search).get("view") === "present") {
      state.pendingInitialView = "presentView";
      state.presentOnly = true; // projector window: no way to switch to admin/vote views
    }
    const sid = pathMatch[1].toUpperCase();
    await consumeHandoverToken(sid); // stores admin token if ?handover= is present
    enterSession(sid);
  }
}

document.addEventListener("DOMContentLoaded", init);
