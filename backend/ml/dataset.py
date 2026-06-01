"""Load draft training data from SQLite into PyTorch datasets."""

from __future__ import annotations

import sqlite3
from pathlib import Path
import numpy as np
import torch
from torch.utils.data import Dataset

from ml.features import DraftState, FeatureStore, build_input_vector, input_dim

# (blue_picks, red_picks, map_id, winning_team)
MatchRecord = tuple[list[int], list[int], int, str]


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _fetch_distinct_brawler_ids(conn: sqlite3.Connection, mode_id: int) -> list[int]:
    ids: set[int] = set()
    if _table_exists(conn, "brawler_stats"):
        rows = conn.execute(
            "SELECT DISTINCT brawler_id FROM brawler_stats WHERE game_mode_id = ?",
            (mode_id,),
        ).fetchall()
        ids.update(int(r[0]) for r in rows)
    if _table_exists(conn, "training_match_brawlers"):
        rows = conn.execute(
            """
            SELECT DISTINCT tmb.brawler_id
            FROM training_match_brawlers tmb
            JOIN training_matches tm ON tm.id = tmb.match_id
            WHERE tm.mode_id = ?
            """,
            (mode_id,),
        ).fetchall()
        ids.update(int(r[0]) for r in rows)
    return sorted(ids)


def _fetch_distinct_map_ids(conn: sqlite3.Connection, mode_id: int) -> list[int]:
    ids: set[int] = set()
    if _table_exists(conn, "maps"):
        rows = conn.execute(
            "SELECT DISTINCT id FROM maps WHERE game_mode_id = ?",
            (mode_id,),
        ).fetchall()
        ids.update(int(r[0]) for r in rows)
    if _table_exists(conn, "training_matches"):
        rows = conn.execute(
            "SELECT DISTINCT map_id FROM training_matches WHERE mode_id = ?",
            (mode_id,),
        ).fetchall()
        ids.update(int(r[0]) for r in rows)
    if _table_exists(conn, "brawler_stats"):
        rows = conn.execute(
            "SELECT DISTINCT map_id FROM brawler_stats WHERE game_mode_id = ?",
            (mode_id,),
        ).fetchall()
        ids.update(int(r[0]) for r in rows)
    return sorted(ids)


def load_feature_store(conn: sqlite3.Connection, mode_id: int) -> FeatureStore:
    """Load vocabularies and score lookups for a single game mode."""
    win_rates: dict[tuple[int, int], float] = {}
    synergy_scores: dict[tuple[int, int, int], float] = {}
    counter_scores: dict[tuple[int, int, int], float] = {}

    if _table_exists(conn, "brawler_stats"):
        for brawler_id, map_id, win_rate in conn.execute(
            """
            SELECT brawler_id, map_id, win_rate
            FROM brawler_stats
            WHERE game_mode_id = ?
            """,
            (mode_id,),
        ):
            win_rates[(int(brawler_id), int(map_id))] = float(win_rate)

    if _table_exists(conn, "synergies"):
        for a_id, b_id, map_id, score in conn.execute(
            """
            SELECT brawler_a_id, brawler_b_id, map_id, synergy_score
            FROM synergies
            WHERE game_mode_id = ?
            """,
            (mode_id,),
        ):
            synergy_scores[(int(a_id), int(b_id), int(map_id))] = float(score)

    if _table_exists(conn, "counters"):
        for a_id, b_id, map_id, score in conn.execute(
            """
            SELECT brawler_a_id, brawler_b_id, map_id, counter_score
            FROM counters
            WHERE game_mode_id = ?
            """,
            (mode_id,),
        ):
            counter_scores[(int(a_id), int(b_id), int(map_id))] = float(score)

    return FeatureStore(
        all_brawler_ids=_fetch_distinct_brawler_ids(conn, mode_id),
        all_map_ids=_fetch_distinct_map_ids(conn, mode_id),
        all_mode_ids=[mode_id],
        counter_scores=counter_scores,
        synergy_scores=synergy_scores,
        win_rates=win_rates,
    )


