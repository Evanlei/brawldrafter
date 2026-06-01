"""APScheduler jobs for periodic data pipeline runs."""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.services.pipeline import run_full_pipeline

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _scheduled_pipeline() -> None:
    logger.info("Scheduled pipeline starting")
    try:
        result = run_full_pipeline()
        logger.info(
            "Scheduled pipeline finished fetch=%s trained=%s failures=%s",
            result.fetch_ran,
            result.trained_mode_ids,
            result.train_failures,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Scheduled pipeline failed")


def start_scheduler() -> BackgroundScheduler | None:
    global _scheduler
    if not settings.SCHEDULER_ENABLED:
        logger.info("APScheduler disabled (SCHEDULER_ENABLED=false)")
        return None
    if _scheduler is not None:
        return _scheduler

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _scheduled_pipeline,
        trigger="interval",
        hours=settings.PIPELINE_INTERVAL_HOURS,
        id="brawldrafter_pipeline",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "APScheduler started; pipeline every %s hour(s), retrain=%s",
        settings.PIPELINE_INTERVAL_HOURS,
        settings.PIPELINE_RETRAIN,
    )
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("APScheduler stopped")


__all__ = ["start_scheduler", "stop_scheduler"]
