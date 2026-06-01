# BrawlDrafter Frontend

React + Vite + Tailwind + Zustand draft UI.

## Setup

```bash
cd frontend
npm install
```

Regenerate catalog after DB changes:

```bash
PYTHONPATH=.:backend python3 scripts/export_catalog.py
```

## Development

Run the API (from repo root):

```bash
PYTHONPATH=backend uvicorn app.main:app --reload --app-dir backend
```

Run the frontend (proxies `/api` to `localhost:8000`):

```bash
cd frontend
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

## Flow

1. **Lobby** — select game mode, map, and first pick team.
2. **Ban phase** — fill 3 blue + 3 red ban slots in any order (overlap allowed).
3. **Pick phase** — snake draft; recommendations load on blue pick turns.
