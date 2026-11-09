"""SPA catch-all routes and static asset serving."""

import hashlib
import os
import re
from functools import cache

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import riskmatris.config as config

router = APIRouter()


@cache
def get_static_version() -> str:
    """Returns a content hash of all frontend assets (JS/CSS), used for cache busting.

    index.html is always served fresh (no-cache), while the JS/CSS files under
    static/ are cached for a day. Referencing them with a content-based version
    parameter guarantees that clients pick up new code immediately after a deploy
    instead of mixing a stale script with fresh markup.
    """
    hasher = hashlib.sha256()
    for root, _, files in sorted(os.walk("static")):
        for name in sorted(files):
            if name.endswith((".js", ".css", ".json")):
                file_path = os.path.join(root, name)
                with open(file_path, "rb") as f:
                    hasher.update(f.read())
    return hasher.hexdigest()[:12]


@router.get("/", response_class=HTMLResponse)
@router.get("/s/{session_id}", response_class=HTMLResponse)
async def serve_spa(request: Request, session_id: str | None = None):
    with open(os.path.join("static", "index.html"), encoding="utf-8") as f:
        html = f.read()
    version = get_static_version()
    # Append the content hash to every versioned static asset reference
    # (stylesheets under static/css/ and the JS entry point).
    html = re.sub(
        r'((?:href|src)="/static/[^"]+\.(?:css|js))"',
        rf'\1?v={version}"',
        html,
    )
    # Inject the configured session retention into the info text so it always
    # matches what the server actually enforces
    ttl_hours = getattr(config, "SESSION_TTL_HOURS", 48)
    html = html.replace("__TTL_HOURS__", str(ttl_hours))
    return HTMLResponse(content=html)
