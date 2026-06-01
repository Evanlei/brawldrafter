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

## Deploy UI on Vercel (personal)

Vercel is a good fit for **this frontend only**. The API uses PyTorch + SQLite and should run elsewhere (Railway, Render, Fly, or your machine with a tunnel).

1. In [Vercel](https://vercel.com), import the repo.
2. Set **Root Directory** to `frontend`.
3. Build settings (defaults are fine): Build `npm run build`, Output `dist`.
4. Add environment variable:
   - `VITE_API_BASE` = `https://your-api-host.example.com` (optional; `vercel.json` proxies `/api/*` to Railway when unset)
5. Deploy.

On the API host, set `FRONTEND_ORIGIN` to your Vercel URL (e.g. `https://brawldrafter.vercel.app`) so CORS works.

Copy to the API server (not in git): `brawldrafter.db` and `backend/models/draftnet_*.pt`.

### API options for personal use

| Option | Notes |
|--------|--------|
| [Railway](https://railway.app) | See [docs/railway.md](../docs/railway.md) — Dockerfile in repo root |
| [Render](https://render.com) | Free web service; attach disk or re-upload DB |
| Local + [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/) | Free; laptop must stay on |
| Same machine | Run `uvicorn` at home; point `VITE_API_BASE` at tunnel URL |

## Flow

1. **Lobby** — select game mode, map, and first pick team.
2. **Ban phase** — fill 3 blue + 3 red ban slots in any order (overlap allowed).
3. **Pick phase** — snake draft; recommendations load on blue pick turns.
