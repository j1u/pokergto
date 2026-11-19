@echo off
REM PokerGTO local - one-time setup + start (backend :8000, frontend :5173)
cd /d %~dp0
if not exist backend\.venv (
  echo Creating Python venv...
  python -m venv backend\.venv
  backend\.venv\Scripts\python -m pip install -r backend\requirements.txt
)
if not exist frontend\node_modules (
  echo Installing frontend packages...
  call npm --prefix frontend install
)
start "PokerGTO backend" cmd /k backend\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --port 8000
start "PokerGTO frontend" cmd /k npm --prefix frontend run dev
timeout /t 4 >nul
start http://localhost:5173
