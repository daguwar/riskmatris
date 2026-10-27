#!/usr/bin/env bash
set -euo pipefail

echo "==================================================="
echo "  Riskmatris Live - Startar lokal webbserver"
echo "==================================================="

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "Skapar virtuell Python-miljo (.venv)..."
    python3 -m venv .venv
fi

echo "Installerar/kontrollerar beroenden..."
source .venv/bin/activate
pip install -q -r requirements.txt

echo ""
echo "Startar Riskmatris Live pa http://localhost:8000"
echo "Tryck Ctrl+C for att stoppa servern."
echo ""
uvicorn app:app --host 0.0.0.0 --port 8000
