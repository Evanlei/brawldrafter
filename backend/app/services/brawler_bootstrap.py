"""Seed and refresh brawler display names from the Brawl Stars API."""

from __future__ import annotations

import logging
import sqlite3

from app.services.aggregation import ensure_aggregated_schema, resolve_db_path
from app.services.brawlstars_client import fetch_brawler_name_map

logger = logging.getLogger(__name__)


def sync_brawler_names(conn: sqlite3.Connection | None = None) -> int:
    """
    Upsert brawler id/name rows from the official API.

    Returns the number of rows written.
    """
    names = fetch_brawler_name_map()
    if not names:
        logger.warning("No brawler names returned from API")
        return 0

    if conn is None:
        db_path = resolve_db_path()
        with sqlite3.connect(db_path) as owned:
            owned.execute("PRAGMA foreign_keys=ON;")
            ensure_aggregated_schema(owned)
            count = _upsert_names(owned, names)
            owned.commit()
            return count

    ensure_aggregated_schema(conn)
    return _upsert_names(conn, names)


def _upsert_names(conn: sqlite3.Connection, names: dict[int, str]) -> int:
    written = 0
    for brawler_id, name in sorted(names.items()):
        conn.execute(
            """
            INSERT INTO brawlers (id, name)
            VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET name = excluded.name
            """,
            (brawler_id, name),
        )
        written += 1
    logger.info("Upserted %s brawler names", written)
    return written


__all__ = ["sync_brawler_names"]
