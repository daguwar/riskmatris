@echo off
chcp 65001 >nul
echo ===================================================
echo   Riskmatris Live - Startar lokal webbserver
echo ===================================================

if not exist ".venv" (
    echo Skapar virtuell Python-miljo (.venv)...
    python -m venv .venv
)

echo Installerar/kontrollerar beroenden...
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt

echo.
echo Startar Riskmatris Live pa http://localhost:8000
echo Tryck Ctrl+C for att stoppa servern.
echo.
uvicorn app:app --host 0.0.0.0 --port 8000
pause

