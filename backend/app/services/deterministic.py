"""Deterministic draft scoring (Mode A fallback)."""

from __future__ import annotations

from dataclasses import dataclass

from ml.features import FeatureStore

# Weights aligned with spec hybrid formula (deterministic-only path).
W_WIN_RATE = 0.40
W_COUNTER = 0.30
W_SYNERGY = 0.20
W_RELIABILITY = 0.10
RELIABILITY_SAMPLE_CAP = 200.0
# Pseudo-match count pulling brawler WR toward map baseline (reduces 100% noise on n=1–3).
WIN_RATE_SHRINKAGE_PRIOR = 20.0
MIN_SAMPLE_FULL_WEIGHT = 30


@dataclass(frozen=True)
class DeterministicScore:
    brawler_id: int
    score: float
    reason: str


def _lookup_counter(store: FeatureStore, blue_id: int, red_id: int, map_id: int) -> float:
    return float(store.counter_scores.get((blue_id, red_id, map_id), 0.0))


def _lookup_synergy(store: FeatureStore, a_id: int, b_id: int, map_id: int) -> float:
    key_ab = (a_id, b_id, map_id)
    if key_ab in store.synergy_scores:
        return float(store.synergy_scores[key_ab])
    key_ba = (b_id, a_id, map_id)
    return float(store.synergy_scores.get(key_ba, 0.0))


def _lookup_win_rate(store: FeatureStore, brawler_id: int, map_id: int) -> float:
    return float(store.win_rates.get((brawler_id, map_id), 0.0))


def map_baseline_win_rate(
    map_id: int,
    store: FeatureStore,
    sample_sizes: dict[tuple[int, int], int] | None,
) -> float:
    """Sample-size-weighted average raw win rate on this map."""
    sizes = sample_sizes or {}
    weighted = 0.0
    total_n = 0
    for (brawler_id, mid), raw_wr in store.win_rates.items():
        if mid != map_id:
            continue
        n = sizes.get((brawler_id, map_id), 0)
        if n <= 0:
            continue
        weighted += float(raw_wr) * n
        total_n += n
    if total_n <= 0:
        return 0.5
    return weighted / total_n


def adjusted_map_win_rate(
    brawler_id: int,
    map_id: int,
    store: FeatureStore,
    sample_sizes: dict[tuple[int, int], int] | None,
    *,
    baseline: float | None = None,
) -> float:
    """
    Shrink raw map win rate toward the map baseline so small samples are not shown as 100%.
    """
    raw = _lookup_win_rate(store, brawler_id, map_id)
    n = (sample_sizes or {}).get((brawler_id, map_id), 0)
    if n <= 0:
        return 0.0
    base = baseline if baseline is not None else map_baseline_win_rate(map_id, store, sample_sizes)
    prior = WIN_RATE_SHRINKAGE_PRIOR
    return (raw * n + base * prior) / (n + prior)


def _reliability(sample_size: int) -> float:
    return min(max(sample_size, 0) / RELIABILITY_SAMPLE_CAP, 1.0)


def _format_pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def _build_reason(
    *,
    brawler_name: str,
    win_rate: float,
    sample_size: int,
    best_counter: tuple[int, float] | None,
    best_synergy: tuple[int, float] | None,
    counter_names: dict[int, str],
    synergy_names: dict[int, str],
) -> str:
    candidates: list[tuple[float, str]] = []

    if win_rate > 0 and sample_size > 0:
        games_note = f", {sample_size} matches" if sample_size < MIN_SAMPLE_FULL_WEIGHT else ""
        candidates.append(
            (
                win_rate * W_WIN_RATE,
                f"Map win rate ({_format_pct(win_rate)}{games_note}) for {brawler_name}",
            )
        )
    if best_counter and best_counter[1] > 0:
        red_name = counter_names.get(best_counter[0], f"Brawler {best_counter[0]}")
        candidates.append(
            (
                best_counter[1] * W_COUNTER,
                f"Counters {red_name} on this map",
            )
        )
    if best_synergy and best_synergy[1] > 0:
        ally_name = synergy_names.get(best_synergy[0], f"Brawler {best_synergy[0]}")
        candidates.append(
            (
                best_synergy[1] * W_SYNERGY,
                f"Synergizes with {ally_name}",
            )
        )

    if not candidates:
        return f"Balanced stats profile for {brawler_name} on this map"

    return max(candidates, key=lambda row: row[0])[1]


