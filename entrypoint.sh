#!/bin/sh
set -e

# Katalog där SQLite-databasen ligger (monteras som volym i Docker)
DB_DIR="$(dirname "${RISKMATRIS_DB_PATH:-/app/data/riskmatris.db}")"

# Säkerställ att katalogen finns och ägs av appuser (uid 1000).
# Detta reparerar även äldre volymer där katalogen eller db-filen ägs av root,
# vilket annars ger felmeddelandet "attempt to write a readonly database".
mkdir -p "$DB_DIR"
chown -R appuser:appuser "$DB_DIR"

# Växla till icke-root-användaren och kör huvudkommandot (t.ex. uvicorn)
exec setpriv --reuid=1000 --regid=1000 --clear-groups "$@"
