# Riskmatris Live

An open, interactive real-time web application for running group risk assessments (e.g. together with a PowerPoint presentation).

> Note: all code, comments and log messages are in English. The user interface is in Swedish. Translations of the UI may be added in the future.

## Features

- **Open to everyone (no login):** The meeting leader starts a session and receives a unique 6-character session ID, a **QR code** and a share link. Participants scan the QR code with their phone and go straight into the voting view, fully anonymously.
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

---

## Running the application

### 1. Running locally (manually, without Docker)

Create a Python virtual environment, install the dependencies and start the server in your terminal:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

Then open **http://localhost:8000** in your browser.
*(If you open it via `localhost`, the QR code automatically points to the computer's local network IP so that participants on the same Wi-Fi can scan it with their phones.)*

### Development in VS Code with Dev Containers

Open the project in VS Code and choose **Dev Containers: Reopen in Container** from the command palette. Once the container has been created, the dependencies from `requirements-dev.txt` are installed automatically. Then start the app in the container's terminal:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Port 8000 is forwarded automatically. Run the tests with `pytest`.

Check the pinned runtime dependencies for known vulnerabilities (see `TODO_SECURITY.md` for the security decisions):

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
- `TRAEFIK_NETWORK` – the name of the Docker network your Traefik runs on (usually `traefik-public`; the network must already exist)
- `TRAEFIK_ENTRYPOINT` / `TRAEFIK_CERT_RESOLVER` – names of the entrypoint and certificate resolver (defaults: `websecure` / `letsencrypt`)

Open the app via your domain (`https://riskmatris.example.com`). The share link and QR code then point to the right address automatically, and WebSockets (`wss://`) work through Traefik without extra configuration. For local debugging on the server you can add `ports: - "127.0.0.1:8000:8000"` to the compose file (binding to localhost only).
