#!/bin/sh
set -e

PORT="${PORT:-8000}"
DATA_DIR="${DATA_DIR:-/data}"

# Optional: download DB on first boot (upload brawldrafter.db to a private URL, set in Railway)
if [ -n "$DB_DOWNLOAD_URL" ] && [ ! -f "$DATA_DIR/brawldrafter.db" ]; then
  echo "Downloading database to $DATA_DIR/brawldrafter.db ..."
  mkdir -p "$DATA_DIR"
  curl -fsSL "$DB_DOWNLOAD_URL" -o "$DATA_DIR/brawldrafter.db"
fi

if [ -f "$DATA_DIR/brawldrafter.db" ]; then
  export DATABASE_URL="sqlite:////$DATA_DIR/brawldrafter.db"
  echo "Using database at $DATABASE_URL"
fi

if [ ! -f "$DATA_DIR/brawldrafter.db" ] && [ ! -f "/app/brawldrafter.db" ]; then
  echo "WARNING: No brawldrafter.db at $DATA_DIR/brawldrafter.db — catalog/recommendations will be empty until you add one (see docs/railway.md)."
fi

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

echo "Could not find app.main — set Railway Root Directory to repo root (/)." >&2
exit 1
