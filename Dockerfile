# BrawlDrafter API — Railway / Docker (repo root build context)
FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# CPU-only PyTorch (smaller image than default CUDA wheels)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

COPY backend ./backend
COPY start.sh ./start.sh
RUN chmod +x /app/start.sh

# Models: commit backend/models/draftnet_*.pt to git (see .gitignore exceptions).
# DB: use a Railway volume at /data (see docs/railway.md) — not copied in GitHub builds.
RUN mkdir -p /data /app/backend/models

ENV PYTHONPATH=/app/backend \
    DATA_DIR=/data \
    DATABASE_URL=sqlite:////data/brawldrafter.db \
    MODEL_DEVICE=cpu \
    SCHEDULER_ENABLED=false

EXPOSE 8000

CMD ["sh", "/app/start.sh"]
