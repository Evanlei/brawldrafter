# Deploy API on Railway

The frontend stays on **Vercel**; this guide is for the **FastAPI + PyTorch** backend only.

## Railway settings (required)

| Setting | Value |
|---------|--------|
| **Root Directory** | `/` (repo root — **not** `backend`) |
| **Builder** | Dockerfile (`Dockerfile` at repo root) |

The Dockerfile expects paths like `backend/`, `start.sh`, and `requirements-prod.txt` at the **repo root**. Root Directory `backend` will break the build.

## What goes in git vs volume

| Artifact | In GitHub? | How to deploy |
|----------|------------|----------------|
| `backend/models/draftnet_*.pt` | **Yes** (~200KB each) — commit them | `git add -f backend/models/draftnet_1.pt` |
| `brawldrafter.db` | **No** (gitignored, ~2MB) | Railway **volume** at `/data` or `DB_DOWNLOAD_URL` |

The Docker build **does not** `COPY` the database. That keeps GitHub deploys from failing when the DB isn’t in the repo.

## 1. Commit the model checkpoint

From repo root:

```bash
git add -f backend/models/draftnet_1.pt
git commit -m "Add DraftNet checkpoint for Railway deploy"
git push
```

Add more `draftnet_2.pt`, etc. when you train other modes.

## 2. Environment variables

Railway → service → **Variables**:

| Variable | Value |
|----------|---------|
| `BRAWLSTARS_API_KEY` | your Supercell token |
| `INTERNAL_API_KEY` | long random secret |
| `FRONTEND_ORIGIN` | `https://your-app.vercel.app` |
| `DATABASE_URL` | `sqlite:////data/brawldrafter.db` (do **not** use `/app/brawldrafter.db` — the DB is on the volume) |
| `DATA_DIR` | `/data` |
| `RECOMMENDER_ALPHA` | `0.6` |
| `MODEL_DEVICE` | `cpu` |
| `SCHEDULER_ENABLED` | `false` |

Optional (first-boot DB download):

| Variable | Value |
|----------|---------|
| `DB_DOWNLOAD_URL` | HTTPS URL to a `brawldrafter.db` you uploaded (Drive/S3/GitHub Release) |

## 3. Add the database (pick one)

### A. Railway volume (recommended)

1. Deploy once (build should succeed after model is in git).
2. **Required:** Service → **Volumes** → **Add volume** → mount path **`/data`** → redeploy so the mount is active.
3. Copy your local DB (from repo root, [Railway CLI](https://docs.railway.com/develop/cli) linked):

```bash
railway link
railway ssh -s brawldrafter -- "mkdir -p /data && ls -la /data"
cat brawldrafter.db | railway ssh -s brawldrafter -- "tee /data/brawldrafter.db > /dev/null"
railway ssh -s brawldrafter -- "ls -la /data/brawldrafter.db"
```

Or: `./scripts/upload_db_to_railway.sh`

`cat > /data/brawldrafter.db` fails with “No such file or directory” when **`/data` is missing** — add the volume first, redeploy, then `mkdir -p /data`.

If `railway ssh` isn’t available on your plan, use **option B** or **C**.

(Committed models already live under `/app/backend/models/` in the image.)

### B. `DB_DOWNLOAD_URL`

Upload `brawldrafter.db` to a stable HTTPS URL (private GitHub Release asset, S3, etc.), set `DB_DOWNLOAD_URL` in Railway, redeploy. `start.sh` downloads it to `/data/brawldrafter.db` on first boot.

### C. One-shot deploy from your Mac (includes DB in image)

Temporarily use a local-only Dockerfile override, or run:

```bash
railway up
```

from your machine **before** switching to GitHub-only — your local `.dockerignore` can include the DB for that single build. For ongoing GitHub deploys, prefer **A** or **B**.

## 4. Deploy and verify

Push to GitHub (or `railway up`), then:

```bash
curl https://YOUR-RAILWAY-DOMAIN/health
curl https://YOUR-RAILWAY-DOMAIN/api/v1/modes
```

`/health` should show `models_loaded`. `/api/v1/modes` should list modes once the DB exists on `/data`.

## 5. Wire Vercel

Push the repo and redeploy the frontend. `frontend/vercel.json` proxies `/api/*` to your Railway service, so **`VITE_API_BASE` is optional**.

To call Railway directly (no proxy), set:

```
VITE_API_BASE=https://YOUR-RAILWAY-DOMAIN
```

Redeploy after changing env vars.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Build: `COPY backend/` failed | Root Directory must be **repo root**, not `backend` |
| Build: `COPY ... models` failed | Removed — commit `draftnet_*.pt` to git instead |
| `ModuleNotFoundError: backend` | Pull latest; imports use `ml` + `start.sh` |
| Empty catalog / 503 recommendations | DB missing on `/data` — complete step 3 |
| Recommendations **405** on Vercel | `VITE_API_BASE` missing `https://` (becomes a relative path), or redeploy with `frontend/vercel.json` proxy / remove `VITE_API_BASE` |
| Recommendations **Load failed** (Safari) | Cross-origin call to Railway blocked by CORS — remove `VITE_API_BASE` on Vercel (app uses `/api` proxy) or match `FRONTEND_ORIGIN` to your exact site URL |
| `DATABASE_URL` points at `/app/...` | Wrong path — use `/data/brawldrafter.db` or let `start.sh` set it when the volume file exists |
| PyTorch OOM | Upgrade Railway plan RAM (≥2GB) |
