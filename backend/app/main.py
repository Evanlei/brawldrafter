"""BrawlDrafter FastAPI application."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.routes.catalog import router as catalog_router
from app.api.routes.internal import router as internal_router
from app.api.routes.recommendations import limiter, router as recommendations_router
from app.core.config import settings
from app.services.model_runtime import clear_inference_cache, model_registry, warmup_inference_cache
from app.services.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    warmup_inference_cache()
    registry = model_registry()
    if registry:
        for mode_id, meta in registry.items():
            logger.info(
                "Model registry mode_id=%s sha256=%s val_accuracy=%s",
                mode_id,
                str(meta.get("sha256", ""))[:16],
                meta.get("val_accuracy"),
            )
    else:
        logger.warning("No DraftNet checkpoints loaded at startup")
    start_scheduler()
    yield
    stop_scheduler()
    clear_inference_cache()


app = FastAPI(title="BrawlDrafter", version="2.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(recommendations_router)
app.include_router(catalog_router)
app.include_router(internal_router)


@app.get("/health")
def health() -> dict[str, object]:
    from app.services.model_runtime import loaded_mode_ids

    return {
        "status": "ok",
        "models_loaded": loaded_mode_ids(),
        "model_registry": model_registry(),
        "scheduler_enabled": settings.SCHEDULER_ENABLED,
    }
