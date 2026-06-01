#!/usr/bin/env python3
"""Fetch high-ELO Brawl Stars match data for local model training."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import re
import sqlite3
import sys
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEEDS_DIR = PROJECT_ROOT / "seeds"
MASTERS_PLAYERS_PATH = SEEDS_DIR / "masters_players.json"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import settings  # noqa: E402


API_BASE = "https://api.brawlstars.com/v1"
THREE_VS_THREE_MODES = frozenset({
    "brawlBall",
    "gemGrab",
    "bounty",
    "hotZone",
    "knockout",
    "heist",
})
RANKED_BATTLE_TYPES = frozenset({"ranked", "soloRanked", "teamRanked"})
TROPHY_SEED_LIMIT = 200
_warned_missing_rank_keys: set[str] = set()


@dataclass
class VerifiedPlayer:
    tag: str
    rank_label: str
    rank_source_key: str
    elo: int | None = None
    raw_rank_value: Any = None
    extra: dict[str, Any] = field(default_factory=dict)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def _backoff_sleep(attempt: int) -> float:
    sleep_s = (2 ** (attempt + 1)) + random.uniform(0, 1)
    time.sleep(sleep_s)
    return sleep_s


def resolve_db_path() -> Path:
    db_url = settings.DATABASE_URL
    if db_url.startswith("sqlite:///"):
        raw_path = db_url.removeprefix("sqlite:///")
        path = Path(raw_path)
        if path.is_absolute():
            return path.resolve()
        return (PROJECT_ROOT / path).resolve()
    return (PROJECT_ROOT / "brawldrafter.db").resolve()


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS game_modes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS maps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            game_mode_id INTEGER NOT NULL,
            UNIQUE(name, game_mode_id),
            FOREIGN KEY(game_mode_id) REFERENCES game_modes(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS training_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_fingerprint TEXT NOT NULL UNIQUE,
            source_player_tag TEXT NOT NULL,
            played_at TEXT NOT NULL,
            map_id INTEGER NOT NULL,
            mode_id INTEGER NOT NULL,
            winning_team TEXT NOT NULL CHECK(winning_team IN ('blue', 'red', 'draw')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(map_id) REFERENCES maps(id),
            FOREIGN KEY(mode_id) REFERENCES game_modes(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS training_match_brawlers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            brawler_id INTEGER NOT NULL,
            team TEXT NOT NULL CHECK(team IN ('blue', 'red')),
            pick_order INTEGER NOT NULL CHECK(pick_order BETWEEN 1 AND 3),
            UNIQUE(match_id, team, pick_order),
            FOREIGN KEY(match_id) REFERENCES training_matches(id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()


def brawl_get(path: str, *, retries: int = 3) -> dict[str, Any]:
    url = f"{API_BASE}{path}"
    headers = {"Authorization": f"Bearer {settings.BRAWLSTARS_API_KEY}"}

    for attempt in range(retries + 1):
        req = Request(url, headers=headers, method="GET")
        try:
            with urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body)
        except HTTPError as exc:
            if exc.code == 429 and attempt < retries:
                sleep_s = _backoff_sleep(attempt)
                logging.warning("429 rate-limited on %s. Retrying in %.1fs", path, sleep_s)
                continue
            err_body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {exc.code} for {path}: {err_body}") from exc
        except URLError as exc:
            if attempt < retries:
                sleep_s = _backoff_sleep(attempt)
                logging.warning("Network error on %s (%s). Retrying in %.1fs", path, exc, sleep_s)
                continue
            raise RuntimeError(f"Network error for {path}: {exc}") from exc

    raise RuntimeError(f"Failed request after retries: {path}")


def get_or_create_mode_id(conn: sqlite3.Connection, mode_name: str) -> int:
    row = conn.execute("SELECT id FROM game_modes WHERE name = ?", (mode_name,)).fetchone()
    if row:
        return int(row[0])
    cur = conn.execute("INSERT INTO game_modes(name) VALUES (?)", (mode_name,))
    return int(cur.lastrowid)


def get_or_create_map_id(conn: sqlite3.Connection, map_name: str, mode_id: int) -> int:
    row = conn.execute(
        "SELECT id FROM maps WHERE name = ? AND game_mode_id = ?",
        (map_name, mode_id),
    ).fetchone()
    if row:
        return int(row[0])
    cur = conn.execute(
        "INSERT INTO maps(name, game_mode_id) VALUES (?, ?)",
        (map_name, mode_id),
    )
    return int(cur.lastrowid)


def normalize_tag(tag: str | None) -> str:
    if not tag:
        return ""
    return tag.strip().upper()


def is_ranked_match(battle: dict[str, Any]) -> bool:
    battle_type = battle.get("type")
    return isinstance(battle_type, str) and battle_type in RANKED_BATTLE_TYPES


def extract_played_at(item: dict[str, Any], battle: dict[str, Any]) -> str | None:
    """battleTime lives on the log item, not inside battle."""
    played_at = item.get("battleTime")
    if isinstance(played_at, str) and played_at.strip():
        return played_at.strip()
    return None


def extract_map_name(event: dict[str, Any]) -> str | None:
    raw = event.get("map")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(raw, dict):
        name = raw.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        parts = [_flatten_text(v) for v in value.values()]
        return " ".join(p for p in parts if p)
    if isinstance(value, list):
        parts = [_flatten_text(v) for v in value]
        return " ".join(p for p in parts if p)
    return str(value).lower()


def _extract_elo(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, dict):
        for key in ("elo", "trophies", "rating", "score", "points"):
            if key in value:
                parsed = _extract_elo(value[key])
                if parsed is not None:
                    return parsed
        for nested in value.values():
            parsed = _extract_elo(nested)
            if parsed is not None:
                return parsed
    return None


def _tier_text_from_value(value: Any) -> str:
    text = _flatten_text(value)
    if text:
        return text
    return ""


def is_masters_plus(tier_text: str, elo: int | None = None) -> bool:
    """Masters I/II/III or Pro."""
    t = tier_text.lower()
    if "pro" in t:
        return True
    if "master" in t:
        return True
    # Roman numerals / divisions for masters only
    if re.search(r"master[s]?\s*(i{1,3}|1|2|3)\b", t):
        return True
    return False


def _iter_rank_season_fields(obj: Any, prefix: str = "") -> list[tuple[str, Any]]:
    found: list[tuple[str, Any]] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_lower = key.lower()
            path = f"{prefix}.{key}" if prefix else key
            if "rank" in key_lower or "season" in key_lower:
                found.append((path, value))
            found.extend(_iter_rank_season_fields(value, path))
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            found.extend(_iter_rank_season_fields(value, f"{prefix}[{idx}]"))
    return found


def _warn_missing_rank_fields(tag: str, profile: dict[str, Any]) -> None:
    norm = normalize_tag(tag)
    if norm in _warned_missing_rank_keys:
        return
    _warned_missing_rank_keys.add(norm)
    logging.warning(
        "%s | no rank/season fields found in player profile; top-level keys: %s",
        tag,
        list(profile.keys()),
    )


def parse_rank_from_profile(tag: str, profile: dict[str, Any]) -> VerifiedPlayer | None:
    """Inspect profile JSON for ranked season data without assuming a fixed field name."""
    candidates = _iter_rank_season_fields(profile)
    if not candidates:
        _warn_missing_rank_fields(tag, profile)
        return None

    best: VerifiedPlayer | None = None
    for key_path, value in candidates:
        tier_text = _tier_text_from_value(value)
        elo = _extract_elo(value)
        if not tier_text and elo is None:
            continue
        if not is_masters_plus(tier_text, elo):
            continue
        label = tier_text or (f"elo={elo}" if elo is not None else key_path)
        verified = VerifiedPlayer(
            tag=tag.strip(),
            rank_label=label,
            rank_source_key=key_path,
            elo=elo,
            raw_rank_value=value,
        )
        if best is None:
            best = verified
        elif "pro" in label and "pro" not in best.rank_label:
            best = verified
    return best


def fetch_player_profile(tag: str) -> dict[str, Any]:
    encoded_tag = quote(tag, safe="")
    payload = brawl_get(f"/players/{encoded_tag}")
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected player profile payload for {tag}")
    return payload


def verify_player_rank(tag: str) -> VerifiedPlayer | None:
    try:
        profile = fetch_player_profile(tag)
    except RuntimeError as exc:
        logging.warning("Profile lookup failed for %s: %s", tag, exc)
        return None
    return parse_rank_from_profile(tag, profile)


def load_masters_players_file() -> dict[str, VerifiedPlayer]:
    if not MASTERS_PLAYERS_PATH.is_file():
        return {}

    try:
        raw = json.loads(MASTERS_PLAYERS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logging.warning("Could not parse %s: %s", MASTERS_PLAYERS_PATH, exc)
        return {}

    players_raw = raw.get("players", raw if isinstance(raw, list) else [])
    verified: dict[str, VerifiedPlayer] = {}
    if not isinstance(players_raw, list):
        return verified

    for row in players_raw:
        if not isinstance(row, dict):
            continue
        tag = row.get("tag")
        if not isinstance(tag, str) or not tag.strip():
            continue
        norm = normalize_tag(tag)
        verified[norm] = VerifiedPlayer(
            tag=tag.strip(),
            rank_label=str(row.get("rank_label", "masters")),
            rank_source_key=str(row.get("rank_source_key", "seed_file")),
            elo=row.get("elo"),
            raw_rank_value=row.get("raw_rank_value"),
            extra={k: v for k, v in row.items() if k not in {"tag", "rank_label", "rank_source_key", "elo", "raw_rank_value"}},
        )
    return verified


def _player_to_json(player: VerifiedPlayer) -> dict[str, Any]:
    row = asdict(player)
    raw = row.get("raw_rank_value")
    try:
        json.dumps(raw)
    except TypeError:
        row["raw_rank_value"] = str(raw)
    return row


def save_masters_players_file(verified: dict[str, VerifiedPlayer]) -> None:
    SEEDS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "players": [
            _player_to_json(player)
            for player in sorted(verified.values(), key=lambda p: normalize_tag(p.tag))
        ],
    }
    MASTERS_PLAYERS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logging.info("Wrote %s verified Masters+ players to %s", len(verified), MASTERS_PLAYERS_PATH)


def fetch_trophy_leaderboard_tags(limit: int = TROPHY_SEED_LIMIT) -> list[str]:
    payload = brawl_get("/rankings/global/players")
    items = payload.get("items", [])
    if not isinstance(items, list):
        logging.warning("Trophy leaderboard returned no items list")
        return []

    tags: list[str] = []
    for row in items[:limit]:
        if not isinstance(row, dict):
            continue
        tag = row.get("tag")
        if isinstance(tag, str) and tag.strip():
            tags.append(tag.strip())
    logging.info("Trophy leaderboard seed pool: %s tags", len(tags))
    return tags


def discover_player_tags(*, max_players: int, seed_pool_limit: int = TROPHY_SEED_LIMIT) -> dict[str, VerifiedPlayer]:
    """
    Steps 1–2 (+ load persisted seeds):
      - Load seeds/masters_players.json first
      - Seed from trophy leaderboard
      - Verify each tag via player profile (Masters I+ or Pro)
    """
    verified = load_masters_players_file()
    logging.info("Loaded %s verified players from %s", len(verified), MASTERS_PLAYERS_PATH)

    if len(verified) >= max_players:
        return {k: verified[k] for k in list(verified.keys())[:max_players]}

    seen = set(verified.keys())
    seed_tags: list[str] = []
    for player in verified.values():
        seed_tags.append(player.tag)

    for tag in fetch_trophy_leaderboard_tags(seed_pool_limit):
        norm = normalize_tag(tag)
        if norm in seen:
            continue
        seen.add(norm)
        seed_tags.append(tag)

    logging.info("Verifying ranks for %s seed tags (target %s Masters+ players)", len(seed_tags), max_players)
    checked = 0
    for tag in seed_tags:
        if len(verified) >= max_players:
            break
        norm = normalize_tag(tag)
        if norm in verified:
            continue
        checked += 1
        player = verify_player_rank(tag)
        if player:
            verified[norm] = player
            logging.info(
                "Verified Masters+ %s | rank=%s | source=%s | elo=%s",
                player.tag,
                player.rank_label,
                player.rank_source_key,
                player.elo,
            )
        time.sleep(0.12)

    logging.info(
        "Discovery complete: %s verified Masters+ players (%s profile checks)",
        len(verified),
        checked,
    )
    return {k: verified[k] for k in list(verified.keys())[:max_players]}


def normalize_comp_teams(
    source_tag: str,
    teams: list[list[dict[str, Any]]],
    result: str,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]] | None:
    """
    Normalize so the winning composition is always blue and the loser is red.

    If the source player won, their team becomes blue; if they lost, the opponent becomes blue.
    """
    if result == "draw":
        return "draw", teams[0], teams[1]
    if result not in {"victory", "defeat"}:
        return None

    source_team_idx: int | None = None
    for idx, team in enumerate(teams):
        for player in team:
            if normalize_tag(player.get("tag")) == normalize_tag(source_tag):
                source_team_idx = idx
                break
        if source_team_idx is not None:
            break

    if source_team_idx is None:
        return None

    if result == "victory":
        winner_idx, loser_idx = source_team_idx, 1 - source_team_idx
    else:
        winner_idx, loser_idx = 1 - source_team_idx, source_team_idx

    return "blue", teams[winner_idx], teams[loser_idx]


def build_match_fingerprint(
    played_at: str,
    mode_name: str,
    map_name: str,
    blue_ids: list[int],
    red_ids: list[int],
    winning_team: str,
) -> str:
    payload = "|".join(
        [
            played_at,
            mode_name,
            map_name,
            ",".join(map(str, sorted(blue_ids))),
            ",".join(map(str, sorted(red_ids))),
            winning_team,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def extract_three_brawler_ids(team: list[dict[str, Any]]) -> list[int] | None:
    if len(team) != 3:
        return None
    ids: list[int] = []
    for player in team:
        brawler = player.get("brawler") or {}
        brawler_id = brawler.get("id")
        if not isinstance(brawler_id, int):
            return None
        ids.append(brawler_id)
    return ids


def extract_opponent_tags(items: list[Any], source_tag: str) -> set[str]:
    """Collect opponent tags from battle log items for snowball expansion."""
    opponents: set[str] = set()
    source_norm = normalize_tag(source_tag)
    for item in items:
        if not isinstance(item, dict):
            continue
        battle = item.get("battle") or {}
        if not isinstance(battle, dict):
            continue
        teams = battle.get("teams")
        if not isinstance(teams, list):
            continue
        for team in teams:
            if not isinstance(team, list):
                continue
            for player in team:
                if not isinstance(player, dict):
                    continue
                tag = player.get("tag")
                if isinstance(tag, str) and tag.strip() and normalize_tag(tag) != source_norm:
                    opponents.add(tag.strip())
    return opponents


def insert_match(
    conn: sqlite3.Connection,
    source_player_tag: str,
    played_at: str,
    map_id: int,
    mode_id: int,
    winning_team: str,
    blue_ids: list[int],
    red_ids: list[int],
    fingerprint: str,
) -> bool:
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO training_matches
            (match_fingerprint, source_player_tag, played_at, map_id, mode_id, winning_team)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (fingerprint, source_player_tag, played_at, map_id, mode_id, winning_team),
    )
    if cur.rowcount == 0:
        return False

    match_id = int(cur.lastrowid or 0)
    if match_id <= 0:
        return False
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
    return True


def process_player_battlelog(
    conn: sqlite3.Connection, player_tag: str, max_matches: int
) -> tuple[int, int, int, set[str]]:
    encoded_tag = quote(player_tag, safe="")
    payload = brawl_get(f"/players/{encoded_tag}/battlelog")
    items = payload.get("items", [])
    if not isinstance(items, list):
        logging.warning("%s battlelog returned no items list", player_tag)
        return 0, 0, 0, set()

    opponents = extract_opponent_tags(items, player_tag)
    inserted = 0
    ranked_seen = 0
    stored = 0

    for item in items:
        if not isinstance(item, dict):
            continue
        if stored >= max_matches:
            break

        battle = item.get("battle") or {}
        if not isinstance(battle, dict) or not is_ranked_match(battle):
            continue

        ranked_seen += 1
        event = item.get("event") or {}
        if not isinstance(event, dict):
            continue

        teams = battle.get("teams")
        result = battle.get("result")
        mode_name = battle.get("mode") or event.get("mode")
        map_name = extract_map_name(event)
        played_at = extract_played_at(item, battle)

        if not (isinstance(teams, list) and len(teams) == 2):
            continue
        if not (isinstance(mode_name, str) and map_name and played_at):
            continue
        if mode_name not in THREE_VS_THREE_MODES:
            continue

        normalized = normalize_comp_teams(player_tag, teams, result)
        if normalized is None:
            continue
        winning_team, blue_team, red_team = normalized
        blue_ids = extract_three_brawler_ids(blue_team)
        red_ids = extract_three_brawler_ids(red_team)
        if blue_ids is None or red_ids is None:
            continue

        mode_id = get_or_create_mode_id(conn, mode_name)
        map_id = get_or_create_map_id(conn, map_name, mode_id)
        fingerprint = build_match_fingerprint(
            played_at, mode_name, map_name, blue_ids, red_ids, winning_team
        )

        if insert_match(
            conn=conn,
            source_player_tag=player_tag,
            played_at=played_at,
            map_id=map_id,
            mode_id=mode_id,
            winning_team=winning_team,
            blue_ids=blue_ids,
            red_ids=red_ids,
            fingerprint=fingerprint,
        ):
            inserted += 1
        stored += 1

    return ranked_seen, stored, inserted, opponents


def _try_add_verified_player(
    verified: dict[str, VerifiedPlayer],
    tag: str,
    *,
    max_players: int,
) -> VerifiedPlayer | None:
    norm = normalize_tag(tag)
    if norm in verified or len(verified) >= max_players:
        return verified.get(norm)
    player = verify_player_rank(tag)
    if player:
        verified[norm] = player
        logging.info(
            "Snowball verified Masters+ %s | rank=%s | source=%s",
            player.tag,
            player.rank_label,
            player.rank_source_key,
        )
    time.sleep(0.12)
    return player


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch and store Masters+ ranked training matches.")
    parser.add_argument(
        "--players",
        type=int,
        default=200,
        help="Max unique verified Masters+ players in the pool (default: 200).",
    )
    parser.add_argument(
        "--matches-per-player",
        type=int,
        default=25,
        help="Max valid ranked 3v3 matches to store per player (default: 25).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional RNG seed.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover/verify Masters+ tags only; no battle logs or DB writes.",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.players < 1:
        raise SystemExit("--players must be >= 1")
    if args.matches_per_player < 1:
        raise SystemExit("--matches-per-player must be >= 1")


def main() -> None:
    setup_logging()
    args = parse_args()
    validate_args(args)

    if args.seed is not None:
        random.seed(args.seed)
        logging.info("Using RNG seed=%s", args.seed)

    verified = discover_player_tags(max_players=args.players)
    if not verified:
        logging.warning("No verified Masters+ players discovered. Exiting.")
        return

    if args.dry_run:
        print(f"\nDry run: {len(verified)} verified Masters+ players\n")
        for player in verified.values():
            print(
                f"  {player.tag} | rank={player.rank_label} | "
                f"source={player.rank_source_key} | elo={player.elo}"
            )
        return

    db_path = resolve_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logging.info("Using DATABASE_URL=%s", settings.DATABASE_URL)
    logging.info("Resolved SQLite path: %s", db_path)

    scrape_queue: deque[str] = deque(player.tag for player in verified.values())
    scraped_norm: set[str] = set()
    pending_opponents: deque[str] = deque()

    total_ranked_seen = 0
    total_stored = 0
    total_inserted = 0
    player_attempts = 0
    player_failures = 0
    started = time.time()

    with sqlite3.connect(db_path) as conn:
        init_db(conn)

        while scrape_queue:
            tag = scrape_queue.popleft()
            norm = normalize_tag(tag)
            if norm in scraped_norm:
                continue
            scraped_norm.add(norm)

            player_attempts += 1
            try:
                ranked_seen, stored, inserted, opponents = process_player_battlelog(
                    conn, tag, args.matches_per_player
                )
                total_ranked_seen += ranked_seen
                total_stored += stored
                total_inserted += inserted
                conn.commit()
                logging.info(
                    "[%s] %s | ranked=%s stored=%s inserted=%s total_inserted=%s opponents=%s",
                    len(scraped_norm),
                    tag,
                    ranked_seen,
                    stored,
                    inserted,
                    total_inserted,
                    len(opponents),
                )

                for opponent_tag in opponents:
                    opp_norm = normalize_tag(opponent_tag)
                    if opp_norm in verified or opp_norm in scraped_norm:
                        continue
                    if len(verified) >= args.players:
                        break
                    pending_opponents.append(opponent_tag)

                while pending_opponents and len(verified) < args.players:
                    opp_tag = pending_opponents.popleft()
                    added = _try_add_verified_player(verified, opp_tag, max_players=args.players)
                    if added and normalize_tag(added.tag) not in scraped_norm:
                        scrape_queue.append(added.tag)

                time.sleep(0.15)
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                player_failures += 1
                logging.exception("[%s] %s | failed: %s", len(scraped_norm), tag, exc)

            if player_attempts > 0 and (player_failures / player_attempts) > 0.5:
                logging.error(
                    "Aborting early: %.0f%% of player battlelog fetches failed (%s/%s)",
                    100 * player_failures / player_attempts,
                    player_failures,
                    player_attempts,
                )
                break

    save_masters_players_file(verified)
    elapsed = time.time() - started
    logging.info(
        "Done. verified=%s scraped=%s ranked_seen=%s stored=%s inserted=%s failures=%s/%s elapsed=%.1fs",
        len(verified),
        len(scraped_norm),
        total_ranked_seen,
        total_stored,
        total_inserted,
        player_failures,
        player_attempts,
        elapsed,
    )


if __name__ == "__main__":
    main()
