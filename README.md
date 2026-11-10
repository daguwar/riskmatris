# Riskmatris Live

Riskmatris Live is a real-time web application for collaborative 4×4 risk assessments. A facilitator creates a session, participants join anonymously via QR code or session code from mobile or desktop browsers, and votes are aggregated live on an interactive risk matrix. Results can be locked and exported as PNG images, CSV spreadsheets, or JSON snapshots.

## Features

- **Anonymous participation:** No user accounts or registrations. Sessions generate an 8-character code, a join link, and a QR code. Participant votes are associated with a random device identifier.
- **Interactive 4×4 risk matrix:**
  - **Probability (X-axis, 1–4):** Unlikely (1), Possible (2), Likely (3), Highly likely (4).
  - **Consequence (Y-axis, 1–4):** Negligible (1), Moderate (2), Serious (3), Critical (4).
  - **Risk score (1–16):** Low (Green, 1–2), Medium (Yellow, 3–6), High (Orange, 8–9), Very High (Red, 12–16).
- **Facilitator controls:**
  - Configurable vote reveal threshold (default: 4 votes). Votes remain hidden until the threshold is met or the facilitator manually triggers a reveal.
  - Calculated consensus recommendations based on the arithmetic mean, rounded up at `.5` (precautionary principle).
  - Manual override to adjust and lock a risk's final cell position after group discussion.
  - Projector mode with a toggleable full-screen QR code for late arrivals.
  - Secure admin handover via single-use QR code or link with a 5-minute expiry.
- **Export options:**
  - **PNG:** High-resolution rendering of the complete summary matrix.
  - **CSV:** Tabular export containing risk descriptions, vote counts, averages, final coordinates, and risk levels (`/api/sessions/{session_id}/export.csv?lang=sv|en`).
  - **JSON Snapshot:** Export and restore full session states directly from the landing page.
- **Localization & accessibility:**
  - Full UI localization in Swedish (`sv`) and English (`en`), plus light/dark theme toggle.
  - Built to WCAG 2.1 AA standards (high-contrast ratios, complete keyboard navigation, ARIA live regions, and modal focus traps).

## Tech Stack

