"""Aggregate training matches into brawler stats, counters, and synergies."""

from __future__ import annotations

import logging
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from app.core.config import settings
from app.services.meta_snapshot import record_snapshot

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class MatchRow:
    map_id: int
    mode_id: int
    winning_team: str
    blue_picks: list[int]
    red_picks: list[int]


@dataclass(frozen=True)
class AggregationResult:
    match_count: int
    mode_ids: list[int]
    brawler_stats_rows: int
    counter_rows: int
    synergy_rows: int
    snapshot_id: int


def resolve_db_path() -> Path:
    db_url = settings.DATABASE_URL
    if db_url.startswith("sqlite:///"):
        raw = db_url.removeprefix("sqlite:///")
        path = Path(raw)
        if path.is_absolute():
            return path.resolve()
        return (_PROJECT_ROOT / path).resolve()
    return (_PROJECT_ROOT / "brawldrafter.db").resolve()


def ensure_aggregated_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS brawlers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS brawler_stats (
            brawler_id INTEGER NOT NULL,
            map_id INTEGER NOT NULL,
            game_mode_id INTEGER NOT NULL,
            win_rate REAL NOT NULL,
            sample_size INTEGER NOT NULL,
            pick_rate REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (brawler_id, map_id, game_mode_id),
            FOREIGN KEY (brawler_id) REFERENCES brawlers(id),
            FOREIGN KEY (map_id) REFERENCES maps(id),
            FOREIGN KEY (game_mode_id) REFERENCES game_modes(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS counters (
            brawler_a_id INTEGER NOT NULL,
            brawler_b_id INTEGER NOT NULL,
            map_id INTEGER NOT NULL,
            game_mode_id INTEGER NOT NULL,
            counter_score REAL NOT NULL,
            sample_size INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (brawler_a_id, brawler_b_id, map_id, game_mode_id),
            FOREIGN KEY (brawler_a_id) REFERENCES brawlers(id),
            FOREIGN KEY (brawler_b_id) REFERENCES brawlers(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS synergies (
            brawler_a_id INTEGER NOT NULL,
            brawler_b_id INTEGER NOT NULL,
            map_id INTEGER NOT NULL,
            game_mode_id INTEGER NOT NULL,
            synergy_score REAL NOT NULL,
            sample_size INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (brawler_a_id, brawler_b_id, map_id, game_mode_id),
            CHECK (brawler_a_id < brawler_b_id),
            FOREIGN KEY (brawler_a_id) REFERENCES brawlers(id),
            FOREIGN KEY (brawler_b_id) REFERENCES brawlers(id)
        )
        """
    )


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _load_team_picks(conn: sqlite3.Connection, match_id: int, team: str) -> list[int]:
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


def load_match_rows(conn: sqlite3.Connection, mode_id: int | None = None) -> list[MatchRow]:
    if not _table_exists(conn, "training_matches"):
        return []

    query = """
        SELECT id, map_id, mode_id, winning_team
        FROM training_matches
        WHERE winning_team IN ('blue', 'red')
    """
    params: tuple[int, ...] = ()
    if mode_id is not None:
        query += " AND mode_id = ?"
        params = (mode_id,)

    rows = conn.execute(query, params).fetchall()
    matches: list[MatchRow] = []
    for match_id, map_id, row_mode_id, winning_team in rows:
        blue_picks = _load_team_picks(conn, int(match_id), "blue")
        red_picks = _load_team_picks(conn, int(match_id), "red")
        if len(blue_picks) != 3 or len(red_picks) != 3:
            continue
        if len(set(blue_picks)) != 3 or len(set(red_picks)) != 3:
            continue
        matches.append(
            MatchRow(
                map_id=int(map_id),
                mode_id=int(row_mode_id),
                winning_team=str(winning_team),
                blue_picks=blue_picks,
                red_picks=red_picks,
            )
        )
    return matches


def _win_rate(wins: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return wins / total


def _centered_score(wins: int, total: int, baseline: float) -> float:
    if total <= 0:
        return 0.0
    return _win_rate(wins, total) - baseline


def compute_aggregates(matches: list[MatchRow]) -> tuple[
    dict[tuple[int, int, int], tuple[float, int, float]],
    dict[tuple[int, int, int, int], tuple[float, int]],
    dict[tuple[int, int, int, int], tuple[float, int]],
    set[int],
]:
    """
    Return brawler_stats, counters, synergies, and all brawler ids seen.

    brawler_stats key: (brawler_id, map_id, mode_id) -> (win_rate, sample_size, pick_rate)
    counter key: (blue_id, red_id, map_id, mode_id) -> (counter_score, sample_size)
    synergy key: (a_id, b_id, map_id, mode_id) with a_id < b_id -> (synergy_score, sample_size)
    """
    brawler_wins: dict[tuple[int, int, int], int] = defaultdict(int)
    brawler_totals: dict[tuple[int, int, int], int] = defaultdict(int)
    counter_wins: dict[tuple[int, int, int, int], int] = defaultdict(int)
    counter_totals: dict[tuple[int, int, int, int], int] = defaultdict(int)
    synergy_wins: dict[tuple[int, int, int, int], int] = defaultdict(int)
    synergy_totals: dict[tuple[int, int, int, int], int] = defaultdict(int)
    baseline_blue_wins: dict[tuple[int, int], int] = defaultdict(int)
    baseline_totals: dict[tuple[int, int], int] = defaultdict(int)
    map_mode_match_counts: dict[tuple[int, int], int] = defaultdict(int)
    all_brawler_ids: set[int] = set()

    for match in matches:
        blue_won = match.winning_team == "blue"
        map_mode = (match.map_id, match.mode_id)
        map_mode_match_counts[map_mode] += 1
        baseline_totals[map_mode] += 1
        if blue_won:
            baseline_blue_wins[map_mode] += 1

        for brawler_id in match.blue_picks:
            all_brawler_ids.add(brawler_id)
            key = (brawler_id, match.map_id, match.mode_id)
            brawler_totals[key] += 1
            if blue_won:
                brawler_wins[key] += 1

        for brawler_id in match.red_picks:
            all_brawler_ids.add(brawler_id)
            key = (brawler_id, match.map_id, match.mode_id)
            brawler_totals[key] += 1
            if not blue_won:
                brawler_wins[key] += 1

        for blue_id in match.blue_picks:
            for red_id in match.red_picks:
                ckey = (blue_id, red_id, match.map_id, match.mode_id)
                counter_totals[ckey] += 1
                if blue_won:
                    counter_wins[ckey] += 1

        for a_id, b_id in combinations(sorted(set(match.blue_picks)), 2):
            if a_id >= b_id:
                continue
            skey = (a_id, b_id, match.map_id, match.mode_id)
            synergy_totals[skey] += 1
            if blue_won:
                synergy_wins[skey] += 1

    brawler_stats: dict[tuple[int, int, int], tuple[float, int, float]] = {}
    for key, total in brawler_totals.items():
        wins = brawler_wins[key]
        brawler_id, map_id, mode_id = key
        match_count = map_mode_match_counts[(map_id, mode_id)]
        pick_rate = total / match_count if match_count > 0 else 0.0
        brawler_stats[key] = (_win_rate(wins, total), total, pick_rate)

    counters: dict[tuple[int, int, int, int], tuple[float, int]] = {}
    for key, total in counter_totals.items():
        blue_id, red_id, map_id, mode_id = key
        baseline = _win_rate(baseline_blue_wins[(map_id, mode_id)], baseline_totals[(map_id, mode_id)])
        counters[key] = (_centered_score(counter_wins[key], total, baseline), total)

    synergies: dict[tuple[int, int, int, int], tuple[float, int]] = {}
    for key, total in synergy_totals.items():
        a_id, b_id, map_id, mode_id = key
        baseline = _win_rate(baseline_blue_wins[(map_id, mode_id)], baseline_totals[(map_id, mode_id)])
        synergies[key] = (_centered_score(synergy_wins[key], total, baseline), total)

    return brawler_stats, counters, synergies, all_brawler_ids


def _load_existing_brawler_names(conn: sqlite3.Connection) -> dict[int, str]:
    if not _table_exists(conn, "brawlers"):
        return {}
    rows = conn.execute("SELECT id, name FROM brawlers").fetchall()
    return {int(row[0]): str(row[1]) for row in rows}


def _upsert_brawlers(conn: sqlite3.Connection, brawler_ids: set[int]) -> None:
    existing = _load_existing_brawler_names(conn)
    for brawler_id in sorted(brawler_ids):
        name = existing.get(brawler_id) or f"Brawler {brawler_id}"
        conn.execute(
            """
            INSERT INTO brawlers (id, name)
            VALUES (?, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (brawler_id, name),
        )


def _write_aggregates(
    conn: sqlite3.Connection,
    *,
    mode_id: int | None,
    brawler_stats: dict[tuple[int, int, int], tuple[float, int, float]],
    counters: dict[tuple[int, int, int, int], tuple[float, int]],
    synergies: dict[tuple[int, int, int, int], tuple[float, int]],
) -> tuple[int, int, int]:
    if mode_id is None:
        conn.execute("DELETE FROM brawler_stats")
        conn.execute("DELETE FROM counters")
        conn.execute("DELETE FROM synergies")
    else:
        conn.execute("DELETE FROM brawler_stats WHERE game_mode_id = ?", (mode_id,))
        conn.execute("DELETE FROM counters WHERE game_mode_id = ?", (mode_id,))
        conn.execute("DELETE FROM synergies WHERE game_mode_id = ?", (mode_id,))

    stats_rows = 0
    for (brawler_id, map_id, row_mode_id), (win_rate, sample_size, pick_rate) in brawler_stats.items():
        if mode_id is not None and row_mode_id != mode_id:
            continue
        conn.execute(
            """
            INSERT INTO brawler_stats (
                brawler_id, map_id, game_mode_id, win_rate, sample_size, pick_rate
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (brawler_id, map_id, row_mode_id, win_rate, sample_size, pick_rate),
        )
        stats_rows += 1

    counter_rows = 0
    for (blue_id, red_id, map_id, row_mode_id), (score, sample_size) in counters.items():
        if mode_id is not None and row_mode_id != mode_id:
            continue
        conn.execute(
            """
            INSERT INTO counters (
                brawler_a_id, brawler_b_id, map_id, game_mode_id, counter_score, sample_size
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (blue_id, red_id, map_id, row_mode_id, score, sample_size),
        )
        counter_rows += 1

    synergy_rows = 0
    for (a_id, b_id, map_id, row_mode_id), (score, sample_size) in synergies.items():
        if mode_id is not None and row_mode_id != mode_id:
            continue
        conn.execute(
            """
            INSERT INTO synergies (
                brawler_a_id, brawler_b_id, map_id, game_mode_id, synergy_score, sample_size
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (a_id, b_id, map_id, row_mode_id, score, sample_size),
        )
        synergy_rows += 1

    return stats_rows, counter_rows, synergy_rows


def run_aggregation(
    conn: sqlite3.Connection,
    *,
    mode_id: int | None = None,
) -> AggregationResult:
    """Recompute aggregated tables from training_matches and record a meta snapshot."""
    ensure_aggregated_schema(conn)
    matches = load_match_rows(conn, mode_id=mode_id)
    if not matches:
        logger.warning("No complete training matches found for aggregation (mode_id=%s)", mode_id)
        snapshot = record_snapshot(
            conn,
            match_count=0,
            mode_ids=[],
            brawler_stats_rows=0,
            counter_rows=0,
            synergy_rows=0,
        )
        return AggregationResult(
            match_count=0,
            mode_ids=[],
            brawler_stats_rows=0,
            counter_rows=0,
            synergy_rows=0,
            snapshot_id=snapshot.id,
        )

    brawler_stats, counters, synergies, brawler_ids = compute_aggregates(matches)
    _upsert_brawlers(conn, brawler_ids)
    stats_rows, counter_rows, synergy_rows = _write_aggregates(
        conn,
        mode_id=mode_id,
        brawler_stats=brawler_stats,
        counters=counters,
        synergies=synergies,
    )
    mode_ids = sorted({match.mode_id for match in matches})
    snapshot = record_snapshot(
        conn,
        match_count=len(matches),
        mode_ids=mode_ids,
        brawler_stats_rows=stats_rows,
        counter_rows=counter_rows,
        synergy_rows=synergy_rows,
    )
    logger.info(
        "Aggregation complete: matches=%s modes=%s stats=%s counters=%s synergies=%s snapshot_id=%s",
        len(matches),
        mode_ids,
        stats_rows,
        counter_rows,
        synergy_rows,
        snapshot.id,
    )
    return AggregationResult(
        match_count=len(matches),
        mode_ids=mode_ids,
        brawler_stats_rows=stats_rows,
        counter_rows=counter_rows,
        synergy_rows=synergy_rows,
        snapshot_id=snapshot.id,
    )


def aggregate_database(db_path: Path | None = None, *, mode_id: int | None = None) -> AggregationResult:
    path = db_path or resolve_db_path()
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys=ON;")
        result = run_aggregation(conn, mode_id=mode_id)
        conn.commit()
        return result


__all__ = [
    "AggregationResult",
    "MatchRow",
    "aggregate_database",
    "compute_aggregates",
    "ensure_aggregated_schema",
    "load_match_rows",
    "resolve_db_path",
    "run_aggregation",
]
