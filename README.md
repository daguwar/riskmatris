# Riskmatris Live

An open, interactive real-time web application for running group risk assessments (e.g. together with a PowerPoint presentation).

> Note: all code, comments and log messages are in English. The user interface is in Swedish. Translations of the UI may be added in the future.

## Features

- **Open to everyone (no login):** The meeting leader starts a session and receives a unique session code (**8 characters**, configurable 6–16), a **QR code** and a share link. Participants scan the QR code with their phone and go straight into the voting view, fully anonymously.
- **Step-by-step voting per risk (`#1`, `#2`, `#3`...):**
  - **Probability (X axis, 1–4):** `1 – Osannolik` (unlikely), `2 – Möjlig` (possible), `3 – Sannolik` (likely), `4 – Mycket sannolik` (very likely).
  - **Consequence (Y axis, 1–4):** `1 – Försumbar` (negligible), `2 – Måttlig` (moderate), `3 – Allvarlig` (serious), `4 – Mycket allvarlig` (very serious).
- **Automatic reveal at the vote threshold:** Results stay hidden until the configured number of responses has arrived (default: `4`), or until the meeting leader clicks **"Visa resultat nu"** (reveal results now). If more responses arrive afterwards, the matrix updates in real time. The threshold is never adjusted to the number of currently connected participants – if fewer participants show up, the leader reveals manually.
- **4×4 risk matrix (Probability × Consequence = 1–16):**
  - **Green (1–2):** Low risk
  - **Yellow (3–6):** Medium risk
  - **Orange (8–9):** High risk
  - **Red (12–16):** Very high risk
- **Calculated suggestion & summary matrix:**
  - Shows both the vote distribution (number of votes per cell) and the calculated average (rounded up at `.5` per the precautionary principle).
  - The meeting leader can accept the suggestion or click any cell in the matrix after discussion to lock the placement of `#1`, `#2` etc. into the **summary matrix**.
- **Export to PowerPoint & Excel:**
  - **PNG image:** Download a high-resolution image of the summary matrix with all placed risks (`#1`, `#2`...) ready to paste into PowerPoint.
  - **CSV (Excel):** Export a table with all risks, vote counts, averages, decided Probability/Consequence, risk score and risk level.
- **Remote-controlled QR overlay:** From the admin view the leader can show/hide a large QR code with the session link directly on the projector view – e.g. to let latecomers join mid-meeting. The state follows every connected presentation window.
- **Admin handover:** The admin view can show a one-time QR code / copyable link that transfers admin rights to another device (e.g. from laptop to phone). The link is single-use and expires after 5 minutes; the original device stays admin too (the token is per session, not per device).

---

## Running the application

### 1. Running locally (manually, without Docker)

