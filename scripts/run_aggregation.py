#!/usr/bin/env python3
"""Recompute brawler_stats, counters, and synergies from training_matches."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.aggregation import aggregate_database, resolve_db_path  # noqa: E402


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate training match data into meta tables.")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="SQLite path (default: from DATABASE_URL in .env)",
    )
    parser.add_argument(
        "--mode-id",
        type=int,
        default=None,
        help="Re-aggregate only this game mode (default: all modes)",
    )
    return parser.parse_args()


def main() -> None:
    setup_logging()
    args = parse_args()
    db_path = args.db_path or resolve_db_path()
    logging.info("Aggregating from %s (mode_id=%s)", db_path, args.mode_id)
    result = aggregate_database(db_path, mode_id=args.mode_id)
    print(
        f"Done. matches={result.match_count} modes={result.mode_ids} "
        f"stats={result.brawler_stats_rows} counters={result.counter_rows} "
        f"synergies={result.synergy_rows} snapshot_id={result.snapshot_id}"
    )


if __name__ == "__main__":
    main()
