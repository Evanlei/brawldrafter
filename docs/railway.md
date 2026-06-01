# Deploy API on Railway

The frontend stays on **Vercel**; this guide is for the **FastAPI + PyTorch** backend only.

## 1. Prerequisites

On your Mac, from the repo root:

- `brawldrafter.db` exists (your training DB)
- `backend/models/draftnet_1.pt` exists (at least mode 1)
- [Railway CLI](https://docs.railway.com/develop/cli) installed (`npm i -g @railway/cli` or see their docs)

## 2. Create a Railway project

```bash
cd /Users/evan/brawldrafter
railway login
railway init
```

Choose **Deploy from local directory** (or connect GitHub and use Dockerfile — see step 4).

**Important:** Set **Root Directory** to the **repo root** (`.`), not `backend`.  
If Root Directory is `backend`, Nixpacks still works via `backend/nixpacks.toml`, but Docker needs the root `Dockerfile`.

## 3. Environment variables

In Railway → your service → **Variables**, set:

| Variable | Example |
|----------|---------|
| `BRAWLSTARS_API_KEY` | your Supercell token |
| `INTERNAL_API_KEY` | long random secret |
| `FRONTEND_ORIGIN` | `https://your-app.vercel.app` |
| `DATABASE_URL` | `sqlite:////app/brawldrafter.db` |
| `RECOMMENDER_ALPHA` | `0.6` |
| `MODEL_DEVICE` | `cpu` |
| `SCHEDULER_ENABLED` | `false` |

Railway sets `PORT` automatically; do not override it.

## 4. Deploy with local DB + models

Because `*.db` and `*.pt` are gitignored, the easiest first deploy is from your machine so Docker can copy them in:

```bash
railway up
```

That uses the root `Dockerfile`, which bundles `brawldrafter.db` and `backend/models/*.pt` from your disk.

**GitHub-only deploys** won’t include those files. Options then:

- Run `railway up` once from your Mac, or  
- Attach a [Railway volume](https://docs.railway.com/reference/volumes) mounted at `/data`, set `DATABASE_URL=sqlite:////data/brawldrafter.db`, and upload the DB + models with the CLI.

## 5. Public URL

After deploy: Railway → **Settings** → **Networking** → **Generate domain**.

Example: `https://brawldrafter-production.up.railway.app`

Test:

```bash
curl https://YOUR-RAILWAY-DOMAIN/health
```

## 6. Wire Vercel

Vercel → **Environment variables** (Production):

```
VITE_API_BASE=https://YOUR-RAILWAY-DOMAIN
```

Redeploy the frontend (env vars are applied at build time).

## 7. Notes

- Use a Railway plan with enough **RAM** for PyTorch (≥ 1–2 GB recommended).
- `SCHEDULER_ENABLED=true` only if you run a **single** instance and want periodic fetch/aggregate.
- Internal pipeline routes: `POST /api/v1/internal/...` with header `X-Internal-Api-Key`.
