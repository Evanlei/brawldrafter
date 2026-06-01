#!/usr/bin/env python3
"""Export game_modes, maps, and brawlers to frontend/src/data/catalog.json."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.aggregation import resolve_db_path  # noqa: E402

OUTPUT = PROJECT_ROOT / "frontend" / "src" / "data" / "catalog.json"

MODE_LABELS = {
    "brawlBall": "Brawl Ball",
    "gemGrab": "Gem Grab",
    "bounty": "Bounty",
    "heist": "Heist",
    "hotZone": "Hot Zone",
    "knockout": "Knockout",
}


def main() -> None:
    db_path = resolve_db_path()
    with sqlite3.connect(db_path) as conn:
        modes = [
            {
                "modeId": int(row[0]),
                "name": str(row[1]),
                "label": MODE_LABELS.get(str(row[1]), str(row[1])),
            }
            for row in conn.execute("SELECT id, name FROM game_modes ORDER BY id")
        ]
        maps = [
            {
                "mapId": int(row[0]),
                "name": str(row[1]),
                "modeId": int(row[2]),
            }
            for row in conn.execute(
                "SELECT id, name, game_mode_id FROM maps ORDER BY game_mode_id, name"
            )
        ]
        brawlers = [
            {"brawlerId": int(row[0]), "name": str(row[1])}
            for row in conn.execute("SELECT id, name FROM brawlers ORDER BY name, id")
        ]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps({"modes": modes, "maps": maps, "brawlers": brawlers}, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {len(modes)} modes, {len(maps)} maps, {len(brawlers)} brawlers → {OUTPUT}")


if __name__ == "__main__":
    main()
