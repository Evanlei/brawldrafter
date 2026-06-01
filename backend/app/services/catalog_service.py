"""Read game modes, maps, and brawlers for public catalog endpoints."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.services.aggregation import resolve_db_path

MODE_LABELS = {
    "brawlBall": "Brawl Ball",
    "gemGrab": "Gem Grab",
    "bounty": "Bounty",
    "heist": "Heist",
    "hotZone": "Hot Zone",
    "knockout": "Knockout",
}


@dataclass(frozen=True)
class ModeRow:
    mode_id: int
    name: str
    label: str


@dataclass(frozen=True)
class MapRow:
    map_id: int
    name: str
    mode_id: int


@dataclass(frozen=True)
class BrawlerRow:
    brawler_id: int
    name: str


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def list_modes(conn: sqlite3.Connection) -> list[ModeRow]:
    if not _table_exists(conn, "game_modes"):
        return []
    rows = conn.execute("SELECT id, name FROM game_modes ORDER BY id").fetchall()
    return [
        ModeRow(
            mode_id=int(row[0]),
            name=str(row[1]),
            label=MODE_LABELS.get(str(row[1]), str(row[1])),
        )
        for row in rows
    ]


def list_maps(conn: sqlite3.Connection, *, mode_id: int | None = None) -> list[MapRow]:
    if not _table_exists(conn, "maps"):
        return []
    if mode_id is None:
        rows = conn.execute(
            "SELECT id, name, game_mode_id FROM maps ORDER BY game_mode_id, name"
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, name, game_mode_id
            FROM maps
            WHERE game_mode_id = ?
            ORDER BY name
            """,
            (mode_id,),
        ).fetchall()
    return [
        MapRow(map_id=int(row[0]), name=str(row[1]), mode_id=int(row[2]))
        for row in rows
    ]


def list_brawlers(conn: sqlite3.Connection) -> list[BrawlerRow]:
    if not _table_exists(conn, "brawlers"):
        return []
    rows = conn.execute("SELECT id, name FROM brawlers ORDER BY name, id").fetchall()
    return [BrawlerRow(brawler_id=int(row[0]), name=str(row[1])) for row in rows]


def with_catalog_connection():
    db_path = resolve_db_path()
    return sqlite3.connect(db_path)


__all__ = [
    "BrawlerRow",
    "MapRow",
    "ModeRow",
    "list_brawlers",
    "list_maps",
    "list_modes",
    "with_catalog_connection",
]
