"""Feature encoding for draft-state win-probability models."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Fixed slot counts for partial drafts (3v3).
MAX_PICKS_PER_TEAM = 3
COUNTER_FEATURE_LEN = MAX_PICKS_PER_TEAM * MAX_PICKS_PER_TEAM  # 3 × 3 = 9
SYNERGY_FEATURE_LEN = 3  # C(3, 2)
WIN_RATE_FEATURE_LEN = MAX_PICKS_PER_TEAM

# Pair order for blue-team synergy slots: (pick0, pick1), (pick0, pick2), (pick1, pick2)
_SYNERGY_PAIR_INDICES = ((0, 1), (0, 2), (1, 2))


@dataclass(frozen=True)
class DraftState:
    """Current draft snapshot at inference or training time."""

    blue_picks: list[int]
    red_picks: list[int]
    map_id: int
    mode_id: int
    bans: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class FeatureStore:
    """Lookup tables and vocabulary for fixed-length feature construction."""

    all_brawler_ids: list[int]
    all_map_ids: list[int]
    all_mode_ids: list[int]
    counter_scores: dict[tuple[int, int, int], float]
    synergy_scores: dict[tuple[int, int, int], float]
    win_rates: dict[tuple[int, int], float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "all_brawler_ids", sorted(self.all_brawler_ids))
        object.__setattr__(self, "all_map_ids", sorted(self.all_map_ids))
        object.__setattr__(self, "all_mode_ids", sorted(self.all_mode_ids))


def max_brawlers(store: FeatureStore) -> int:
    return len(store.all_brawler_ids)


def max_maps(store: FeatureStore) -> int:
    return len(store.all_map_ids)


def max_modes(store: FeatureStore) -> int:
    return len(store.all_mode_ids)


def input_dim(store: FeatureStore) -> int:
    """Total length of the model input vector for this feature store."""
    return (
        max_brawlers(store)
        + max_brawlers(store)
        + max_maps(store)
        + max_modes(store)
        + COUNTER_FEATURE_LEN
        + SYNERGY_FEATURE_LEN
        + WIN_RATE_FEATURE_LEN
        + WIN_RATE_FEATURE_LEN
    )


def _pad_picks(picks: list[int], size: int = MAX_PICKS_PER_TEAM) -> list[int | None]:
    slots: list[int | None] = list(picks[:size])
    while len(slots) < size:
        slots.append(None)
    return slots


def _brawler_index(store: FeatureStore) -> dict[int, int]:
    return {brawler_id: idx for idx, brawler_id in enumerate(store.all_brawler_ids)}


def _map_index(store: FeatureStore) -> dict[int, int]:
    return {map_id: idx for idx, map_id in enumerate(store.all_map_ids)}


def _mode_index(store: FeatureStore) -> dict[int, int]:
    return {mode_id: idx for idx, mode_id in enumerate(store.all_mode_ids)}


def _lookup_counter(
    store: FeatureStore,
    blue_id: int,
    red_id: int,
    map_id: int,
) -> float:
    return float(store.counter_scores.get((blue_id, red_id, map_id), 0.0))


def _lookup_synergy(
    store: FeatureStore,
    brawler_a_id: int,
    brawler_b_id: int,
    map_id: int,
) -> float:
    key_ab = (brawler_a_id, brawler_b_id, map_id)
    if key_ab in store.synergy_scores:
        return float(store.synergy_scores[key_ab])
    key_ba = (brawler_b_id, brawler_a_id, map_id)
    if key_ba in store.synergy_scores:
        return float(store.synergy_scores[key_ba])
    return 0.0


def _lookup_win_rate(store: FeatureStore, brawler_id: int, map_id: int) -> float:
    return float(store.win_rates.get((brawler_id, map_id), 0.0))


def _encode_team_presence(
    picks: list[int],
    brawler_to_idx: dict[int, int],
    size: int,
) -> np.ndarray:
    vec = np.zeros(size, dtype=np.float32)
    for brawler_id in picks:
        idx = brawler_to_idx.get(brawler_id)
        if idx is not None:
            vec[idx] = 1.0
    return vec


def _encode_one_hot(value_id: int, index: dict[int, int], size: int) -> np.ndarray:
    vec = np.zeros(size, dtype=np.float32)
    idx = index.get(value_id)
    if idx is not None:
        vec[idx] = 1.0
    return vec


def _encode_counter_features(
    blue_slots: list[int | None],
    red_slots: list[int | None],
    map_id: int,
    store: FeatureStore,
) -> np.ndarray:
    vec = np.zeros(COUNTER_FEATURE_LEN, dtype=np.float32)
    offset = 0
    for blue_id in blue_slots:
        for red_id in red_slots:
            if blue_id is not None and red_id is not None:
                vec[offset] = _lookup_counter(store, blue_id, red_id, map_id)
            offset += 1
    return vec


def _encode_synergy_features(
    blue_slots: list[int | None],
    map_id: int,
    store: FeatureStore,
) -> np.ndarray:
    vec = np.zeros(SYNERGY_FEATURE_LEN, dtype=np.float32)
    for slot_idx, (i, j) in enumerate(_SYNERGY_PAIR_INDICES):
        a_id = blue_slots[i]
        b_id = blue_slots[j]
        if a_id is not None and b_id is not None:
            vec[slot_idx] = _lookup_synergy(store, a_id, b_id, map_id)
    return vec


def _encode_win_rate_features(
    slots: list[int | None],
    map_id: int,
    store: FeatureStore,
) -> np.ndarray:
    vec = np.zeros(WIN_RATE_FEATURE_LEN, dtype=np.float32)
    for slot_idx, brawler_id in enumerate(slots):
        if brawler_id is not None:
            vec[slot_idx] = _lookup_win_rate(store, brawler_id, map_id)
    return vec


def build_input_vector(state: DraftState, store: FeatureStore) -> np.ndarray:
    """
    Build a fixed-length feature vector for blue-team win probability.

    Layout (concatenated):
      [blue presence | red presence | map one-hot | mode one-hot |
       counters (9) | blue synergies (3) | blue win rates (3) | red win rates (3)]
    """
    brawler_idx = _brawler_index(store)
    map_idx = _map_index(store)
    mode_idx = _mode_index(store)

    blue_slots = _pad_picks(state.blue_picks)
    red_slots = _pad_picks(state.red_picks)

    parts = [
        _encode_team_presence(state.blue_picks, brawler_idx, max_brawlers(store)),
        _encode_team_presence(state.red_picks, brawler_idx, max_brawlers(store)),
        _encode_one_hot(state.map_id, map_idx, max_maps(store)),
        _encode_one_hot(state.mode_id, mode_idx, max_modes(store)),
        _encode_counter_features(blue_slots, red_slots, state.map_id, store),
        _encode_synergy_features(blue_slots, state.map_id, store),
        _encode_win_rate_features(blue_slots, state.map_id, store),
        _encode_win_rate_features(red_slots, state.map_id, store),
    ]
    return np.concatenate(parts).astype(np.float32, copy=False)


__all__ = [
    "COUNTER_FEATURE_LEN",
    "DraftState",
    "FeatureStore",
    "MAX_PICKS_PER_TEAM",
    "SYNERGY_FEATURE_LEN",
    "WIN_RATE_FEATURE_LEN",
    "build_input_vector",
    "input_dim",
    "max_brawlers",
    "max_maps",
    "max_modes",
]
