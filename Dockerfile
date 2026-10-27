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

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]

