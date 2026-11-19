#!/usr/bin/env bash
# PokerGTO local - one-time setup + start (backend :8000, frontend :5173). macOS / Linux.
set -e
cd "$(dirname "$0")"
if [ ! -d backend/.venv ]; then
  echo "Creating Python venv..."
  python3 -m venv backend/.venv
  backend/.venv/bin/python -m pip install -r backend/requirements.txt
fi
if [ ! -d frontend/node_modules ]; then
  echo "Installing frontend packages..."
  npm --prefix frontend install
fi
backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --port 8000 &
BACK=$!
trap 'kill $BACK 2>/dev/null' EXIT
echo "Open http://localhost:5173"
npm --prefix frontend run dev
