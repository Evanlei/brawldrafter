"""Hybrid recommendation orchestration: deterministic + DraftNet fusion."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.services.deterministic import (
    adjusted_map_win_rate,
    confidence_from_scores,
    map_baseline_win_rate,
    rank_deterministic,
)
from app.services.model_runtime import has_draftnet_model
from app.services.nn_scorer import normalize_scores, score_candidates_nn
from app.services.recommendation_errors import (
    InsufficientCandidatesError,
    ModelUnavailableError,
)
from ml.dataset import load_feature_store
from ml.features import FeatureStore

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class RecommendationRequest:
    map_id: int
    mode_id: int
    first_pick_team: str
    blue_bans: list[int]
    red_bans: list[int]
    blue_picks: list[int]
    red_picks: list[int]
    current_pick_number: int


@dataclass(frozen=True)
class RecommendationItem:
    brawler_id: int
    name: str
    map_win_rate: float
    pick_score: float
    reason: str


def _resolve_db_path() -> Path:
    db_url = settings.DATABASE_URL
    if db_url.startswith("sqlite:///"):
        raw = db_url.removeprefix("sqlite:///")
        path = Path(raw)
        if path.is_absolute():
            return path
        return (_PROJECT_ROOT / path).resolve()
    return (_PROJECT_ROOT / "brawldrafter.db").resolve()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def load_brawler_names(conn: sqlite3.Connection, brawler_ids: list[int]) -> dict[int, str]:
    if not brawler_ids or not _table_exists(conn, "brawlers"):
        return {bid: f"Brawler {bid}" for bid in brawler_ids}

    placeholders = ",".join("?" for _ in brawler_ids)
    rows = conn.execute(
        f"SELECT id, name FROM brawlers WHERE id IN ({placeholders})",
        brawler_ids,
    ).fetchall()
    names = {int(row[0]): str(row[1]) for row in rows}
    for bid in brawler_ids:
        names.setdefault(bid, f"Brawler {bid}")
    return names


def load_sample_sizes(conn: sqlite3.Connection, mode_id: int) -> dict[tuple[int, int], int]:
    if not _table_exists(conn, "brawler_stats"):
        return {}
    rows = conn.execute(
        """
        SELECT brawler_id, map_id, sample_size
        FROM brawler_stats
        WHERE game_mode_id = ?
        """,
        (mode_id,),
    ).fetchall()
    return {(int(bid), int(mid)): int(size) for bid, mid, size in rows}


def derive_available_brawlers(
    store: FeatureStore,
    *,
    blue_bans: list[int],
    red_bans: list[int],
    blue_picks: list[int],
    red_picks: list[int],
) -> list[int]:
    taken = set(blue_bans) | set(red_bans) | set(blue_picks) | set(red_picks)
    return [bid for bid in store.all_brawler_ids if bid not in taken]


def _fuse_and_rank(
    *,
    det_ranked: list[tuple[int, float, str]],
    nn_scores: dict[int, float] | None,
    alpha: float,
    brawler_names: dict[int, str],
) -> list[tuple[int, float, str]]:
    """Blend deterministic and neural scores; return (id, fused_score, reason)."""
    det_by_id = {bid: score for bid, score, _ in det_ranked}
    reasons = {bid: reason for bid, _, reason in det_ranked}

    if nn_scores is None or alpha >= 1.0:
        return det_ranked

    if alpha <= 0.0:
        nn_norm = normalize_scores(nn_scores)
        ranked = sorted(
            ((bid, nn_norm[bid], reasons.get(bid, f"Model favors {brawler_names.get(bid, bid)}"))
             for bid in nn_norm),
            key=lambda row: row[1],
            reverse=True,
        )
        return ranked

    det_norm = normalize_scores(det_by_id)
    nn_norm = normalize_scores(nn_scores)
    candidate_ids = set(det_norm) | set(nn_norm)
    fused: list[tuple[int, float, str]] = []
    for brawler_id in candidate_ids:
        det_part = det_norm.get(brawler_id, 0.0)
        nn_part = nn_norm.get(brawler_id, 0.0)
        score = alpha * det_part + (1.0 - alpha) * nn_part
        fused.append((brawler_id, score, reasons.get(brawler_id, f"Strong pick for this draft")))
    fused.sort(key=lambda row: row[1], reverse=True)
    return fused


def get_recommendations(request: RecommendationRequest) -> list[RecommendationItem]:
    """
    Return up to 3 pick recommendations for the current blue-team turn.

    Uses weighted fusion of deterministic and DraftNet scores when a per-mode
    checkpoint exists; otherwise deterministic scoring only.
    """
    alpha = settings.RECOMMENDER_ALPHA
    db_path = _resolve_db_path()
    with sqlite3.connect(db_path) as conn:
        store = load_feature_store(conn, request.mode_id)
        available = derive_available_brawlers(
            store,
            blue_bans=request.blue_bans,
            red_bans=request.red_bans,
            blue_picks=request.blue_picks,
            red_picks=request.red_picks,
        )
        name_ids = sorted(
            set(available)
            | set(request.blue_picks)
            | set(request.red_picks)
            | set(request.blue_bans)
            | set(request.red_bans)
        )
        brawler_names = load_brawler_names(conn, name_ids)
        sample_sizes = load_sample_sizes(conn, request.mode_id)

    if len(available) < 3:
        raise InsufficientCandidatesError(
            f"Only {len(available)} brawler(s) available; need at least 3"
        )

    det_ranked = rank_deterministic(
        request.blue_picks,
        request.red_picks,
        available,
        request.map_id,
        store,
        brawler_names=brawler_names,
        sample_sizes=sample_sizes,
    )

    nn_scores: dict[int, float] | None = None
    if alpha < 1.0 and has_draftnet_model(request.mode_id):
        try:
            nn_scores = score_candidates_nn(
                mode_id=request.mode_id,
                map_id=request.map_id,
                blue_picks=request.blue_picks,
                red_picks=request.red_picks,
                available_brawlers=available,
                store=store,
            )
        except Exception as exc:  # noqa: BLE001
            if alpha <= 0.0:
                raise ModelUnavailableError(
                    f"DraftNet inference failed for mode_id={request.mode_id}"
                ) from exc
            logger.exception(
                "DraftNet inference failed for mode_id=%s; using deterministic only: %s",
                request.mode_id,
                exc,
            )
    elif alpha <= 0.0:
        raise ModelUnavailableError(
            f"No DraftNet checkpoint for mode_id={request.mode_id}"
        )

    fused = _fuse_and_rank(
        det_ranked=det_ranked,
        nn_scores=nn_scores,
        alpha=alpha,
        brawler_names=brawler_names,
    )
    top = fused[:3]
    pick_scores = confidence_from_scores([score for _, score, _ in top])
    baseline = map_baseline_win_rate(request.map_id, store, sample_sizes)

    return [
        RecommendationItem(
            brawler_id=brawler_id,
            name=brawler_names.get(brawler_id, f"Brawler {brawler_id}"),
            map_win_rate=round(
                adjusted_map_win_rate(
                    brawler_id,
                    request.map_id,
                    store,
                    sample_sizes,
                    baseline=baseline,
                ),
                4,
            ),
            pick_score=round(pick_score, 4),
            reason=reason,
        )
        for (brawler_id, _score, reason), pick_score in zip(top, pick_scores)
    ]


__all__ = [
    "RecommendationItem",
    "RecommendationRequest",
    "derive_available_brawlers",
    "get_recommendations",
]
