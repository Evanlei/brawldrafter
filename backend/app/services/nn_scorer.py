"""Neural draft scoring wrapper (feature encoding + DraftNet inference)."""

from __future__ import annotations

from backend.ml.features import FeatureStore
from backend.ml.inference import rank_candidates
from app.services.model_runtime import get_inference_model


def score_candidates_nn(
    *,
    mode_id: int,
    map_id: int,
    blue_picks: list[int],
    red_picks: list[int],
    available_brawlers: list[int],
    store: FeatureStore,
) -> dict[int, float]:
    """
    Return raw neural win-probability scores keyed by brawler id.

    Raises RuntimeError when the mode checkpoint is missing or inference fails.
    """
    inference = get_inference_model(mode_id)
    if inference is None:
        raise RuntimeError(f"DraftNet model missing for mode_id={mode_id}")

    ranked = rank_candidates(
        inference,
        blue_picks,
        red_picks,
        available_brawlers,
        map_id,
        mode_id,
        store,
    )
    return {brawler_id: float(score) for brawler_id, score in ranked}


def normalize_scores(scores: dict[int, float]) -> dict[int, float]:
    """Min-max normalize scores to [0, 1] for fusion with deterministic scores."""
    if not scores:
        return {}
    values = list(scores.values())
    lo = min(values)
    hi = max(values)
    if hi == lo:
        return {key: 0.5 for key in scores}
    span = hi - lo
    return {key: (value - lo) / span for key, value in scores.items()}


__all__ = ["normalize_scores", "score_candidates_nn"]