Create a Python virtual environment, install the dependencies and start the server in your terminal:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn riskmatris:app --host 0.0.0.0 --port 8000
```

Then open **http://localhost:8000** in your browser.
*(If you open it via `localhost`, the QR code automatically points to the computer's local network IP so that participants on the same Wi-Fi can scan it with their phones.)*

### Development in VS Code with Dev Containers

Open the project in VS Code and choose **Dev Containers: Reopen in Container** from the command palette. Once the container has been created, the dependencies from `requirements-dev.txt` are installed automatically. Then start the app in the container's terminal:

```bash
uvicorn riskmatris:app --host 0.0.0.0 --port 8000 --reload
```

Port 8000 is forwarded automatically. Run the tests with `pytest`.

Check the pinned runtime dependencies for known vulnerabilities:

```bash
pip-audit -r requirements.txt
```

### 2. Running with Docker

```bash
docker compose up --build -d
```

The application is then available at **http://localhost:8000** and stores ongoing sessions in a Docker volume (`riskmatris_data`) so they survive a restart. Sessions are cleaned up automatically after 48 hours (configurable via the `RISKMATRIS_TTL_HOURS` environment variable).

### 3. Running in the cloud (Render, Fly.io, Google Cloud Run, Azure App Service)

Since the project has both a `Dockerfile` and `requirements.txt`, and listens to the `PORT` environment variable, you can upload the project directly to any cloud service without changes.

### 4. Running on your own server behind an existing Traefik (HTTPS)

If you have a server where Traefik already handles HTTPS and certificates, run the app **without published ports** – Traefik routes traffic to the container via a shared Docker network (labels on the container, see `docker-compose.traefik.yml`):

```bash
cp .env.example .env    # fill in your values
docker compose -f docker-compose.traefik.yml up -d --build
```

Fill in `.env`:

- `RISKMATRIS_DOMAIN` – the domain Traefik should respond on (required), e.g. `riskmatris.example.com`
- `RISKMATRIS_TTL_HOURS` – session retention in hours (default: `48`)
- `RISKMATRIS_SESSION_READ_LIMIT` / `RISKMATRIS_SESSION_READ_WINDOW_SECONDS` – per-IP rate limit on read endpoints keyed by session code, in requests per window (defaults: `300` per `60` seconds); protects against enumeration of session codes
- `RISKMATRIS_SESSION_CODE_LENGTH` – length of generated session codes, 6–16 (default: `8` = 40 bits of entropy)
- `RISKMATRIS_WS_MAX_CONNECTIONS_PER_IP` / `RISKMATRIS_WS_MAX_CONNECTIONS_TOTAL` – WebSocket connection caps per client IP / globally (defaults: `20` / `1000`)
- `RISKMATRIS_WS_MESSAGE_RATE_LIMIT` / `RISKMATRIS_WS_MESSAGE_RATE_WINDOW_SECONDS` – max WS messages per connection per window (defaults: `120` per `60` seconds)
- `RISKMATRIS_ENABLE_DOCS` – set to `1` to expose the interactive API docs (`/docs`, `/redoc`, `/openapi.json`); disabled by default, enabled only in the local `docker-compose.yml`
- `RISKMATRIS_SQLITE_BUSY_TIMEOUT_MS` – how long SQLite waits for a lock before failing (default: `5000` ms); the database runs in WAL mode
- `TRAEFIK_NETWORK` – the name of the Docker network your Traefik runs on (usually `traefik-public`; the network must already exist)
- `TRAEFIK_ENTRYPOINT` / `TRAEFIK_CERT_RESOLVER` – names of the entrypoint and certificate resolver (defaults: `websecure` / `letsencrypt`)

Other optional settings (see `riskmatris/config.py` for the full list):

- `LOG_LEVEL` – log level (default: `INFO`)
- `RISKMATRIS_LOG_FORMAT` – `text` (human-readable, default locally) or `json` (one JSON object per line; default in the Docker image)
- `RISKMATRIS_DB_PATH` – SQLite database path (default: `data/riskmatris.db`)
- `RISKMATRIS_SESSION_CREATE_LIMIT` – max sessions created per IP per hour (default: `10`)
- `RISKMATRIS_CLEANUP_INTERVAL` – seconds between automatic session cleanups (default: `3600`)
- `RISKMATRIS_WS_MAX_CONNECTIONS` – WebSocket connections per session (default: `200`)
- `RISKMATRIS_WS_MAX_MESSAGE_BYTES` – max WebSocket message size (default: `8192`)

Open the app via your domain (`https://riskmatris.example.com`). The share link and QR code then point to the right address automatically, and WebSockets (`wss://`) work through Traefik without extra configuration. For local debugging on the server you can add `ports: - "127.0.0.1:8000:8000"` to the compose file (binding to localhost only).

**Security note:** `FORWARDED_ALLOW_IPS=*` in `docker-compose.traefik.yml` is only safe because the container port is never published to untrusted networks. If you ever expose port 8000 directly (do not do this in production), remove that variable or clients can spoof `X-Forwarded-For` and bypass the per-IP rate limits.

---

## Development & CI

Every push/PR to `master` runs CI (`.github/workflows/ci.yml`): `ruff` lint, the full `pytest` suite, and `pip-audit` against known dependency vulnerabilities. The Docker base image is pinned to an exact content digest in the `Dockerfile`, and Dependabot (`.github/dependabot.yml`) automatically proposes updates for Python dependencies, GitHub Actions and the base image digest.

---

## License

Licensed under the **European Union Public Licence v. 1.2 (EUPL-1.2)** – see [LICENSE](LICENSE) for the full text (SPDX identifier: `EUPL-1.2`).

The EUPL is a copyleft open-source licence created and maintained by the European Commission, available in all official EU languages (all versions are equally authentic). In short: you may use, study, modify and distribute this software freely, but if you distribute it (or works based on it), you must do so under the same licence and provide access to the source code.
