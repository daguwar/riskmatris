# Riskmatris Live

An open-source, interactive real-time web application for running group risk assessments — e.g. together with a PowerPoint presentation. A facilitator starts a session; participants scan a QR code or enter a session code and vote anonymously from their phones. Results appear live in a 4×4 risk matrix, and the facilitator locks each risk's placement and exports the summary.

End-user documentation — what the service stores, privacy notes, FAQ, self-hosting — lives in the app itself on the **`/about`** page. Keep it in sync when behavior changes.

> Code, comments, log messages and this README are in English. The UI is localized: Swedish (`static/i18n/sv.json`, the reference) and English (`en.json`), with a language selector in the top bar.

## Feature highlights

- **No accounts, no login.** Starting a session yields a unique session code (**8 characters** by default, configurable 6–16 → 40 bits of entropy), a **QR code** and a share link. Participants join instantly and vote fully anonymously — votes are tied to a random per-device client key, never to a name.
- **Step-by-step voting per risk (`#1`, `#2`, `#3` …):** **Probability (X axis, 1–4)** and **Consequence (Y axis, 1–4)**.
- **Automatic reveal at the vote threshold** (default `4`, configurable 1–50): the matrix stays hidden until enough votes have arrived, or until the facilitator clicks **"Visa resultat nu"** (reveal now). Additional votes update the matrix in real time. The threshold is never silently adjusted to the number of connected participants — if fewer people show up, the facilitator reveals manually.
- **4×4 risk matrix (Probability × Consequence = 1–16):** green 1–2 (low), yellow 3–6 (medium), orange 8–9 (high), red 12–16 (very high).
- **Calculated suggestion & summary matrix:** the presentation view shows the vote distribution per cell plus the calculated average (rounded up at `.5`, precautionary principle). The facilitator accepts the suggestion or clicks any cell after the discussion to lock that risk into the **summary matrix**.
- **Exports (admin view):**
  - **PNG** — high-resolution image of the summary matrix with all placed risks, ready to paste into PowerPoint.
  - **CSV (Excel)** — all risks with vote counts, averages, decided Probability/Consequence, risk score and risk level (`/api/sessions/{id}/export.csv?lang=sv|en`).
  - **Snapshot (JSON)** — export the whole session and re-import it later from the landing page ("Återuppta en sparad session"), optionally including previous votes.
- **Remote-controlled QR overlay:** show/hide a large QR code with the session link directly on the projector view — e.g. to let latecomers join mid-meeting. The state follows every connected presentation window.
- **Admin handover:** a one-time QR code / copyable link transfers admin rights to another device (e.g. laptop → phone). Single-use, expires after 5 minutes (configurable); the token is per session, so the original device stays admin too.
- **Localization & themes:** UI in Swedish and English, dark/light theme — both chosen in the top bar and remembered in the browser's local storage.
- **Lean UI by design:** long input hints sit behind small info ("i") popups instead of always-visible text; the About/FAQ/self-hosting texts live on `/about`, not on the landing page.
- **Accessible:** built to WCAG 2.1 AA — see below.

## Tech stack

