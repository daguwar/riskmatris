FROM python:3.12-slim

WORKDIR /app

# Skapa en katalog för SQLite-databasen så den kan monteras som en volym
RUN mkdir -p /app/data
ENV RISKMATRIS_DB_PATH=/app/data/riskmatris.db
ENV PORT=8000

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY static/ ./static/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Skapa en icke-root-användare för säkerhet. Entrypoint kör som root,
# rättar ägarskap på data-katalogen och växlar sedan till appuser.
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]

