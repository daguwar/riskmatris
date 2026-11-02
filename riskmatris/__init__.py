"""Riskmatris Live – FastAPI application package.

Usage:
    uvicorn riskmatris:app --host 0.0.0.0 --port 8000
"""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from riskmatris.config import SESSION_CLEANUP_INTERVAL, logger
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


app = FastAPI(title="Riskmatris Live", lifespan=lifespan)
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
    elif path == "/" or path.startswith("/s/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


# ---------------------------------------------------------------------------
# Mount routers & static files
# ---------------------------------------------------------------------------

app.include_router(api.router)
app.include_router(ws.router)
app.include_router(spa.router)

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
