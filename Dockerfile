# Base image pinned to an exact content digest (sakerhetsrapport A08-1), not
# just a tag: a tag can be moved to different content, a digest cannot.
# Dependabot (.github/dependabot.yml) proposes updates of this digest.
# Current: python:3.12-slim manifest list, resolved 2026-11-04.
FROM python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30

WORKDIR /app

# Create a directory for the SQLite database so it can be mounted as a volume
RUN mkdir -p /app/data
ENV RISKMATRIS_DB_PATH=/app/data/riskmatris.db
ENV RISKMATRIS_LOG_FORMAT=json
ENV PORT=8000

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The backend lives in the riskmatris/ package (fas 1); app.py is only a
# backward-compatible shim, so the package itself must be copied too.
COPY riskmatris/ ./riskmatris/
COPY app.py .
COPY log_config.json .
COPY static/ ./static/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create a non-root user for security. The entrypoint runs as root,
# fixes ownership of the data directory and then switches to appuser.
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["sh", "-c", "uvicorn riskmatris:app --host 0.0.0.0 --port ${PORT:-8000} --log-config /app/log_config.json"]