def _load_team_picks(
    conn: sqlite3.Connection, match_id: int, team: str
) -> list[int]:
    rows = conn.execute(
        """
        SELECT brawler_id
        FROM training_match_brawlers
        WHERE match_id = ? AND team = ?
        ORDER BY pick_order ASC
        """,
        (match_id, team),
    ).fetchall()
    return [int(row[0]) for row in rows]


def load_matches(conn: sqlite3.Connection, mode_id: int) -> list[MatchRecord]:
    """Load complete 3v3 matches for a mode; excludes draws."""
    if not _table_exists(conn, "training_matches"):
        return []

    rows = conn.execute(
        """
        SELECT id, map_id, winning_team
        FROM training_matches
        WHERE mode_id = ? AND winning_team IN ('blue', 'red')
        ORDER BY id ASC
        """,
        (mode_id,),
    ).fetchall()

    matches: list[MatchRecord] = []
    for match_id, map_id, winning_team in rows:
        blue_picks = _load_team_picks(conn, int(match_id), "blue")
        red_picks = _load_team_picks(conn, int(match_id), "red")
        if len(blue_picks) != 3 or len(red_picks) != 3:
            continue
        if len(set(blue_picks)) != 3 or len(set(red_picks)) != 3:
            continue
        matches.append((blue_picks, red_picks, int(map_id), str(winning_team)))
    return matches


def augment_to_partial_states(matches: list[MatchRecord]) -> list[MatchRecord]:
    """
    Expand each complete match into three training snapshots:
    1v1 (first pick each side), 2v2 (first two picks), 3v3 (full teams).
    """
    expanded: list[MatchRecord] = []
    for blue_picks, red_picks, map_id, winning_team in matches:
        expanded.append((blue_picks[:1], red_picks[:1], map_id, winning_team))
        expanded.append((blue_picks[:2], red_picks[:2], map_id, winning_team))
        expanded.append((blue_picks[:3], red_picks[:3], map_id, winning_team))
    return expanded


def _label_from_winner(winning_team: str) -> float:
    if winning_team == "blue":
        return 1.0
    if winning_team == "red":
        return 0.0
    raise ValueError(f"Unexpected winning_team for binary label: {winning_team!r}")


class DraftDataset(Dataset):
    """PyTorch dataset of (feature_vector, blue_win_label) pairs."""

    def __init__(
        self,
        samples: list[MatchRecord],
        store: FeatureStore,
        mode_id: int,
    ) -> None:
        self.store = store
        self.mode_id = mode_id
        self.samples = samples

        vectors: list[np.ndarray] = []
        labels: list[float] = []
        for blue_picks, red_picks, map_id, winning_team in samples:
            state = DraftState(
                blue_picks=blue_picks,
                red_picks=red_picks,
                map_id=map_id,
                mode_id=mode_id,
            )
            vectors.append(build_input_vector(state, store))
            labels.append(_label_from_winner(winning_team))

        if vectors:
            self._features = torch.from_numpy(np.stack(vectors, axis=0))
            self._labels = torch.tensor(labels, dtype=torch.float32)
        else:
            self._features = torch.empty((0, input_dim(store)), dtype=torch.float32)
            self._labels = torch.empty((0,), dtype=torch.float32)

    def __len__(self) -> int:
        return int(self._labels.shape[0])

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        return self._features[index], self._labels[index]


def load_dataset(db_path: str | Path, mode_id: int) -> DraftDataset:
    """Open the DB, build feature store + augmented samples, return a DraftDataset."""
    path = Path(db_path)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        store = load_feature_store(conn, mode_id)
        matches = load_matches(conn, mode_id)
        samples = augment_to_partial_states(matches)
    return DraftDataset(samples, store, mode_id)


__all__ = [
    "DraftDataset",
    "MatchRecord",
    "augment_to_partial_states",
    "load_dataset",
    "load_feature_store",
    "load_matches",
]