- **Backend:** Python 3.12, [FastAPI](https://fastapi.tiangolo.com) + Uvicorn, SQLite (WAL mode) for session persistence, WebSockets for real-time state. Runtime dependencies are pinned in `requirements.txt`.
- **Frontend:** dependency-free vanilla ES modules (no build step, no framework) in `static/`. JS/CSS/JSON are referenced with a content-hash `?v=` parameter for cache busting; HTML pages are served `no-cache` so deploys never mix stale markup with cached scripts.
- **QR codes:** the [`qrcode`](https://pypi.org/project/qrcode/) package.

## How it works

- `riskmatris/__init__.py` builds the FastAPI app (middleware: cache headers, security headers, lifespan with DB load + periodic cleanup).
- `riskmatris/routes/api.py` — REST API: create/join sessions, QR code SVG, CSV export, snapshot export/import, `/health`.
- `riskmatris/routes/ws.py` + `ws_*.py` — WebSocket endpoint: one-time tickets, origin check, per-connection message rate limit; all session state changes are broadcast to the session's participants.
- `riskmatris/routes/spa.py` — serves the HTML pages: `index.html` for `/` and `/s/{session_code}`, `about.html` for `/about`, with asset versioning and the configured retention injected.
- `riskmatris/state.py` / `db.py` — session state lives in memory and is persisted to SQLite, so sessions survive a restart; a background task deletes sessions once their TTL has expired.
- Rate limiting is in-memory and per process, which fits the deployment model (a single container).

## Running the application

### 1. Locally, without Docker

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn riskmatris:app --host 0.0.0.0 --port 8000
```

Then open **http://localhost:8000**. (Opened via `localhost`, the QR code automatically points to the computer's local network IP, so phones on the same Wi-Fi can scan it.)

### Development in VS Code with Dev Containers

Open the project in VS Code → **Dev Containers: Reopen in Container**. The container installs `requirements-dev.txt` automatically (`postCreateCommand` in `.devcontainer/devcontainer.json`). Then, in the container's terminal:

```bash
uvicorn riskmatris:app --host 0.0.0.0 --port 8000 --reload
```

Port 8000 is forwarded automatically. Run the tests with `pytest -q` and audit the pinned runtime dependencies with `pip-audit -r requirements.txt`.

### 2. With Docker (local)

```bash
docker compose up --build -d
```

Available at **http://localhost:8000**. Sessions are stored in the Docker volume `riskmatris_data`, so they survive a restart; they are auto-deleted after 48 hours (`RISKMATRIS_TTL_HOURS`). The local compose file also enables the API docs (`RISKMATRIS_ENABLE_DOCS=1`) for debugging. A `/health` endpoint is used by the container healthcheck.

### 3. In the cloud (Render, Fly.io, Google Cloud Run, Azure App Service, …)

The project ships both a `Dockerfile` and `requirements.txt`, and listens on the `PORT` environment variable (default `8000`), so it can be deployed to any platform that builds from a Dockerfile or installs Python requirements — no changes needed.

### 4. On your own server behind an existing Traefik (HTTPS)

Run the app **without published ports** — Traefik routes traffic to the container over a shared Docker network (labels in `docker-compose.traefik.yml`):

```bash
cp .env.example .env    # fill in your values
docker compose -f docker-compose.traefik.yml up -d --build
```

`.env` keys: `RISKMATRIS_DOMAIN` (required), `RISKMATRIS_CONTAINER_NAME` (override to run a second/test instance in parallel), `TRAEFIK_NETWORK`, `TRAEFIK_ENTRYPOINT`, `TRAEFIK_CERT_RESOLVER`. WebSockets (`wss://`) work through Traefik without extra configuration. For local debugging on the server you can temporarily add `ports: - "127.0.0.1:8000:8000"` (localhost only).

> **Security note:** `FORWARDED_ALLOW_IPS=*` in `docker-compose.traefik.yml` is only safe because the container port is never published. If you ever expose port 8000 directly (don't in production), remove that variable — otherwise clients can spoof `X-Forwarded-For` and bypass the per-IP rate limits.

## Configuration

All settings are environment variables with safe defaults (invalid values log a warning and fall back — see `riskmatris/config.py`):

| Variable | Default | Description |
| --- | --- | --- |
| `PORT` | `8000` | Listen port (used by cloud platforms; the Docker image sets it) |
| `RISKMATRIS_DB_PATH` | `data/riskmatris.db` | SQLite database path (WAL mode) |
| `RISKMATRIS_TTL_HOURS` | `48` | Session retention; expired sessions are deleted automatically |
| `RISKMATRIS_CLEANUP_INTERVAL` | `3600` | Seconds between cleanup runs |
| `RISKMATRIS_SESSION_CODE_LENGTH` | `8` | Session code length, 6–16 (8 chars = 40 bits of entropy) |
| `RISKMATRIS_SESSION_CREATE_LIMIT` | `10` | Max sessions created per IP per hour |
| `RISKMATRIS_SESSION_READ_LIMIT` / `RISKMATRIS_SESSION_READ_WINDOW_SECONDS` | `300` / `60` | Per-IP rate limit on read endpoints keyed by session code (anti-enumeration) |
| `RISKMATRIS_WS_MAX_CONNECTIONS` | `200` | WebSocket connections per session |
| `RISKMATRIS_WS_MAX_CONNECTIONS_PER_IP` / `RISKMATRIS_WS_MAX_CONNECTIONS_TOTAL` | `20` / `1000` | WebSocket connection caps per client IP / globally |
| `RISKMATRIS_WS_MESSAGE_RATE_LIMIT` / `RISKMATRIS_WS_MESSAGE_RATE_WINDOW_SECONDS` | `120` / `60` | Max WS messages per connection per window |
| `RISKMATRIS_WS_MAX_MESSAGE_BYTES` | `8192` | Max WebSocket message size |
| `RISKMATRIS_MAX_RISKS_PER_SESSION` | `100` | Resource cap per session |
| `RISKMATRIS_MAX_VOTES_PER_RISK` | `500` | Resource cap per risk |
| `RISKMATRIS_MAX_SNAPSHOT_BYTES` | `1000000` | Max snapshot import size |
| `RISKMATRIS_ADMIN_HANDOVER_TTL_SECONDS` | `300` | Lifetime of single-use admin-handover links |
| `RISKMATRIS_SQLITE_BUSY_TIMEOUT_MS` | `5000` | SQLite lock wait before failing |
| `RISKMATRIS_ENABLE_DOCS` | `0` | `1` exposes `/docs`, `/redoc`, `/openapi.json` (enabled in the local compose file only) |
| `LOG_LEVEL` | `INFO` | Root log level |
| `RISKMATRIS_LOG_FORMAT` | `text` (`json` in Docker) | Human-readable or one JSON object per log line |

## Security

Secure by default (hardened in the 2026-11 security audit, SEC-01…SEC-07):

- Session codes are capabilities: 8 random chars, and all read endpoints keyed by the code are rate-limited per IP so the code space cannot be enumerated.
- WebSocket: `Origin` checked against the Host, one-time tickets for admin auth (30 s TTL), per-IP/per-session/global connection caps, per-connection message rate limit, no tokens in URLs.
- `secrets.compare_digest` for all token comparisons; user text sanitized on input and escaped on output; parameterized SQL only; CSV cells escaped against formula injection.
- Security headers (CSP, `nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options`) on every response; generic error messages to clients, details in logs; API docs disabled by default.
- Runtime dependencies pinned in `requirements.txt`; Docker base image pinned to an exact content digest; container runs as a non-root user; `pip-audit` runs in CI; Dependabot proposes updates for dependencies, Actions and the base-image digest.

## Accessibility & internationalization

- **WCAG 2.1 AA by default:** text contrast ≥ 4.5:1 in both themes; visible focus indicator (outline + ring) on all interactive elements; skip link; single `<main>`; logical heading order; all controls keyboard-operable (native buttons, Enter/Space); icon-only buttons have accessible names; dialogs use `role="dialog"` with focus moved in on open, Tab trapped, focus restored on close, Escape closes; `aria-live` on dynamic status; labeled forms. Verify with axe/Lighthouse on all views in both themes plus a keyboard-only walkthrough.
- **i18n:** UI dictionaries live in `static/i18n/sv.json` (reference) and `static/i18n/en.json` — keep them in parity. Static HTML uses `data-i18n*` attributes; dynamic JS uses `t("key", {param})` from `static/js/i18n.js`. The server sends error *codes* which the client translates (`server.*` keys); CSV export takes `?lang=sv|en`.

## Project structure

```
├── app.py                  # backward-compatible shim re-exporting riskmatris.* (tests import it)
├── riskmatris/             # the application package
│   ├── __init__.py         # FastAPI app, middleware, routers, static mount
│   ├── config.py           # env parsing, constants, limits
│   ├── routes/             # api.py (REST), ws.py (WebSocket), spa.py (HTML pages)
│   ├── db.py / state.py    # SQLite persistence / in-memory session state
│   ├── session.py / ws_*.py / handover.py / snapshot.py / rate_limit.py / i18n.py / ...
├── static/                 # frontend: index.html, about.html, app.js / js/*, css/*, i18n/*.json
├── tests/                  # pytest suite (API, WS, rate limit, handover, snapshot, SPA, ...)
├── Dockerfile              # base image pinned by digest, non-root user, /health healthcheck
├── docker-compose.yml      # local: publishes 8000, enables /docs
├── docker-compose.traefik.yml + .env.example   # server deployment behind Traefik (HTTPS)
├── .devcontainer/          # VS Code dev container (installs requirements-dev.txt)
├── AGENTS.md               # working conventions (read this first)
└── pyproject.toml          # ruff + pytest configuration
```

## Development workflow

See **AGENTS.md** for the full working conventions. In short:

- Before committing, run: `pytest -q`, `ruff check .`, `ruff format --check .` (CI runs `ruff check`, `pytest -q --timeout=120` and `pip-audit -r requirements.txt` on every push/PR to `master`). Frontend files are formatted with Prettier (`.prettierrc`).
- Small fixes go straight to `master`; scoped work goes on a `feature/<name>` branch + PR with `Closes #N`.
- Releases: annotated tag `vX.Y.Z` (`git tag -a`), push the tag, create a GitHub release from it. Before tagging, test on a second instance (separate clone with `RISKMATRIS_CONTAINER_NAME=riskmatris-test` in `.env`).

## Testing

The pytest suite in `tests/` (~230 tests) covers the REST API, WebSocket flow, rate limiting, admin handover, snapshot import/export, SPA serving & cache busting, config parsing, DB and utils:

```bash
pytest -q          # locally; CI adds --timeout=120 --timeout-method=thread
```

## License

Licensed under the **European Union Public Licence v. 1.2 (EUPL-1.2)** — see [LICENSE](LICENSE) for the full text (SPDX identifier: `EUPL-1.2`).

The EUPL is a copyleft open-source licence created and maintained by the European Commission, available in all official EU languages (all versions are equally authentic). In short: you may use, study, modify and distribute this software freely, but if you distribute it (or works based on it), you must do so under the same licence and provide access to the source code.
