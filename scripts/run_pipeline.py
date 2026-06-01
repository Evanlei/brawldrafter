#!/usr/bin/env python3
"""One-command pipeline: fetch → aggregate → bootstrap names → optional train all modes."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
for path in (PROJECT_ROOT, BACKEND_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.services.pipeline import run_full_pipeline  # noqa: E402


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full BrawlDrafter data pipeline.")
    parser.add_argument("--skip-fetch", action="store_true", help="Only aggregate/train.")
    parser.add_argument("--skip-aggregate", action="store_true")
    parser.add_argument("--retrain", action="store_true", help="Train DraftNet for all modes with enough data.")
    parser.add_argument("--players", type=int, default=None)
    parser.add_argument("--matches-per-player", type=int, default=None)
    parser.add_argument("--mode-id", type=int, default=None, help="Limit aggregation to one mode.")
    return parser.parse_args()


def main() -> None:
    setup_logging()
    args = parse_args()
    result = run_full_pipeline(
        fetch=not args.skip_fetch,
        aggregate=not args.skip_aggregate,
        retrain=args.retrain,
        players=args.players,
        matches_per_player=args.matches_per_player,
        mode_id=args.mode_id,
    )
    agg = result.aggregate
    print(
        "Pipeline complete.\n"
        f"  fetch_ran={result.fetch_ran}\n"
        f"  matches={agg.match_count if agg else 'n/a'}\n"
        f"  brawlers_synced={result.brawlers_synced}\n"
        f"  trained_modes={result.trained_mode_ids}\n"
        f"  train_failures={result.train_failures}"
    )


if __name__ == "__main__":
    main()
