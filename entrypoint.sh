#!/bin/sh
set -e

# Directory where the SQLite database lives (mounted as a volume in Docker)
DB_DIR="$(dirname "${RISKMATRIS_DB_PATH:-/app/data/riskmatris.db}")"

# Ensure the directory exists and is owned by appuser (uid 1000).
# This also repairs older volumes where the directory or db file is owned by
# root, which otherwise causes the error "attempt to write a readonly database".
mkdir -p "$DB_DIR"
chown -R appuser:appuser "$DB_DIR"

# Switch to the non-root user and run the main command (e.g. uvicorn)
exec setpriv --reuid=1000 --regid=1000 --clear-groups "$@"