- **Backend:** Python 3.12, [FastAPI](https://fastapi.tiangolo.com), Uvicorn, SQLite (WAL mode), WebSockets.
- **Frontend:** Vanilla JavaScript (ES modules), HTML5, CSS3. No compilation or client-side build pipeline required. Static assets are cache-busted with content hashes.
- **QR Code Generation:** [`qrcode`](https://pypi.org/project/qrcode/).

## Project Structure

```
├── app.py                      # Compatibility entrypoint
├── riskmatris/                 # Application backend package
│   ├── __init__.py             # FastAPI factory, middleware, and lifespan handlers
│   ├── config.py               # Settings, validation, and environment defaults
│   ├── db.py                   # SQLite database initialization and queries
│   ├── state.py                # In-memory session state management
│   ├── routes/
│   │   ├── api.py              # REST API endpoints (sessions, exports, health)
│   │   ├── ws.py               # WebSocket endpoint and connection dispatching
│   │   └── spa.py              # Single Page Application routing and HTML serving
├── static/                     # Frontend client assets
│   ├── index.html              # Main application markup
│   ├── about.html              # Information and privacy page
│   ├── css/                    # Stylesheets (tokens, layout, matrix, themes)
│   ├── js/                     # Client JavaScript modules
│   └── i18n/                   # Translation files (sv.json, en.json)
├── tests/                      # Pytest suite
├── Dockerfile                  # Production container definition
├── docker-compose.yml          # Local container environment
├── docker-compose.traefik.yml  # Reverse proxy deployment setup
└── AGENTS.md                   # Development conventions and guidelines
```

## Getting Started

### Local Development (Python)

Prerequisites: Python 3.12+

```bash
# Create and activate a virtual environment
python -m venv .venv

# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements-dev.txt

# Start development server
uvicorn riskmatris:app --host 0.0.0.0 --port 8000 --reload
```

Navigate to `http://localhost:8000`. When accessed locally, generated QR codes automatically resolve to your local network IP to allow mobile devices on the same Wi-Fi network to connect.

### VS Code Dev Containers

This repository includes a `.devcontainer` configuration. Open the directory in VS Code and select **Dev Containers: Reopen in Container** to initialize the environment with all development dependencies pre-installed.

### Docker (Local)

Run with Docker Compose:

```bash
docker compose up --build -d
```

The application will be available at `http://localhost:8000`. Sessions persist in the `riskmatris_data` volume and interactive API documentation is enabled at `http://localhost:8000/docs`.

### Production Deployment (Traefik)

To deploy behind an existing Traefik reverse proxy handling TLS:

```bash
cp .env.example .env
# Edit .env with your domain and network configuration
docker compose -f docker-compose.traefik.yml up -d --build
```

In this mode, the container does not expose host ports directly; traffic is routed entirely via the shared Docker network.

## Configuration

Settings are configured using environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `PORT` | `8000` | HTTP port for the web server |
| `RISKMATRIS_DB_PATH` | `data/riskmatris.db` | Path to the SQLite database file |
| `RISKMATRIS_TTL_HOURS` | `48` | Session retention period in hours |
| `RISKMATRIS_CLEANUP_INTERVAL` | `3600` | Frequency of expired session cleanup in seconds |
| `RISKMATRIS_SESSION_CODE_LENGTH` | `8` | Length of generated session codes (6–16 characters) |
| `RISKMATRIS_SESSION_CREATE_LIMIT` | `10` | Max sessions created per IP per hour |
| `RISKMATRIS_SESSION_READ_LIMIT` | `300` | Max requests per IP to read-only endpoints per window |
| `RISKMATRIS_SESSION_READ_WINDOW_SECONDS` | `60` | Time window in seconds for read rate limiting |
| `RISKMATRIS_WS_MAX_CONNECTIONS` | `200` | Maximum simultaneous WebSocket connections per session |
| `RISKMATRIS_WS_MAX_CONNECTIONS_PER_IP` | `20` | Maximum simultaneous WebSocket connections per IP address |
| `RISKMATRIS_WS_MAX_CONNECTIONS_TOTAL` | `1000` | Global limit for concurrent WebSocket connections |
| `RISKMATRIS_WS_MESSAGE_RATE_LIMIT` | `120` | Max WebSocket messages per connection per window |
| `RISKMATRIS_WS_MESSAGE_RATE_WINDOW_SECONDS` | `60` | Time window in seconds for WebSocket message throttling |
| `RISKMATRIS_WS_MAX_MESSAGE_BYTES` | `8192` | Maximum allowable WebSocket payload size in bytes |
| `RISKMATRIS_MAX_RISKS_PER_SESSION` | `100` | Maximum number of risks allowed per session |
| `RISKMATRIS_MAX_VOTES_PER_RISK` | `500` | Maximum number of recorded votes allowed per risk |
| `RISKMATRIS_MAX_SNAPSHOT_BYTES` | `1000000` | Maximum payload size in bytes for JSON snapshot imports |
| `RISKMATRIS_ADMIN_HANDOVER_TTL_SECONDS` | `300` | Validity duration of admin handover tokens in seconds |
| `RISKMATRIS_SQLITE_BUSY_TIMEOUT_MS` | `5000` | SQLite lock wait timeout in milliseconds |
| `RISKMATRIS_ENABLE_DOCS` | `0` | Set to `1` to enable `/docs` and `/openapi.json` |
| `LOG_LEVEL` | `INFO` | Application log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `RISKMATRIS_LOG_FORMAT` | `text` (`json` in Docker) | Log output format (`text` or `json`) |

## Security

- **Anti-enumeration:** Session read endpoints and connection tickets are rate-limited per IP.
- **WebSocket protection:** Origin validation against Host header, one-time tickets for admin authorization (30s TTL), payload size constraints, and connection limits per IP/session/host.
- **Input hygiene:** Text input is sanitized, SQL queries use parameterized statements, and CSV exports escape spreadsheet formula triggers (`=`, `+`, `-`, `@`).
- **Cryptographic verification:** Token validation uses constant-time string comparisons (`secrets.compare_digest`).
- **Defensive HTTP headers:** Responses include strict Content Security Policy (CSP), `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and `X-Frame-Options: DENY`.
- **Hardened container:** The container runs as an unprivileged user (`appuser`) with a digest-pinned base image.

## Testing & Quality

Run the test suite and linters:

```bash
# Run tests
pytest -q

# Run linters and formatting checks
ruff check .
ruff format --check .
```

## License

This project is licensed under the **European Union Public Licence v. 1.2 (EUPL-1.2)**. See the [LICENSE](LICENSE) file for details.
