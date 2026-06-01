"""Shared pytest fixtures."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("BRAWLSTARS_API_KEY", "test-key")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_brawldrafter.db")
os.environ.setdefault("FRONTEND_ORIGIN", "http://localhost:5173")


def _init_training_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS game_modes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS maps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            game_mode_id INTEGER NOT NULL,
            UNIQUE(name, game_mode_id)
        );
        CREATE TABLE IF NOT EXISTS training_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_fingerprint TEXT NOT NULL UNIQUE,
            source_player_tag TEXT NOT NULL,
            played_at TEXT NOT NULL,
            map_id INTEGER NOT NULL,
            mode_id INTEGER NOT NULL,
            winning_team TEXT NOT NULL CHECK(winning_team IN ('blue', 'red', 'draw'))
        );
        CREATE TABLE IF NOT EXISTS training_match_brawlers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            brawler_id INTEGER NOT NULL,
            team TEXT NOT NULL CHECK(team IN ('blue', 'red')),
            pick_order INTEGER NOT NULL CHECK(pick_order BETWEEN 1 AND 3),
            UNIQUE(match_id, team, pick_order)
        );
        """
    )


def _insert_match(
    conn: sqlite3.Connection,
    *,
    fingerprint: str,
    map_id: int,
    mode_id: int,
    winning_team: str,
    blue_ids: list[int],
    red_ids: list[int],
) -> None:
    cur = conn.execute(
        """
        INSERT INTO training_matches (
            match_fingerprint, source_player_tag, played_at,
            map_id, mode_id, winning_team
        )
        VALUES (?, '#TEST', '20260101T120000.000Z', ?, ?, ?)
        """,
        (fingerprint, map_id, mode_id, winning_team),
    )
    match_id = int(cur.lastrowid)
    for idx, brawler_id in enumerate(blue_ids, start=1):
        conn.execute(
            """
            INSERT INTO training_match_brawlers(match_id, brawler_id, team, pick_order)
            VALUES (?, ?, 'blue', ?)
            """,
            (match_id, brawler_id, idx),
        )
    for idx, brawler_id in enumerate(red_ids, start=1):
        conn.execute(
            """
            INSERT INTO training_match_brawlers(match_id, brawler_id, team, pick_order)
            VALUES (?, ?, 'red', ?)
            """,
            (match_id, brawler_id, idx),
        )


@pytest.fixture
def sample_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """SQLite DB with synthetic matches, aggregated stats, and brawler names."""
    db_path = tmp_path / "sample.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    from app.core.config import get_settings

    get_settings.cache_clear()

    with sqlite3.connect(db_path) as conn:
        _init_training_schema(conn)
        conn.execute("INSERT INTO game_modes(id, name) VALUES (1, 'brawlBall')")
        conn.execute("INSERT INTO maps(id, name, game_mode_id) VALUES (1, 'Test Map', 1)")

        # Brawler 1 wins often on blue; brawler 5 counters brawler 9 on this map.
        scenarios = [
            ("m1", "blue", [1, 2, 3], [7, 8, 9]),
            ("m2", "blue", [1, 2, 4], [7, 8, 9]),
            ("m3", "blue", [1, 3, 4], [7, 8, 9]),
            ("m4", "red", [5, 6, 7], [1, 8, 9]),
            ("m5", "blue", [1, 5, 6], [7, 8, 9]),
            ("m6", "blue", [1, 2, 5], [7, 8, 9]),
        ]
        for fp, winner, blue, red in scenarios:
            _insert_match(
                conn,
                fingerprint=fp,
                map_id=1,
                mode_id=1,
                winning_team=winner,
                blue_ids=blue,
                red_ids=red,
            )

        from app.services.aggregation import run_aggregation

        run_aggregation(conn)
        conn.execute("UPDATE brawlers SET name = 'Tara' WHERE id = 1")
        conn.execute("UPDATE brawlers SET name = 'Shelly' WHERE id = 5")
        conn.commit()

    def _db_path_override() -> Path:
        return db_path

    monkeypatch.setattr("app.services.recommendation._resolve_db_path", _db_path_override)
    monkeypatch.setattr("app.services.aggregation.resolve_db_path", _db_path_override)
    monkeypatch.setattr("app.services.catalog_service.resolve_db_path", _db_path_override)

    from app.core.config import get_settings

    get_settings.cache_clear()
    refreshed = get_settings()
    monkeypatch.setattr("app.core.config.settings", refreshed)
    monkeypatch.setattr("app.services.recommendation.settings", refreshed)

    yield db_path

    get_settings.cache_clear()


@pytest.fixture
def feature_store(sample_db: Path):
    import sqlite3

    from backend.ml.dataset import load_feature_store

    with sqlite3.connect(sample_db) as conn:
        return load_feature_store(conn, mode_id=1)
