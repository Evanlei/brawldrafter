"""Deterministic scorer tests."""

from __future__ import annotations

from app.services.deterministic import (
    confidence_from_scores,
    rank_deterministic,
    score_candidate,
)


def test_win_rate_and_reliability_influence_ranking(feature_store) -> None:
    brawler_names = {i: f"Brawler {i}" for i in range(1, 20)}
    sample_sizes = {(1, 1): 150, (5, 1): 40, (10, 1): 10}

    ranked = rank_deterministic(
        blue_picks=[],
        red_picks=[9],
        available_brawlers=[1, 5, 10],
        map_id=1,
        store=feature_store,
        brawler_names=brawler_names,
        sample_sizes=sample_sizes,
    )

    assert ranked[0][0] == 1
    assert ranked[0][1] >= ranked[1][1] >= ranked[2][1]


def test_counter_and_synergy_contribute_to_reason(feature_store) -> None:
    brawler_names = {1: "Tara", 5: "Shelly", 9: "Emz"}
    result = score_candidate(
        1,
        blue_picks=[5],
        red_picks=[9],
        map_id=1,
        store=feature_store,
        brawler_name="Tara",
        brawler_names=brawler_names,
        sample_sizes={(1, 1): 100},
    )
    assert result.reason
    assert "Tara" in result.reason or "Shelly" in result.reason or "Emz" in result.reason


def test_stable_ranking_for_unchanged_input(feature_store) -> None:
    brawler_names = {i: f"Brawler {i}" for i in range(1, 15)}
    kwargs = dict(
        blue_picks=[2],
        red_picks=[9],
        available_brawlers=[1, 3, 4, 5, 6],
        map_id=1,
        store=feature_store,
        brawler_names=brawler_names,
        sample_sizes={(i, 1): 50 for i in range(1, 15)},
    )
    first = rank_deterministic(**kwargs)
    second = rank_deterministic(**kwargs)
    assert first == second


def test_confidence_from_scores_spreads_values() -> None:
    confidences = confidence_from_scores([0.2, 0.5, 0.8])
    assert len(confidences) == 3
    assert confidences[0] < confidences[-1]
    assert all(0.0 < c <= 1.0 for c in confidences)


def test_confidence_flat_scores_use_default() -> None:
    confidences = confidence_from_scores([0.5, 0.5, 0.5])
    assert confidences == [0.72, 0.72, 0.72]


def test_adjusted_win_rate_shrinks_small_samples(feature_store) -> None:
    from app.services.deterministic import adjusted_map_win_rate, map_baseline_win_rate

    sample_sizes = {(99, 1): 2, (1, 1): 80}
    baseline = map_baseline_win_rate(1, feature_store, sample_sizes)
    raw_perfect = adjusted_map_win_rate(99, 1, feature_store, sample_sizes, baseline=baseline)
    assert raw_perfect < 1.0
    assert raw_perfect > baseline * 0.9
