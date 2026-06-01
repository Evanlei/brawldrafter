"""Data pipeline: fetch training matches, aggregate stats, optionally retrain models."""

from __future__ import annotations

import logging
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.services.aggregation import AggregationResult, aggregate_database, resolve_db_path
from app.services.brawler_bootstrap import sync_brawler_names
from app.services.model_runtime import clear_inference_cache, warmup_inference_cache

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_FETCH_SCRIPT = _PROJECT_ROOT / "scripts" / "fetch_training_data.py"
_TRAIN_SCRIPT = _PROJECT_ROOT / "backend" / "ml" / "train.py"


@dataclass(frozen=True)
class PipelineRunResult:
    fetch_ran: bool
    aggregate: AggregationResult | None
    brawlers_synced: int
    trained_mode_ids: list[int]
    train_failures: list[int]


def run_fetch(*, players: int | None = None, matches_per_player: int | None = None) -> None:
    """Run the training-data fetch script as a subprocess."""
    players = players if players is not None else settings.PIPELINE_FETCH_PLAYERS
    matches_per_player = (
        matches_per_player
        if matches_per_player is not None
        else settings.PIPELINE_FETCH_MATCHES_PER_PLAYER
    )
    cmd = [
        sys.executable,
        str(_FETCH_SCRIPT),
        "--players",
        str(players),
        "--matches-per-player",
        str(matches_per_player),
    ]
    logger.info("Running fetch pipeline: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=str(_PROJECT_ROOT))


def run_aggregate(*, mode_id: int | None = None) -> AggregationResult:
    result = aggregate_database(mode_id=mode_id)
    synced = sync_brawler_names()
    logger.info("Aggregation finished; synced %s brawler names", synced)
    return result


def _modes_with_min_matches(db_path: Path, min_matches: int) -> list[int]:
    with sqlite3.connect(db_path) as conn:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='training_matches'"
        ).fetchone():
            return []
        rows = conn.execute(
            """
            SELECT mode_id, COUNT(*) AS match_count
            FROM training_matches
            GROUP BY mode_id
            HAVING match_count >= ?
            ORDER BY mode_id
            """,
            (min_matches,),
        ).fetchall()
    return [int(row[0]) for row in rows]


def run_train_mode(
    mode_id: int,
    *,
    epochs: int | None = None,
    aggregate_first: bool = True,
) -> None:
    db_path = resolve_db_path()
    epochs = epochs if epochs is not None else settings.PIPELINE_TRAIN_EPOCHS
    cmd = [
        sys.executable,
        str(_TRAIN_SCRIPT),
        "--db-path",
        str(db_path),
        "--mode-id",
        str(mode_id),
        "--epochs",
        str(epochs),
    ]
    if aggregate_first:
        cmd.append("--aggregate-first")
    logger.info("Training DraftNet for mode_id=%s", mode_id)
    subprocess.run(cmd, check=True, cwd=str(_PROJECT_ROOT))


def run_train_all_modes(
    *,
    min_matches: int | None = None,
    epochs: int | None = None,
) -> tuple[list[int], list[int]]:
    min_matches = (
        min_matches if min_matches is not None else settings.PIPELINE_TRAIN_MIN_MATCHES
    )
    db_path = resolve_db_path()
    mode_ids = _modes_with_min_matches(db_path, min_matches)
    trained: list[int] = []
    failures: list[int] = []
    for mode_id in mode_ids:
        try:
            run_train_mode(mode_id, epochs=epochs, aggregate_first=False)
            trained.append(mode_id)
        except subprocess.CalledProcessError:
            logger.exception("Training failed for mode_id=%s", mode_id)
            failures.append(mode_id)
    if trained:
        clear_inference_cache()
        warmup_inference_cache()
    return trained, failures


def run_full_pipeline(
    *,
    fetch: bool = True,
    aggregate: bool = True,
    retrain: bool | None = None,
    players: int | None = None,
    matches_per_player: int | None = None,
    mode_id: int | None = None,
) -> PipelineRunResult:
    """fetch → aggregate → bootstrap names → optional train all modes."""
    retrain = settings.PIPELINE_RETRAIN if retrain is None else retrain
    fetch_ran = False
    agg_result: AggregationResult | None = None
    synced = 0
    trained: list[int] = []
    failures: list[int] = []

    if fetch:
        run_fetch(players=players, matches_per_player=matches_per_player)
        fetch_ran = True

    if aggregate:
        agg_result = run_aggregate(mode_id=mode_id)
        synced = 0
    else:
        synced = sync_brawler_names()

    if retrain:
        trained, failures = run_train_all_modes()

    return PipelineRunResult(
        fetch_ran=fetch_ran,
        aggregate=agg_result,
        brawlers_synced=synced,
        trained_mode_ids=trained,
        train_failures=failures,
    )


__all__ = [
    "PipelineRunResult",
    "run_aggregate",
    "run_fetch",
    "run_full_pipeline",
    "run_train_all_modes",
    "run_train_mode",
]
