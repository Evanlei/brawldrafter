"""Versioned metadata for aggregation runs."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class MetaSnapshot:
    id: int
    created_at: str
    match_count: int
    mode_ids: list[int]
    brawler_stats_rows: int
    counter_rows: int
    synergy_rows: int


def ensure_meta_snapshot_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meta_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            match_count INTEGER NOT NULL,
            mode_ids TEXT NOT NULL,
            brawler_stats_rows INTEGER NOT NULL,
            counter_rows INTEGER NOT NULL,
            synergy_rows INTEGER NOT NULL
        )
        """
    )


def record_snapshot(
    conn: sqlite3.Connection,
    *,
    match_count: int,
    mode_ids: list[int],
    brawler_stats_rows: int,
    counter_rows: int,
    synergy_rows: int,
) -> MetaSnapshot:
    ensure_meta_snapshot_schema(conn)
    created_at = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """
        INSERT INTO meta_snapshots (
            created_at, match_count, mode_ids,
            brawler_stats_rows, counter_rows, synergy_rows
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            created_at,
            match_count,
            json.dumps(sorted(mode_ids)),
            brawler_stats_rows,
            counter_rows,
            synergy_rows,
        ),
    )
    snapshot_id = int(cur.lastrowid)
    return MetaSnapshot(
        id=snapshot_id,
        created_at=created_at,
        match_count=match_count,
        mode_ids=sorted(mode_ids),
        brawler_stats_rows=brawler_stats_rows,
        counter_rows=counter_rows,
        synergy_rows=synergy_rows,
    )


def latest_snapshot(conn: sqlite3.Connection) -> MetaSnapshot | None:
    if not _table_exists(conn, "meta_snapshots"):
        return None
    row = conn.execute(
        """
        SELECT id, created_at, match_count, mode_ids,
               brawler_stats_rows, counter_rows, synergy_rows
        FROM meta_snapshots
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    return MetaSnapshot(
        id=int(row[0]),
        created_at=str(row[1]),
        match_count=int(row[2]),
        mode_ids=json.loads(str(row[3])),
        brawler_stats_rows=int(row[4]),
        counter_rows=int(row[5]),
        synergy_rows=int(row[6]),
    )


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


__all__ = ["MetaSnapshot", "ensure_meta_snapshot_schema", "latest_snapshot", "record_snapshot"]
