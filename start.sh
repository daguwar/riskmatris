#!/usr/bin/env bash
set -euo pipefail

echo "==================================================="
echo "  Riskmatris Live - Startar lokal webbserver"
echo "==================================================="

cd "$(dirname "$0")"

# Hitta venv-Python – layouten skiljer sig mellan Windows (.venv/Scripts/python.exe)
# och macOS/Linux (.venv/bin/python). Samma repo kan delas mellan Git Bash och WSL,
# sa båda varianterna accepteras. "activate" används inte: Windows-venv:ns
# activate-skript innehåller cygpath och backslash-sökvägar som inte fungerar i WSL.
if [ -f ".venv/bin/python" ]; then
    PY=".venv/bin/python"
elif [ -f ".venv/Scripts/python.exe" ]; then
    PY=".venv/Scripts/python.exe"
else
    echo "Skapar virtuell Python-miljo (.venv)..."
    if command -v python3 >/dev/null 2>&1; then
        python3 -m venv .venv
    else
        python -m venv .venv
    fi
    if [ -f ".venv/bin/python" ]; then
        PY=".venv/bin/python"
    else
        PY=".venv/Scripts/python.exe"
    fi
fi

echo "Anvander Python: $PY"

echo "Installerar/kontrollerar beroenden..."
"$PY" -m pip install -q -r requirements.txt

echo ""
echo "Startar Riskmatris Live pa http://localhost:8000"
echo "Tryck Ctrl+C for att stoppa servern."
echo ""
# exec: uvicorn ersätter bash direkt – signaler (Ctrl+C) når uvicorn direkt.
exec "$PY" -m uvicorn app:app --host 0.0.0.0 --port 8000
