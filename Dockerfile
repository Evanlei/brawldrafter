# BrawlDrafter API — Railway / Docker
FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# CPU-only PyTorch (smaller image than default CUDA wheels)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

COPY backend ./backend
COPY start.sh ./start.sh

# Training DB + DraftNet checkpoints (not in git — present when you `railway up` locally)
COPY brawldrafter.db* ./
COPY backend/models ./backend/models

ENV PYTHONPATH=/app/backend \
    DATABASE_URL=sqlite:////app/brawldrafter.db \
    MODEL_DEVICE=cpu \
    SCHEDULER_ENABLED=false

EXPOSE 8000

RUN chmod +x /app/start.sh
CMD ["sh", "/app/start.sh"]
