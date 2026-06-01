#!/bin/sh
set -e

PORT="${PORT:-8000}"

# Railway Nixpacks: service root = backend/ → /app/app/main.py
if [ -f "/app/app/main.py" ] && [ -d "/app/ml" ]; then
  export PYTHONPATH="/app${PYTHONPATH:+:$PYTHONPATH}"
  exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
fi

# Docker / repo root: /app/backend/...
if [ -f "/app/backend/app/main.py" ]; then
  export PYTHONPATH="/app/backend${PYTHONPATH:+:$PYTHONPATH}"
  exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --app-dir /app/backend
fi

# Local repo layout
if [ -f "backend/app/main.py" ]; then
  export PYTHONPATH="backend${PYTHONPATH:+:$PYTHONPATH}"
  exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --app-dir backend
fi

echo "Could not find app.main — check Railway root directory (use repo root or backend/)." >&2
exit 1