def score_candidate(
    candidate_id: int,
    blue_picks: list[int],
    red_picks: list[int],
    map_id: int,
    store: FeatureStore,
    *,
    brawler_name: str,
    brawler_names: dict[int, str],
    sample_sizes: dict[tuple[int, int], int] | None = None,
) -> DeterministicScore:
    sample_size = (sample_sizes or {}).get((candidate_id, map_id), 0)
    baseline = map_baseline_win_rate(map_id, store, sample_sizes)
    win_rate = adjusted_map_win_rate(
        candidate_id,
        map_id,
        store,
        sample_sizes,
        baseline=baseline,
    )

    counter_values = [
        (red_id, _lookup_counter(store, candidate_id, red_id, map_id)) for red_id in red_picks
    ]
    synergy_values = [
        (ally_id, _lookup_synergy(store, candidate_id, ally_id, map_id)) for ally_id in blue_picks
    ]

    avg_counter = sum(v for _, v in counter_values) / len(counter_values) if counter_values else 0.0
    avg_synergy = sum(v for _, v in synergy_values) / len(synergy_values) if synergy_values else 0.0
    reliability = _reliability(sample_size)

    score = (
        W_WIN_RATE * win_rate
        + W_COUNTER * avg_counter
        + W_SYNERGY * avg_synergy
        + W_RELIABILITY * reliability
    )

    best_counter = max(counter_values, key=lambda row: row[1]) if counter_values else None
    best_synergy = max(synergy_values, key=lambda row: row[1]) if synergy_values else None
    reason = _build_reason(
        brawler_name=brawler_name,
        win_rate=win_rate,
        sample_size=sample_size,
        best_counter=best_counter,
        best_synergy=best_synergy,
        counter_names=brawler_names,
        synergy_names=brawler_names,
    )
    return DeterministicScore(brawler_id=candidate_id, score=score, reason=reason)


def rank_deterministic(
    blue_picks: list[int],
    red_picks: list[int],
    available_brawlers: list[int],
    map_id: int,
    store: FeatureStore,
    *,
    brawler_names: dict[int, str],
    sample_sizes: dict[tuple[int, int], int] | None = None,
) -> list[tuple[int, float, str]]:
    """Return (brawler_id, score, reason) sorted by score descending."""
    scored: list[DeterministicScore] = []
    for brawler_id in available_brawlers:
        if brawler_id in blue_picks or brawler_id in red_picks:
            continue
        name = brawler_names.get(brawler_id, f"Brawler {brawler_id}")
        scored.append(
            score_candidate(
                brawler_id,
                blue_picks,
                red_picks,
                map_id,
                store,
                brawler_name=name,
                brawler_names=brawler_names,
                sample_sizes=sample_sizes,
            )
        )
    scored.sort(key=lambda row: row.score, reverse=True)
    return [(row.brawler_id, row.score, row.reason) for row in scored]


def confidence_from_scores(scores: list[float]) -> list[float]:
    """Map raw deterministic scores to display confidence values in (0, 1]."""
    if not scores:
        return []
    lo = min(scores)
    hi = max(scores)
    if hi == lo:
        return [0.72 for _ in scores]
    return [0.55 + 0.35 * ((s - lo) / (hi - lo)) for s in scores]


__all__ = [
    "DeterministicScore",
    "adjusted_map_win_rate",
    "confidence_from_scores",
    "map_baseline_win_rate",
    "rank_deterministic",
    "score_candidate",
]
