"""Riskmatris Live – FastAPI application package.

Usage:
    uvicorn riskmatris:app --host 0.0.0.0 --port 8000
"""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from riskmatris.config import ENABLE_DOCS, SESSION_CLEANUP_INTERVAL, logger
from riskmatris.db import load_sessions_from_db_async
from riskmatris.routes import api, spa, ws
from riskmatris.state import AppState, default_state


async def _periodic_cleanup(state: AppState) -> None:
    """Background loop that removes expired sessions at regular intervals."""
    while True:
        await asyncio.sleep(SESSION_CLEANUP_INTERVAL)
        try:
            await state.cleanup_expired_sessions_async()
            state.cleanup_expired_ws_tickets()
            state.cleanup_expired_handover_tokens()
            state.cleanup_rate_limit_log()
        except Exception:
            logger.exception("Error during periodic session cleanup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from riskmatris.config import DB_PATH

    logger.info("Starting Riskmatris Live – loading sessions from DB (%s)", DB_PATH)
    state = getattr(app.state, "app_state", None)
    if state is None:
        state = default_state
        app.state.app_state = state

    loaded = await load_sessions_from_db_async()
    state.sessions.update(loaded)
    logger.info("Server ready. %d active sessions.", len(state.sessions))

    # Start background cleanup of expired sessions (hourly)
    cleanup_task = asyncio.create_task(_periodic_cleanup(state))
    logger.info("Periodic cleanup scheduled (interval: %d seconds).", SESSION_CLEANUP_INTERVAL)

    yield

    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    logger.info("Shutting down – sessions saved to DB.")


# Interactive API docs (/docs, /redoc, /openapi.json) are disabled unless
# explicitly enabled via RISKMATRIS_ENABLE_DOCS=1.
app = FastAPI(
    title="Riskmatris Live",
    lifespan=lifespan,
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url="/redoc" if ENABLE_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_DOCS else None,
)
# Ensure app.state.app_state is available even before lifespan runs (e.g. TestClient)
app.state.app_state = default_state


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    """Sets Cache-Control depending on the request path.

    Static files (CSS/JS): 1 day (content-based versioning via rebuild).
    SPA routes (HTML): no-cache (index.html must always be fetched fresh).
    API routes: no-store (default, sensitive data).
    """
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=86400"
    elif path == "/" or path == "/about" or path.startswith("/s/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


# ---------------------------------------------------------------------------
# Security headers – defense in depth on every response
# ---------------------------------------------------------------------------

SECURITY_HEADERS = {
    # CSP: no inline scripts (the frontend is pure ES modules); ws:/wss: for the
    # WebSocket; data: for the PNG export; 'unsafe-inline' for styles only (one
    # inline width attribute in index.html – styles cannot execute JS in modern
    # browsers). frame-ancestors 'none' blocks clickjacking. Also applies to the
    # QR endpoint's SVG responses, so a directly opened SVG cannot run scripts.
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self' ws: wss:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    # The session code sits in the URL – never let it leak via Referer
    "Referrer-Policy": "no-referrer",
    # Legacy complement to CSP frame-ancestors
    "X-Frame-Options": "DENY",
}


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Adds defense-in-depth security headers to every HTTP response (A05-3)."""
    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        response.headers[header] = value
    return response


# ---------------------------------------------------------------------------
# Mount routers & static files
# ---------------------------------------------------------------------------

app.include_router(api.router)
app.include_router(ws.router)
app.include_router(spa.router)

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
