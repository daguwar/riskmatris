"""SPA catch-all routes and static asset serving."""

import hashlib
import os
from functools import cache

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import riskmatris.config as config

router = APIRouter()


@cache
def get_static_version() -> str:
    """Returns a content hash of the frontend assets, used for cache busting.

    index.html is always served fresh (no-cache), while app.js/styles.css are
    cached for a day. Referencing them with a content-based version parameter
    guarantees that clients pick up new code immediately after a deploy
    instead of mixing a stale script with fresh markup.
    """
    hasher = hashlib.sha256()
    for name in ("app.js", "styles.css"):
        with open(os.path.join("static", name), "rb") as f:
            hasher.update(f.read())
    return hasher.hexdigest()[:12]


@router.get("/", response_class=HTMLResponse)
@router.get("/s/{session_id}", response_class=HTMLResponse)
async def serve_spa(request: Request, session_id: str | None = None):
    with open(os.path.join("static", "index.html"), encoding="utf-8") as f:
        html = f.read()
    version = get_static_version()
    html = html.replace('"/static/styles.css"', f'"/static/styles.css?v={version}"')
    html = html.replace('"/static/app.js"', f'"/static/app.js?v={version}"')
    # Inject the configured session retention into the info text so it always
    # matches what the server actually enforces
    ttl_hours = getattr(config, "SESSION_TTL_HOURS", 48)
    html = html.replace("__TTL_HOURS__", str(ttl_hours))
    return HTMLResponse(content=html)
