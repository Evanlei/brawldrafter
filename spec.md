# BrawlDrafter — Project Specification

**Version:** 1.4
**Last Updated:** May 2026
**Stack:** React · Tailwind · FastAPI · SQLite · Python · LLM API (Claude)

---

## Changelog (v1.3 → v1.4)

- **Fixed:** `synergies` table split into two tables — `synergies` (symmetric) and `counters` (directional) — to eliminate null-polluted rows and clarify schema intent
- **Fixed:** Mode-level aggregation path defined; `brawler_stats` gains a nullable `map_id` to support both map-scoped and mode-scoped rows; `meta_snapshots` generation now queries mode-scoped rows directly
- **Fixed:** `matches.winning_team` gains `"draw"` as a valid value; draw handling defined in aggregation formulas (draws excluded from win/loss counts)
- **Fixed:** `maps` table gains a UNIQUE constraint on `(name, game_mode_id)`
- **Fixed:** `pipeline_runs` gains an index on `run_type` for status query performance
- **Fixed:** `POST /api/v1/recommendations` now validates that `map_id` belongs to `mode_id`; mismatch returns 422
- **Fixed:** LLM name→ID resolution is now explicit: the service resolves names case-insensitively after stripping whitespace; unresolved names trigger the parse-failure retry path
- **Fixed:** `GET /api/v1/stats/bulk` and `GET /api/v1/brawlers` now have explicit `Cache-Control` headers defined
- **Fixed:** Internal pipeline `/run` polling contract defined: response includes `run_id` fields; caller compares `id` to detect completion
- **Fixed:** `useDraft` unmount-vs-browser-back behavior explicitly specified; forward navigation after back is handled
- **Fixed:** Red-turn UI state fully specified (recording mode label, roster state)
- **Fixed:** Slugification spec extended to cover accented and non-ASCII characters (NFC normalize → strip diacritics → hyphenate remaining non-alphanumeric)
- **Fixed:** Recommendation panel non-pick-turn states (ban phase, Red pick turns) explicitly specified
- **Fixed:** Meta widget trending display fields fully specified
- **Fixed:** Lobby loading states specified for all async fetches
- **Fixed:** Aggregation scope defined: full recomputation for every `(brawler_id, map_id, game_mode_id)` combination touched by new ingestion rows in that run
- **Fixed:** Draw handling added to `win_rate` formula (draws excluded)
- **Fixed:** Sample size realism note added; implication for `sample_size >= 200` threshold documented
- **Fixed:** `matches.source` gains a CHECK constraint limiting values to known enum strings
- **Fixed:** Draft screen backend-unreachable behavior specified
- **Fixed:** LLM response item count validation defined (not exactly 3 → parse failure → retry → 503)
- **Fixed:** CDN portrait URL staleness strategy defined (re-seed on schedule; frontend fallback already covers gaps)
- **Added:** Local dev setup and environment variable documentation
- **Added:** Alembic migration strategy for schema changes
- **Added:** Brawl Stars API key failure handling (auth errors, quota exhaustion)
- **Added:** Error monitoring and alerting guidance
- **Added:** Map/mode scope design decision documented explicitly in meta widget and recommendation engine sections
- **Added:** High-ELO data bias explicitly documented as a known limitation
- **Added:** Battle log volume ceiling documented (25 matches/player × 200 players)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Tech Stack](#2-tech-stack)
3. [Features](#3-features)
4. [User Flow](#4-user-flow)
5. [Data Model](#5-data-model)
6. [API Endpoints](#6-api-endpoints)
7. [Folder Structure](#7-folder-structure)
8. [Architecture & Patterns](#8-architecture--patterns)
9. [Security](#9-security)
10. [Testing Strategy](#10-testing-strategy)
11. [Pipeline & Scheduler](#11-pipeline--scheduler)
12. [Local Development Setup](#12-local-development-setup)
13. [Known Limitations](#13-known-limitations)
14. [Future Considerations](#14-future-considerations)

---

## 1. Project Overview

BrawlDrafter is a web application that provides AI-powered pick and ban recommendations for Brawl Stars competitive drafting. The user selects a game mode and map, then inputs bans and picks for both teams. The app acts as a coach for the blue team, recommending the best available brawlers at each pick phase based on real match data, known counters and synergies, and meta trends.

### Core Goals

- Recommend the best blue team picks given the current draft state, map, and mode
- Surface the weekly meta on the homepage so users can arrive informed
- Stay minimal and fast — no clutter, no friction
- No user authentication for v1

### Scope Decisions (Documented)

**Map vs. mode scope in the meta widget:** The lobby meta widget operates at mode level only, because the user may not have selected a map yet when they first view it. Once a map is selected, the widget does not switch to map-level data — it remains mode-level throughout the lobby. This is a deliberate simplification. The recommendation engine, by contrast, always uses map-level stats once the draft begins. This discrepancy is intentional: the meta widget gives a general orientation, recommendations give map-specific guidance.

**High-ELO data bias:** All match data is sourced from the top 200 global-ranked players. Recommendations therefore reflect high-ELO meta, which may differ from general play. This is documented as a known limitation (see [Section 13](#13-known-limitations)), not a bug.

---

## 2. Tech Stack

### Frontend
| Technology | Purpose |
|---|---|
| React | Component-based UI framework |
| Tailwind CSS | Utility-first styling |
| Zustand | Lightweight global state for draft state |
| React Router | Page navigation (lobby → draft) |
| Vite | Dev server and build tooling |

### Backend
| Technology | Purpose |
|---|---|
| Python 3.11+ | Primary backend language |
| FastAPI | REST API framework |
| SQLite (WAL mode) | Local relational database (upgradeable to Postgres) |
| SQLAlchemy | ORM and query layer |
| Alembic | Database migrations |
| Pydantic | Request/response validation and serialization |
| httpx | Async HTTP client for Brawl Stars API calls |
| APScheduler | Cron-style pipeline scheduling |
| slowapi | Rate limiting for FastAPI (wraps limits library) |

### AI Layer
| Technology | Purpose |
|---|---|
| Anthropic Claude API | LLM for recommendation reasoning |
| Custom RAG pipeline | Retrieves relevant stats context before each LLM call |

### Hosting (Recommended)
| Service | Purpose |
|---|---|
| Vercel | Frontend deployment |
| Railway or Render | Backend (web server + separate pipeline process) |

---

## 3. Features

### Frontend Features

#### F1 — Lobby Screen
- Game mode selector (Brawl Ball, Gem Grab, Bounty, Hot Zone, Knockout, Heist)
- Map selector that filters dynamically based on selected mode
- "This Week's Meta" widget showing top picks, top bans, and top win rate brawlers for the selected mode
- First-pick team selector: user designates whether Blue or Red team has first pick before starting the draft. This determines the pick order for the entire session.
- Start Draft button — active only when both mode and map are selected

##### Lobby Loading States

All three async fetches on lobby load (modes, maps, meta widget) have explicit loading and error states:

- **Modes loading:** The mode selector renders a row of skeleton placeholder buttons (same size as real mode buttons, muted color) until the fetch resolves. If the fetch fails, the selector renders: "Could not load modes. Refresh to try again." The Start Draft button remains disabled.
- **Maps loading:** The map selector renders a skeleton list while loading. If the mode fetch succeeded but the maps fetch fails, the map selector renders: "Could not load maps for this mode." Start Draft remains disabled.
- **Meta widget loading:** Renders three skeleton stat cards while loading. If the fetch fails, renders: "Meta data unavailable. Check your connection." The rest of the lobby (mode/map/first-pick selectors) remains functional — the widget failure does not block draft start.

No full-page spinner is used. Each section fails and recovers independently.

#### F2 — Brawler Roster Panel
- Scrollable grid of all available brawlers with portrait thumbnails
- Brawler portrait images are sourced from the official Brawl Stars API CDN (`iconUrls.medium` field) and stored as URLs in the `brawlers` table during the seed step. The frontend fetches and renders them directly from those URLs.
- **Portrait fallback:** If a CDN URL returns a 404, the frontend falls back to a local portrait from `assets/brawlers/` using the brawler's slugified name as the filename key.

  **Slugification algorithm (applied in order):**
  1. Unicode NFC normalize the name
  2. Decompose diacritics and strip combining characters (e.g., "é" → "e")
  3. Lowercase the result
  4. Replace all runs of characters that are not `a-z`, `0-9`, or `-` with a single hyphen
  5. Strip leading and trailing hyphens

  Examples: `"El Primo"` → `el-primo.png`, `"8-Bit"` → `8-bit.png`, `"R-T"` → `r-t.png`, `"Stu"` → `stu.png`.

  Local fallback portraits are required, not optional, and must be present for every brawler in the seeded roster.

- Search bar to filter by name
- Brawlers grey out and become unselectable once banned or picked
- Click to select, click again to deselect

#### F3 — Draft Board
- Blue team (left) vs Red team (right) layout
- Three ban slots and three pick slots per side
- Active slot highlighted with a subtle pulsing indicator light (blue or red)
- Turn order enforced according to which team has first pick (see draft order rules below)
- Bans first (3 per side interleaved), then picks (3 per side in snake order)
- Brawler portrait populates the slot on selection

##### Draft Order Rules

**Ban phase** (always interleaved, regardless of first-pick assignment):
```
Blue ban → Red ban → Blue ban → Red ban → Blue ban → Red ban
```

**Pick phase** (snake draft — determined by which team has first pick):

If Blue has first pick:
```
Blue pick 1 → Red pick 1 → Red pick 2 → Blue pick 2 → Blue pick 3 → Red pick 3
```

If Red has first pick:
```
Red pick 1 → Blue pick 1 → Blue pick 2 → Red pick 2 → Red pick 3 → Blue pick 3
```

The first-pick team always receives pick slots 1, 4, and 5 in the sequence. The second-pick team receives slots 2, 3, and 6. The Zustand store records which team has first pick at draft start and `useDraft` derives the full turn sequence from this at initialization.

##### Red-Turn UI State

During Red team's pick turns, the app is in **recording mode** — the user is logging what the opponent picked, not making a recommendation-assisted choice. The UI signals this clearly:

- A banner above the roster reads: **"Red's turn — click to record their pick"** in red-tinted text
- The recommendation panel is hidden (not just empty — the panel element is not rendered)
- The roster remains fully interactive; clicking a non-taken brawler fills the active Red pick slot
- The active slot pulse indicator uses the red team color

During the ban phase, for both Blue and Red bans:
- A banner reads: **"Ban phase — [Blue/Red] team banning"** in the appropriate team color
- The recommendation panel is not rendered

#### F4 — Recommendation Panel
- Displays top 3 recommended picks for blue team's current turn
- Each recommendation shows: brawler name, portrait, confidence score (%), and a one-line reason (e.g. "counters Colt", "strong synergy with Poco", "first pick value on open maps")
- Updates in real time as each ban or pick is locked in
- Rendered only during Blue team's pick turns. During all other turns (ban phase, Red pick turns) the panel element is not present in the DOM — its space is reclaimed by the roster and draft board layout.
- **Loading state:** Shows three skeleton cards while the API call is in flight.
- **Error state — 503:** Displays: "Recommendations unavailable — the AI service is temporarily down. Pick manually." No spinner persists. The skeleton cards are replaced by this message.
- **Error state — network/backend unreachable:** If the fetch itself fails (no response), displays: "Could not reach the recommendation service. Check your connection." Behavior otherwise identical to 503.

##### Draft Screen — Backend Unreachable at Session Start

If the bulk stats fetch (`GET /api/v1/stats/bulk`) fails when the draft screen loads:
- The draft board renders normally (brawler roster, slots, turn indicator)
- A non-blocking banner at the top of the screen reads: "Brawler stats unavailable — recommendations may be limited"
- The recommendation panel still appears on Blue pick turns and attempts the recommendation API call; if that also fails, the panel shows the 503 error message
- The draft is still fully playable manually

If the brawler list fetch fails at draft screen load (edge case — the lobby should have already loaded it):
- The roster renders empty with a message: "Could not load brawlers. Refresh the page."
- The draft board renders but the Start Draft button on this screen is not present (you're already in the draft)
- This state should be treated as unrecoverable in v1; the user must refresh

#### F5 — Meta Widget (Homepage)
- Fetches the latest `meta_snapshots` record for the selected mode
- Displays: top 5 picks, top 5 bans, top 3 win rate brawlers, and up to 3 trending brawlers
- **Top bans caveat:** Because the Brawl Stars battle log API does not include ban data, the `top_bans` list will be empty at launch. The frontend handles this explicitly: if `top_bans` is an empty array, the top bans section is replaced with a notice: "Ban data not yet available." The section is not hidden entirely — it remains visible with the notice so users understand it is a planned feature.
- Refreshes when the user switches game mode on the lobby screen
- **Trending brawler display:** Each trending brawler card shows the brawler name, portrait, and the `delta_pick_rate` formatted as a percentage with a green up-arrow (e.g., "▲ 8.0%"). If `delta_win_rate` is also available in the payload, it is shown as a secondary line in smaller text (e.g., "Win rate ▲ 3.2%"). If `trending_up` is an empty array (first pipeline run), the trending section renders: "Not enough data yet for trends."
- **Backend unreachable:** If the meta widget fetch fails, displays: "Meta data unavailable. Check your connection." The rest of the lobby remains functional.

#### F6 — Frontend/Backend Integration
- Lobby selection (mode + map + first-pick team) passed into draft screen via router state
- All draft actions (ban, pick) fire API calls to the backend
- Recommendation panel polls or calls the recommendation endpoint after each action

---

### Backend Features

#### B1 — Database Setup
- SQLite database initialized via Alembic migrations
- `PRAGMA journal_mode=WAL;` is executed on every database connection at startup. This enables WAL (Write-Ahead Logging) mode, allowing the FastAPI web server to read data concurrently while the ingestion pipeline is writing — eliminating `database is locked` errors under normal operation.
- All tables defined as SQLAlchemy models
- Seed script populates static data: brawlers (including CDN portrait URLs), game modes, maps. See [B1a — Seed Script](#b1a--seed-script) below.
- The seed script uses upsert logic (`INSERT OR REPLACE` or equivalent) so it can be re-run safely when Supercell adds new brawlers without truncating existing data.

##### B1a — Seed Script

The seed script calls `GET /brawlers` on the Brawl Stars API (`https://api.brawlstars.com/v1/brawlers`) using Bearer Token auth to fetch the full current roster. For each brawler returned, it extracts:
- `id` (Supercell's internal ID, used as the primary key)
- `name`
- `starPowers` / `gadgets` (ignored in v1, but the API returns them)
- `iconUrls.medium` → stored as `portrait_url`

`role` and `rarity` are not returned by the `/brawlers` endpoint and must be maintained manually in a local fixture file (`seeds/brawler_roles.json`) keyed by brawler ID. The seed script merges API data with this fixture before upserting.

Game modes and maps are seeded from static fixture files (`seeds/modes.json`, `seeds/maps.json`) maintained manually, since the Brawl Stars API does not provide a maps/modes list endpoint suitable for this purpose.

**CDN URL refresh:** `portrait_url` values are stored at seed time. Supercell occasionally rotates CDN URLs. To handle this, the seed script is scheduled to run weekly (see [Section 11](#11-pipeline--scheduler)) — this keeps URLs current. The frontend's local fallback portrait covers the gap between a URL going stale and the next seed run. Stale URLs are never purged from the database manually; the weekly seed upsert overwrites them.

#### B2 — Brawl Stars API Ingestion
- Uses `httpx` to interact with `https://api.brawlstars.com/v1` via Bearer Token auth (`Authorization: Bearer <BRAWLSTARS_API_KEY>`).
- Implements exponential backoff with jitter on 429 responses. If the API returns 429, the pipeline waits and retries up to 3 times before logging a failure and moving to the next player.
- **Auth failure handling:** If the API returns 401 or 403, the pipeline logs the error with message "Brawl Stars API authentication failed — check BRAWLSTARS_API_KEY" and aborts the entire run immediately (does not continue iterating players). The `pipeline_runs` row is written with `status = "failed"` and this error message. A 401/403 on a single player request is treated as a global key failure, not a per-player skip.
- **Quota exhaustion:** If all retry attempts on a given player are exhausted (3× 429 retries), the pipeline logs a warning for that player, skips them, and continues to the next. If more than 50% of players in a single run fail due to 429s, the pipeline aborts early and records `status = "failed"` with message "Rate limit quota exhausted — more than 50% of players skipped."
- **Step 1 (Source Players):** Calls `GET /rankings/global/players` to fetch the top 200 global players. Extracts their `tag` fields.
- **Step 2 (Fetch Logs):** Iterates through the player tags. Player tags must be URL-encoded before use in request paths: use `urllib.parse.quote(tag, safe='')` to encode the tag (e.g., `#ABC123` → `%23ABC123`), then construct the path as `/players/{encoded_tag}/battlelog`. Do not use f-strings or string concatenation to insert raw tags directly into URLs — the `#` character will not be encoded and the request will return 404.
- **Step 3 (Filter & Parse):**
  - Filters out all non-3v3 modes (e.g., ignores `soloShowdown`, `duoShowdown`).
  - Extracts: map name, mode, match outcome (`victory`/`defeat`/`draw`), and the brawlers on both the blue and red teams.
  - Draw handling: matches with outcome `"draw"` are inserted into the `matches` table with `winning_team = "draw"`. During aggregation, draws are excluded from win/loss calculations — they contribute to `sample_size` and `pick_rate` but not to `win_rate`. See aggregation formulas.
  - **Note:** The Brawl Stars battle log API does not include ban data. The `was_banned` column in `match_brawlers` is reserved for future data sources (e.g., pro match imports) that do include bans. For all matches ingested from the standard battle log, `was_banned` is always `false`. As a result, `ban_rate` in `brawler_stats` will be zero until a ban-aware data source is integrated. The meta snapshot's `top_bans` field is likewise unavailable from this source alone.
- **Step 4 (Database Insertion):** Writes raw records into `matches` and `match_brawlers` tables. Deduplicates by checking for existing rows matching the match timestamp and player tag combination before inserting — running the pipeline twice on the same data will not create duplicate rows.
- **Step 5 (New Brawler Handling):** If a brawler ID encountered in the battle log does not exist in the `brawlers` table, the pipeline logs a warning and skips that match rather than inserting a record that would violate the foreign key constraint. A separate re-seed step (or the next scheduled seed run) is required to add the new brawler before those matches can be ingested.
- Logs run outcome (status, matches fetched, matches inserted, any error) to `pipeline_runs`. Each pipeline execution — whether ingestion, aggregation, or weekly snapshot — writes its own row to `pipeline_runs` with a `run_type` field identifying which phase it represents.

#### B3 — Aggregation Pipeline

Reads from raw match tables and computes per-brawler stats per map per mode, as well as per-brawler stats per mode (map-agnostic). Writes to `brawler_stats`, `synergies`, and `counters` tables using upsert logic.

**Aggregation scope:** On each run, the pipeline identifies all `(map_id, game_mode_id)` combinations that received at least one new `matches` row during the current ingestion run. It recomputes all `brawler_stats` rows for those combinations in full — not incrementally. This ensures correctness at the cost of recomputing some unchanged rows. In addition, for every `game_mode_id` touched, the pipeline recomputes the mode-scoped rows (where `map_id IS NULL`).

##### Aggregation Formulas

All formulas apply within a specific scope. Scope is either `(map_id, game_mode_id)` for map-level rows, or `(game_mode_id)` with `map_id = NULL` for mode-level rows.

**Draw exclusion:** In all win rate calculations, matches with `winning_team = "draw"` are excluded from both numerator and denominator. They are included in `sample_size` and contribute to `pick_rate` denominators.

**`win_rate`** for brawler X:
```
win_rate = (matches where X was on the winning team AND outcome != "draw")
           / (total matches where X was picked AND outcome != "draw")
```

**`pick_rate`** for brawler X:
```
pick_rate = (matches where X was picked) / (total matches in this scope)
```
This includes draw matches.

**`ban_rate`** for brawler X:
```
ban_rate = (matches where X was banned) / (total matches in this scope)
```
Will be 0.0 until a ban-aware data source is integrated.

**`synergy_score`** for pair (A, B):
```
synergy_score = win_rate(A and B on same team, draws excluded)
                - ((win_rate(A, draws excluded) + win_rate(B, draws excluded)) / 2)
```
This measures how much better A and B perform together versus their individual baselines. The formula is symmetric: the value is identical for (A, B) and (B, A). Both rows are written for query convenience. Minimum sample size of 20 co-appearances (draws excluded) required; pairs below this threshold are not written.

**`counter_score`** for pair (A countering B):
```
counter_score(A→B) = win_rate(A when B is on opposing team, draws excluded)
                     - win_rate(A overall, draws excluded)
```
Positive value means A performs better-than-baseline when facing B. The inverse row (B, A) is stored in the `counters` table with the negated value: `counter_score(B→A) = -counter_score(A→B)`. The aggregation pipeline always writes both directions for every pair. Minimum sample size of 20 head-to-head appearances (draws excluded) required.

Runs after ingestion completes each day.

#### B4 — Meta Snapshot Generator
- Runs weekly after aggregation
- Queries **mode-scoped** `brawler_stats` rows (where `map_id IS NULL`) for each `game_mode_id`. This is the intentional design: the meta widget operates at mode level.
- Computes top picks, top bans (empty until ban data is available — see B2 note), top win rates (minimum sample size of **200 matches** per brawler/mode combination to be eligible), and trending brawlers per mode. The same `sample_size >= 200` minimum applies to `top_picks` and `top_bans` candidates — brawlers below this threshold are excluded from all meta lists.
- Trending brawlers are identified by comparing the current week's `pick_rate` and `win_rate` (mode-scoped) against the most recent prior `meta_snapshots` row for the same `game_mode_id`. The `trending_up` response includes both `delta_pick_rate` and `delta_win_rate` for each trending brawler. On the first run, `trending_up` is stored as an empty array.
- Writes a new row to `meta_snapshots`

#### B5 — Recommendation Engine
- Accepts draft state as input (map, mode, first_pick_team, blue bans, red bans, blue picks, red picks, current turn)
- Server-side derives `available_brawlers` by excluding all banned and picked brawlers before querying stats. Rejects any request where a brawler ID appears in more than one of the input lists (e.g., in both `blue_picks` and `red_bans`) with a 422 error.
- **Map/mode consistency validation:** Before any draft logic, validates that the provided `map_id` belongs to the provided `mode_id` by checking the `maps` table. If the map does not belong to the mode, returns 422 with `{"detail": "map_id does not belong to mode_id"}`.
- **Turn-ownership validation:** The endpoint validates two things independently:
  1. `current_pick_number == len(blue_picks) + 1` (sequence consistency)
  2. The `current_pick_number`-th blue pick turn actually exists in the derived turn sequence for the given `first_pick_team`. The full 6-pick sequence is derived server-side from `first_pick_team` (identical logic to `useDraft`), and the endpoint checks that position `current_pick_number` in that sequence belongs to blue team. If either check fails, returns 422.
- Queries `brawler_stats` (map-scoped rows) and `synergies` / `counters` for the relevant map/mode context
- **LLM context size cap:** Before constructing the prompt, the available brawler stats table is trimmed to the top 20 brawlers by `win_rate` on this map/mode. Synergy and counter rows are filtered to only include pairs involving these top 20 brawlers. This bounds prompt token count regardless of roster size.
- Results from the recommendation engine are cached by a hash of the full request body (map, mode, all ban/pick lists, current pick number). Cache TTL is 60 seconds. Identical draft states within this window return the cached response without an additional LLM call. **Failed responses (503) are never cached** — each failure allows a fresh retry on the next request.
- Constructs a focused prompt and calls the Claude API with a 10-second timeout. If the request times out or the API returns an error, the endpoint returns 503 with `{"detail": "Recommendation service temporarily unavailable"}`. See [LLM Prompt Template](#llm-prompt-template) below.
- **LLM response parsing and name resolution:**
  1. The service attempts to parse the LLM response as a JSON array.
  2. If parsing fails (malformed JSON, extra text outside the array), this counts as a parse failure.
  3. If the array does not contain exactly 3 items, this counts as a parse failure.
  4. If parsing succeeds, the service resolves each `name` field to a `brawler_id` by performing a case-insensitive, whitespace-stripped lookup against the `brawlers` table. If any name fails to resolve, this counts as a parse failure.
  5. On any parse failure, the service retries the API call once with the same prompt. If the retry also fails any of the above checks, the endpoint returns 503.
- Returns ranked recommendations with scores and reasoning

#### B6 — REST API Endpoints
- Full set of endpoints for brawlers, maps, modes, meta, and draft recommendations
- All inputs validated with Pydantic schemas
- Rate limiting on the recommendation endpoint

---

### LLM Prompt Template

The recommendation service constructs the following prompt before calling the Claude API. Brawler names and stats are injected from the database — no raw user input ever reaches the prompt. The brawler stats table is capped at top 20 by win rate before injection (see B5).

**Prompt injection safety note:** Brawler names originate from the `brawlers` table, which is populated by the seed script from the official Brawl Stars API and the local fixture file `seeds/brawler_roles.json`. The fixture file is committed to the repository and treated as trusted input. Operators must not allow untrusted parties to modify fixture files.

```
You are a Brawl Stars competitive draft coach. Given the current draft state, recommend the 3 best picks for the blue team's current turn.

## Draft Context
- Map: {map_name}
- Mode: {mode_name}
- Blue team bans: {blue_ban_names}
- Red team bans: {red_ban_names}
- Blue team picks so far: {blue_pick_names}
- Red team picks so far: {red_pick_names}
- Blue team is now making pick #{current_pick_number}

## Available Brawler Stats (this map/mode, top 20 by win rate)
{table of available brawler names, win_rate, pick_rate, ban_rate, sample_size}

## Relevant Synergy Data
{list of (brawler_a, brawler_b, synergy_score) for blue picks paired with available brawlers}

## Relevant Counter Data
{list of (brawler, counter_score) for available brawlers vs each red team pick}

Respond with exactly 3 recommendations in this JSON format:
[
  { "name": "BrawlerName", "confidence": 0.87, "reason": "one concise sentence" },
  ...
]
Do not include any text outside the JSON array. Use brawler names exactly as they appear in the stats table above.
```

---

## 4. User Flow

```
Lobby Screen
  └── [Async] Load modes, maps, meta widget (each independently; skeleton states shown)
  └── Select game mode
  └── Select map (filtered by mode)
  └── View meta widget for selected mode
  └── Select which team has first pick (Blue or Red)
  └── Click "Start Draft"
        │
        ▼
Draft Screen
  ├── [Async] Load brawler roster and bulk stats for selected map/mode
  │     └── On failure: non-blocking banner shown; draft remains playable
  │
  ├── Ban Phase (always interleaved regardless of first pick):
  │     Blue ban → Red ban → Blue ban → Red ban → Blue ban → Red ban
  │     └── Banner: "[Blue/Red] team banning"
  │     └── User clicks brawler in roster → fills next active ban slot
  │     └── Recommendation panel NOT rendered during ban phase
  │
  └── Pick Phase (snake draft — order depends on first-pick team):
        If Blue has first pick: Blue → Red → Red → Blue → Blue → Red
        If Red has first pick:  Red → Blue → Blue → Red → Red → Blue

        Blue pick turns:
        └── Banner: "Blue team — Pick {n}"
        └── Recommendation panel renders with top 3 suggestions (skeleton → results or error)
        └── User clicks brawler in roster OR selects from recommendation panel

        Red pick turns:
        └── Banner: "Red's turn — click to record their pick" (red tint)
        └── Recommendation panel NOT rendered
        └── User manually clicks brawler to record opponent's pick

        └── Draft completes when all 6 pick slots filled

  Back navigation (lobby button or browser back):
        └── Zustand draft store is reset to initial state (see store reset rules below)
        └── User is returned to lobby with mode/map selection cleared
        └── No confirmation dialog in v1 — navigating back unconditionally discards the draft

  Forward navigation after back:
        └── If user presses browser Forward after navigating back to lobby, the draft
            screen remounts with an empty store (reset already occurred on unmount).
            The draft screen detects missing required state (no map_id/mode_id) and
            redirects the user back to the lobby rather than rendering a broken state.
```

---

## 5. Data Model

### Table: `brawlers`
The master roster of all brawlers. Seeded via the Brawl Stars API `/brawlers` endpoint, updated via re-seed when Supercell adds new brawlers.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Supercell's brawler ID from the API (not auto-increment) |
| `name` | TEXT NOT NULL | e.g. "Shelly", "El Primo", "8-Bit" |
| `role` | TEXT | e.g. "Tank", "Assassin", "Support", "Marksman" — sourced from local fixture |
| `rarity` | TEXT | e.g. "Common", "Rare", "Epic", "Legendary" — sourced from local fixture |
| `portrait_url` | TEXT | CDN URL from Brawl Stars API (`iconUrls.medium`), populated at seed time. Refreshed weekly by the scheduled seed run. |

---

### Table: `game_modes`
Static list of all playable modes.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `name` | TEXT NOT NULL UNIQUE | e.g. "Gem Grab", "Brawl Ball" |

---

### Table: `maps`
Every map, linked to its game mode.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `name` | TEXT NOT NULL | e.g. "Hard Rock Mine" |
| `game_mode_id` | INTEGER FK → `game_modes.id` | Which mode this map belongs to |

> **Uniqueness:** A UNIQUE constraint is enforced on `(name, game_mode_id)`. Two maps in different modes may share a name; two maps in the same mode may not.

---

### Table: `matches`
One row per raw match pulled from the Brawl Stars API. This is the raw data layer.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `map_id` | INTEGER FK → `maps.id` | Map the match was played on |
| `game_mode_id` | INTEGER FK → `game_modes.id` | Mode of the match |
| `winning_team` | TEXT | `"blue"`, `"red"`, or `"draw"`. CHECK constraint enforces only these three values. |
| `played_at` | DATETIME | When the match occurred |
| `source_player_tag` | TEXT | The player tag used to fetch this match — used for deduplication |
| `source` | TEXT | Source of the match data. CHECK constraint: value must be one of `"ranked"`. Reserved for future values (e.g., `"pro"`) — add new values via migration + constraint update. |

> **Deduplication key:** `(played_at, source_player_tag)`. The pipeline checks for this combination before inserting. A UNIQUE constraint on these two columns is enforced at the database level.

---

### Table: `match_brawlers`
Bridge table — which brawlers appeared in each match, on which team, in which role.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `match_id` | INTEGER FK → `matches.id` ON DELETE CASCADE | The match this row belongs to. Cascade ensures match_brawlers rows are deleted when a match row is deleted. |
| `brawler_id` | INTEGER FK → `brawlers.id` | Which brawler |
| `team` | TEXT | `"blue"` or `"red"`. CHECK constraint enforces only these values. |
| `pick_order` | INTEGER | 1–3 within the team, null if banned |
| `was_banned` | BOOLEAN | Reserved for future ban-aware data sources. Always `false` for matches ingested from the standard Brawl Stars battle log, which does not include ban information. |

---

### Table: `brawler_stats`
Aggregated win/pick/ban rates per brawler, per map (optionally), per mode. Produced by the daily pipeline. This is what the recommendation engine and meta snapshot generator query.

**Dual scope:** Each row is either map-scoped (`map_id IS NOT NULL`) or mode-scoped (`map_id IS NULL`). Map-scoped rows are used by the recommendation engine. Mode-scoped rows are used by the meta snapshot generator. Both types are produced by the aggregation pipeline.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `brawler_id` | INTEGER FK → `brawlers.id` | Which brawler |
| `map_id` | INTEGER FK → `maps.id` NULLABLE | Which map. NULL for mode-scoped rows. |
| `game_mode_id` | INTEGER FK → `game_modes.id` | Which mode |
| `win_rate` | REAL | 0.0–1.0. Draws excluded. See aggregation formulas. |
| `pick_rate` | REAL | 0.0–1.0, fraction of matches in scope where brawler was picked. Draws included. |
| `ban_rate` | REAL | 0.0–1.0, how often banned. Will be 0.0 until a ban-aware data source is integrated. |
| `sample_size` | INTEGER | Number of matches (including draws) used to compute these stats — indicates statistical reliability |
| `last_updated` | DATETIME | Timestamp of last aggregation run |

> **Uniqueness:** A UNIQUE constraint is enforced on `(brawler_id, map_id, game_mode_id)` where NULL `map_id` is treated as a distinct value (i.e., one mode-scoped row per brawler per mode). The aggregation pipeline upserts — existing rows are updated in place rather than duplicated.

---

### Table: `synergies`
Symmetric pairwise synergy scores per map per mode. Produced by the daily pipeline.

Rows are written for both `(A, B)` and `(B, A)` with identical `synergy_score` values, for query convenience. The score is symmetric by construction — see aggregation formulas.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `brawler_a_id` | INTEGER FK → `brawlers.id` | First brawler in the pair |
| `brawler_b_id` | INTEGER FK → `brawlers.id` | Second brawler in the pair |
| `map_id` | INTEGER FK → `maps.id` | Which map |
| `game_mode_id` | INTEGER FK → `game_modes.id` | Which mode |
| `synergy_score` | REAL | `win_rate(A+B together) - avg(win_rate(A), win_rate(B))`. Draws excluded from all win rates. Positive = good together. Identical on both `(A,B)` and `(B,A)` rows. Minimum 20 co-appearances (draws excluded) required. |
| `sample_size` | INTEGER | Number of co-appearances (draws excluded) used — reliability indicator |
| `last_updated` | DATETIME | Timestamp of last aggregation run |

> **Uniqueness:** UNIQUE constraint on `(brawler_a_id, brawler_b_id, map_id, game_mode_id)`.

---

### Table: `counters`
Directional pairwise counter scores per map per mode. Produced by the daily pipeline. Separated from `synergies` because the relationship is fundamentally directional, not symmetric.

For every pair (A, B) where A counters B, two rows are written: `(A→B)` with a positive value and `(B→A)` with the negated value.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `brawler_a_id` | INTEGER FK → `brawlers.id` | The brawler whose performance is being measured |
| `brawler_b_id` | INTEGER FK → `brawlers.id` | The opposing brawler |
| `map_id` | INTEGER FK → `maps.id` | Which map |
| `game_mode_id` | INTEGER FK → `game_modes.id` | Which mode |
| `counter_score` | REAL | `win_rate(A when facing B) - win_rate(A overall)`. Draws excluded from both win rates. Positive = A counters B. The `(B,A)` row stores the negated value. Minimum 20 head-to-head appearances (draws excluded) required. |
| `sample_size` | INTEGER | Number of head-to-head appearances (draws excluded) used |
| `last_updated` | DATETIME | Timestamp of last aggregation run |

> **Example:** Leon (id=3) vs Colt (id=7) on Hard Rock Mine:
> - Row `(A=3, B=7)`: `counter_score = +0.12` → Leon counters Colt
> - Row `(A=7, B=3)`: `counter_score = -0.12` → Colt is countered by Leon

> **Uniqueness:** UNIQUE constraint on `(brawler_a_id, brawler_b_id, map_id, game_mode_id)`.

---

### Table: `meta_snapshots`
Weekly pre-computed summaries of the meta per game mode. Powers the homepage meta widget.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `game_mode_id` | INTEGER FK → `game_modes.id` | Which mode this snapshot is for |
| `pipeline_run_id` | INTEGER FK → `pipeline_runs.id` ON DELETE SET NULL | The weekly snapshot pipeline run that produced this row. Set to NULL if the pipeline_runs row is deleted — the snapshot data is retained. |
| `top_picks` | JSON | Ordered list of top 5 most-picked brawlers with pick rates. Only brawlers with `sample_size >= 200` (mode-scoped) are eligible. |
| `top_bans` | JSON | Ordered list of top 5 most-banned brawlers with ban rates. Only brawlers with `sample_size >= 200` are eligible. Will be an empty array `[]` until a ban-aware data source is integrated. |
| `top_win_rate` | JSON | Top 3 brawlers by win rate — only brawlers with `sample_size >= 200` on this mode are eligible |
| `trending_up` | JSON | Up to 3 brawlers whose `pick_rate` and/or `win_rate` increased most vs prior week. Each entry includes `brawler_id`, `name`, `delta_pick_rate`, and `delta_win_rate`. Empty array `[]` on first run. |
| `week_of` | DATE | The most recent Monday on or before the date the job runs. If the job runs on a Monday, `week_of` is that Monday. If it runs on any other day, `week_of` is the preceding Monday. |

---

### Table: `pipeline_runs`
Execution log for all pipeline phases. Every run writes a row here regardless of outcome.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `run_type` | TEXT | `"ingestion"`, `"aggregation"`, `"meta_snapshot"`, or `"seed"`. CHECK constraint enforces these values. |
| `started_at` | DATETIME | When the run began |
| `finished_at` | DATETIME | When the run completed (null if still running or crashed) |
| `status` | TEXT | `"running"`, `"success"`, or `"failed"`. CHECK constraint enforces these values. |
| `matches_fetched` | INTEGER | Total matches pulled from the API (ingestion runs only; null otherwise) |
| `matches_inserted` | INTEGER | New matches inserted after deduplication (ingestion runs only; null otherwise) |
| `error_message` | TEXT | Null on success, error detail on failure |

> **Index:** A non-unique index on `run_type` is required for the `/internal/pipeline/status` query, which selects the most recent row per `run_type`.

> **Cascade behavior:** `meta_snapshots.pipeline_run_id` has `ON DELETE SET NULL`. Deleting a `pipeline_runs` row does not delete the snapshot — the snapshot data is retained and `pipeline_run_id` is set to NULL.

---

## 6. API Endpoints

All endpoints are prefixed with `/api/v1/`.
All responses are JSON. All errors return `{ "detail": "..." }`.

---

### Brawlers

#### `GET /api/v1/brawlers`
Returns the full list of brawlers.

**Request:** No parameters.

**Response headers:** `Cache-Control: public, max-age=86400` — the brawler list changes only on seed runs (at most weekly). Clients and CDN edges may cache for 24 hours.

**Response:**
```json
[
  {
    "id": 1,
    "name": "Shelly",
    "role": "Fighter",
    "rarity": "Common",
    "portrait_url": "https://cdn.brawlstars.com/..."
  }
]
```

---

### Game Modes

#### `GET /api/v1/modes`
Returns all game modes.

**Response headers:** `Cache-Control: public, max-age=86400`

**Response:**
```json
[
  { "id": 1, "name": "Gem Grab" },
  { "id": 2, "name": "Brawl Ball" }
]
```

---

### Maps

#### `GET /api/v1/maps`
Returns all maps, optionally filtered by mode.

**Query Parameters:**
| Param | Type | Required | Description |
|---|---|---|---|
| `mode_id` | integer | No | Filter maps by game mode |

**Response headers:** `Cache-Control: public, max-age=86400`

**Response:**
```json
[
  { "id": 1, "name": "Hard Rock Mine", "game_mode_id": 1 },
  { "id": 2, "name": "Undermine", "game_mode_id": 1 }
]
```

---

### Meta

#### `GET /api/v1/meta/snapshot`
Returns the latest meta snapshot for a given game mode. Used by the homepage meta widget.

**Query Parameters:**
| Param | Type | Required | Description |
|---|---|---|---|
| `mode_id` | integer | Yes | The game mode to fetch meta for |

**Response headers:** `Cache-Control: public, max-age=3600` — clients and CDN edges may cache this response for up to one hour. The underlying data changes at most once per week.

**Response:**
```json
{
  "week_of": "2026-05-25",
  "game_mode_id": 1,
  "top_picks": [
    { "brawler_id": 5, "name": "Poco", "pick_rate": 0.42 }
  ],
  "top_bans": [],
  "top_win_rate": [
    { "brawler_id": 3, "name": "Tara", "win_rate": 0.58, "sample_size": 1240 }
  ],
  "trending_up": [
    {
      "brawler_id": 7,
      "name": "Amber",
      "delta_pick_rate": 0.08,
      "delta_win_rate": 0.032
    }
  ]
}
```

> **Note:** `top_bans` will be an empty array at launch. The frontend renders a notice in place of the ban list when this array is empty. See F5.

---

### Brawler Stats

#### `GET /api/v1/stats`
Returns aggregated stats for a brawler on a specific map and mode.

**Query Parameters:**
| Param | Type | Required | Description |
|---|---|---|---|
| `brawler_id` | integer | Yes | The brawler |
| `map_id` | integer | Yes | The map |
| `mode_id` | integer | Yes | The game mode |

**Response:**
```json
{
  "brawler_id": 5,
  "map_id": 1,
  "game_mode_id": 1,
  "win_rate": 0.54,
  "pick_rate": 0.38,
  "ban_rate": 0.12,
  "sample_size": 3200,
  "last_updated": "2026-05-30T04:00:00Z"
}
```

---

#### `GET /api/v1/stats/bulk`
Returns aggregated stats for **all brawlers** on a specific map and mode in a single call. Used by the draft screen to load stats for the full roster without making per-brawler requests.

**Query Parameters:**
| Param | Type | Required | Description |
|---|---|---|---|
| `map_id` | integer | Yes | The map |
| `mode_id` | integer | Yes | The game mode |

**Response headers:** `Cache-Control: public, max-age=3600` — stats change at most once per day (after the aggregation run). One hour is a conservative TTL that tolerates the daily update while reducing DB load from repeated draft screen loads.

**Response:**
```json
[
  {
    "brawler_id": 1,
    "map_id": 1,
    "game_mode_id": 1,
    "win_rate": 0.51,
    "pick_rate": 0.22,
    "ban_rate": 0.00,
    "sample_size": 980,
    "last_updated": "2026-05-30T04:00:00Z"
  }
]
```

> Brawlers with no stats on the given map/mode are omitted from the response (not returned as zero rows). The frontend should treat missing brawlers as having no data.

---

### Recommendations

#### `POST /api/v1/recommendations`
Core endpoint. Accepts the current draft state and returns top 3 pick recommendations for blue team.

**Rate limited:** max 30 requests per minute per IP. Implemented via `slowapi` using in-memory storage. Note: in-memory rate limiting resets on server restart and is not shared across multiple worker processes. For v1 single-worker deployments this is sufficient; if the backend scales to multiple workers, a Redis-backed limiter will be required.

**Request Body:**
```json
{
  "map_id": 1,
  "mode_id": 1,
  "first_pick_team": "blue",
  "blue_bans": [3, 12],
  "red_bans": [7],
  "blue_picks": [5],
  "red_picks": [9, 14],
  "current_pick_number": 2
}
```

| Field | Type | Description |
|---|---|---|
| `map_id` | integer | The selected map |
| `mode_id` | integer | The selected game mode |
| `first_pick_team` | string | `"blue"` or `"red"` — which team has first pick |
| `blue_bans` | int[] | Brawler IDs banned by blue team |
| `red_bans` | int[] | Brawler IDs banned by red team |
| `blue_picks` | int[] | Brawler IDs already picked by blue team |
| `red_picks` | int[] | Brawler IDs already picked by red team |
| `current_pick_number` | integer | Blue team's current pick slot (1, 2, or 3) |

**Validation (in order):**
1. `first_pick_team` must be `"blue"` or `"red"` (422 otherwise)
2. `map_id` must exist in the `maps` table (422 otherwise)
3. `mode_id` must exist in the `game_modes` table (422 otherwise)
4. `map_id` must belong to `mode_id` (422 with `"map_id does not belong to mode_id"` otherwise)
5. All brawler IDs in all four lists must exist in the `brawlers` table (422 otherwise)
6. No brawler ID may appear in more than one list (422 if overlap detected)
7. `current_pick_number` must equal `len(blue_picks) + 1` (422 otherwise)
8. The derived turn sequence for `first_pick_team` must show blue team as the active picker at position `current_pick_number` (422 otherwise — e.g., sending `current_pick_number: 1` when `first_pick_team: "red"` is invalid because slot 1 belongs to red)

**Response:**
```json
{
  "recommendations": [
    {
      "brawler_id": 8,
      "name": "Tara",
      "confidence": 0.87,
      "reason": "Strong counter to their double tank composition on this map"
    },
    {
      "brawler_id": 22,
      "name": "Gene",
      "confidence": 0.74,
      "reason": "High win rate on Hard Rock Mine and synergizes with Poco"
    },
    {
      "brawler_id": 11,
      "name": "Byron",
      "confidence": 0.68,
      "reason": "Completes a heal-heavy comp and is currently unbanned"
    }
  ]
}
```

**Error responses:**
| Status | Condition |
|---|---|
| 422 | Any validation failure (see validation list above) |
| 503 | LLM call timed out, API error, JSON parse failure after one retry, name resolution failure after one retry, or wrong number of recommendations after one retry |

---

### Pipeline (Internal)

These endpoints require an `X-Internal-Key` header matching the `INTERNAL_API_KEY` environment variable. Requests without a valid key return 403. They should additionally be blocked at the network/proxy level in production and never exposed publicly.

#### `POST /api/v1/internal/pipeline/run`
Triggers a full ingestion + aggregation cycle manually (for development/testing).

**Request:** No body required.

**Response:**
```json
{
  "status": "started",
  "run_ids": {
    "ingestion": 42,
    "aggregation": 43
  }
}
```

> Returns immediately after enqueuing the run.

**Polling for completion:** The caller should poll `GET /api/v1/internal/pipeline/status` and compare the returned `ingestion.id` and `aggregation.id` against the `run_ids` values in this response. When both IDs match and both `status` fields are `"success"` or `"failed"`, the run is complete. Recommended polling interval: 5 seconds. Maximum wait: 30 minutes before treating the run as stuck. A `finished_at` timestamp present with `status = "running"` indicates a crash.

#### `GET /api/v1/internal/pipeline/status`
Returns the most recent pipeline run record for each `run_type`.

**Response:**
```json
{
  "ingestion": {
    "id": 42,
    "status": "success",
    "started_at": "2026-05-30T03:00:00Z",
    "finished_at": "2026-05-30T03:47:12Z",
    "matches_fetched": 3840,
    "matches_inserted": 612,
    "error_message": null
  },
  "aggregation": {
    "id": 43,
    "status": "success",
    "started_at": "2026-05-30T04:00:00Z",
    "finished_at": "2026-05-30T04:03:55Z",
    "matches_fetched": null,
    "matches_inserted": null,
    "error_message": null
  },
  "meta_snapshot": {
    "id": 38,
    "status": "success",
    "started_at": "2026-05-25T05:00:00Z",
    "finished_at": "2026-05-25T05:01:22Z",
    "matches_fetched": null,
    "matches_inserted": null,
    "error_message": null
  },
  "seed": {
    "id": 35,
    "status": "success",
    "started_at": "2026-05-26T02:00:00Z",
    "finished_at": "2026-05-26T02:00:45Z",
    "matches_fetched": null,
    "matches_inserted": null,
    "error_message": null
  }
}
```

> If no run of a given type has ever executed, that key maps to `null`.

---

## 7. Folder Structure

### Backend

```
backend/
├── app/
│   ├── api/
│   │   └── routes/
│   │       ├── brawlers.py          # GET /brawlers
│   │       ├── modes.py             # GET /modes
│   │       ├── maps.py              # GET /maps
│   │       ├── meta.py              # GET /meta/snapshot
│   │       ├── stats.py             # GET /stats, GET /stats/bulk
│   │       ├── recommendations.py   # POST /recommendations
│   │       └── internal.py          # POST/GET /internal/pipeline/*
│   ├── core/
│   │   ├── config.py                # Env vars, settings
│   │   └── rate_limit.py            # slowapi limiter instance
│   ├── db/
│   │   ├── database.py              # SQLite connection, check_same_thread=False,
│   │   │                            # session factory, WAL pragma on connect
│   │   └── models.py                # SQLAlchemy model definitions
│   ├── schemas/
│   │   ├── brawler.py               # Pydantic schemas for brawler I/O
│   │   ├── draft.py                 # RecommendationRequest, RecommendationResponse
│   │   ├── meta.py                  # MetaSnapshotResponse
│   │   └── stats.py                 # BrawlerStatsResponse, BrawlerStatsBulkResponse
│   ├── services/
│   │   ├── recommendation.py        # RAG context retrieval + LLM call + name resolution
│   │   ├── aggregation.py           # Computes brawler_stats, synergies, counters
│   │   └── meta_snapshot.py         # Computes and stores weekly snapshots
│   └── main.py                      # FastAPI app entry point, router registration
├── pipeline/
│   ├── fetch.py                     # Pulls match data from Brawl Stars API
│   ├── aggregate.py                 # Runs aggregation services
│   ├── seed.py                      # Seeds/refreshes brawlers, modes, maps
│   └── scheduler.py                 # APScheduler config
├── migrations/                      # Alembic migration files
├── seeds/
│   ├── brawler_roles.json           # Manual fixture: brawler_id → {role, rarity}
│   ├── modes.json                   # Static game mode list
│   └── maps.json                    # Static map list with game_mode_id references
├── tests/
│   ├── test_endpoints.py
│   ├── test_recommendation.py
│   └── test_pipeline.py
├── .env                             # Secret keys — never committed
├── .env.example                     # Non-secret template — committed
├── alembic.ini
└── requirements.txt
```

### Frontend

```
frontend/
├── src/
│   ├── components/
│   │   ├── lobby/
│   │   │   ├── ModeSelector.jsx         # Mode picker buttons + skeleton state
│   │   │   ├── MapSelector.jsx          # Map picker filtered by mode + skeleton state
│   │   │   ├── FirstPickSelector.jsx    # Toggle: which team has first pick
│   │   │   └── MetaWidget.jsx           # Weekly meta summary card + skeleton state
│   │   ├── draft/
│   │   │   ├── DraftBoard.jsx           # Full board layout
│   │   │   ├── TeamColumn.jsx           # One side (blue or red) with ban + pick slots
│   │   │   ├── DraftSlot.jsx            # Single ban or pick slot with active indicator
│   │   │   └── TurnIndicator.jsx        # Context-sensitive banner for current turn phase
│   │   ├── roster/
│   │   │   ├── BrawlerRoster.jsx        # Full scrollable grid
│   │   │   ├── BrawlerCard.jsx          # Individual brawler portrait tile
│   │   │   └── RosterSearch.jsx         # Search input
│   │   └── recommendations/
│   │       ├── RecommendationPanel.jsx  # Container — renders only on Blue pick turns
│   │       └── RecommendationCard.jsx   # Single recommendation with score + reason
│   ├── pages/
│   │   ├── Lobby.jsx                    # Lobby screen page
│   │   └── Draft.jsx                    # Draft screen — redirects to lobby if store empty
│   ├── hooks/
│   │   ├── useDraft.js                  # Draft turn logic, slot management.
│   │   │                                # Derives full turn sequence from first_pick_team.
│   │   │                                # Resets store on unmount.
│   │   └── useRecommendations.js        # Calls recommendation API, manages all states
│   ├── store/
│   │   └── draftStore.js               # Zustand store with reset() action
│   ├── services/
│   │   └── api.js                       # All fetch calls to backend
│   └── assets/
│       └── brawlers/                    # Required local fallback portraits.
│                                        # Filename: slugify(name) + ".png"
│                                        # Slugification: NFC normalize → strip diacritics
│                                        # → lowercase → non-[a-z0-9-] runs → hyphen
│                                        # → trim hyphens
├── .env                                 # VITE_API_URL — not committed
├── .env.example                         # Template — committed
└── vite.config.js
```

---

## 8. Architecture & Patterns

### Separation of Concerns
Routes are thin. Each route handler receives a request, calls a service, and returns a response. All business logic lives in `services/`. Services do not import from `api/` — they have no knowledge of HTTP.

### Service Layer
`recommendation.py`, `aggregation.py`, and `meta_snapshot.py` are pure Python services. They accept typed inputs and return typed outputs. They can be called from routes, from the pipeline, or from tests identically.

### Pydantic Schemas
Every API endpoint has an explicit input schema and output schema defined in `schemas/`. This gives automatic request validation, clear error messages, and a self-documenting contract between frontend and backend.

### Pipeline Decoupling
The ingestion and aggregation pipeline (`pipeline/`) is completely independent of the web server. It writes to the database on a schedule. The API only reads. The pipeline can be run, tested, and debugged without starting the web server.

**Deployment note:** In both development and production, the pipeline runs as a **separate process** from the FastAPI web server. In development this means running two terminal processes (`uvicorn` + `python pipeline/scheduler.py`). This keeps dev and prod architectures consistent and avoids surprises at deployment.

### WAL Mode for Concurrency
SQLite is initialized with `PRAGMA journal_mode=WAL;` in `db/database.py`. This allows the web server and the pipeline process to coexist without locking conflicts — readers never block writers and writers never block readers under WAL mode. This is sufficient for v1 load.

> **Cloud deployment warning:** WAL mode assumes the SQLite file lives on a local disk. On Railway and Render, persistent storage is mounted as network volumes (e.g., EFS on AWS). SQLite WAL mode can exhibit locking bugs on network filesystems under concurrent write pressure. For v1, mitigate by ensuring the pipeline and web server never write simultaneously (the scheduled pipeline runs at off-peak hours, the API is read-only). Monitor for `database is locked` errors in production logs. If they occur, migrate to Postgres — this resolves the issue permanently and is the recommended path once write load increases.

### SQLAlchemy Session Configuration
`db/database.py` creates the engine with `connect_args={"check_same_thread": False}`. This is required because FastAPI handles requests across multiple threads while SQLite's default configuration only permits access from the thread that created the connection. Without this flag, concurrent requests will raise `ProgrammingError: SQLite objects created in a thread can only be used in that same thread`. Sessions are managed per-request via FastAPI's dependency injection (`Depends(get_db)`) and closed after each request completes.

### RAG Pattern for Recommendations
At draft time, the recommendation service:
1. Validates map/mode consistency and all brawler IDs (returns 422 on failure)
2. Derives the available brawler list (all brawlers minus banned and picked)
3. Queries `brawler_stats` (map-scoped) for all available brawlers on the current map/mode
4. Trims to the top 20 available brawlers by `win_rate` to bound prompt token count
5. Queries `synergies` for blue picks paired with top-20 available brawlers
6. Queries `counters` for top-20 available brawlers against red picks
7. Injects this as structured context into a Claude API prompt (see [LLM Prompt Template](#llm-prompt-template))
8. Calls the Claude API with a 10-second timeout
9. Parses JSON, validates exactly 3 items, resolves names to IDs (case-insensitive); retries once on any failure
10. Returns the resolved recommendation schema

### Recommendation Caching
The recommendation service caches responses by a hash of the full request body. Cache TTL is 60 seconds. This eliminates redundant LLM calls for identical draft states and reduces API cost. **Failed responses (503) are never written to cache** — a failed request allows a fresh LLM attempt on the next call.

### Custom React Hooks
Data fetching and business logic are extracted into hooks. Components are declarative and stateless where possible. `useDraft` owns turn order logic and derives the full pick sequence from `first_pick_team` at initialization. `useRecommendations` owns API calls, loading state, and error state for all failure modes. `useDraft` resets the Zustand store on unmount so back-navigating to the lobby always starts fresh.

**Store reset and forward navigation:** When `useDraft` unmounts (Draft page leaves the DOM), it calls `draftStore.reset()`. If the user subsequently presses the browser Forward button, the Draft page remounts. On mount, `Draft.jsx` reads the required fields (`map_id`, `mode_id`, `first_pick_team`) from the store. If any are absent (store was reset), it calls `navigate('/', { replace: true })` to redirect to the lobby. This prevents a broken blank draft state.

### Centralized API Service
All `fetch` calls to the backend live in `services/api.js`. Components and hooks import from this file only. When the API URL or auth headers change, one file changes.

### Global Draft State (Zustand)
The draft state — selected map, mode, first-pick team, bans, picks, and current turn — is shared across multiple components. Zustand provides a minimal, hook-based store without boilerplate. The store exposes a `reset()` action called by `useDraft` on unmount.

### API Versioning
All routes are prefixed with `/api/v1/`. This costs nothing now and avoids breaking changes when the API evolves.

### Alembic Migration Strategy

Schema changes follow this process:

1. Modify the SQLAlchemy model in `db/models.py`
2. Run `alembic revision --autogenerate -m "description"` to generate a migration script
3. Review the generated script — autogenerate is not always correct, especially for CHECK constraints, index additions, and column renames
4. Apply with `alembic upgrade head` in all environments
5. For column additions with NOT NULL: always provide a server-side default or make the column nullable, or the migration will fail on tables with existing rows
6. For CHECK constraint additions: SQLite does not support adding constraints to existing tables via ALTER TABLE. The migration must recreate the table. Alembic's SQLite dialect handles this via `batch_alter_table`; use that pattern.
7. Never modify existing migration files after they have been applied to any environment. Always create a new migration.

---

## 9. Security

### Environment Variables
- `BRAWLSTARS_API_KEY`, `ANTHROPIC_API_KEY`, and `INTERNAL_API_KEY` are loaded from `.env` via `config.py`
- All `.env` files are in `.gitignore` before the first commit
- A `.env.example` file (committed) documents all required variables with placeholder values but no secrets
- Frontend uses `VITE_API_URL` only — no secret keys ever reach the frontend

### CORS
- FastAPI is configured to accept requests only from the frontend domain
- In development: `localhost:5173`
- In production: the deployed Vercel URL
- Wildcard (`*`) is never used in production

### Rate Limiting
- The `POST /api/v1/recommendations` endpoint is rate limited to 30 requests per minute per IP
- Implemented via `slowapi` (wraps the `limits` library). Uses in-memory storage for v1 — sufficient for a single-worker deployment. Rate limit state resets on server restart and is not shared across workers. If the deployment scales beyond one worker process, switch the `slowapi` storage backend to Redis.

### Internal Endpoint Protection
- Internal pipeline endpoints (`/api/v1/internal/*`) require an `X-Internal-Key` header matching `INTERNAL_API_KEY`
- Requests without a valid key return 403
- In production, these routes should additionally be blocked at the network/proxy level (e.g., only accessible from within the private network or via an internal service URL)

### Input Validation
- All incoming request bodies are validated by Pydantic before reaching service logic
- The recommendation endpoint validates (in order): `first_pick_team` enum, `map_id` and `mode_id` existence, map/mode relationship, brawler ID existence, brawler list overlap, `current_pick_number` sequence consistency, and blue team turn ownership. See validation list in [Section 6](#recommendations).

### LLM Prompt Safety
- Brawler names and stats come from the database, which is populated from the official Brawl Stars API and committed fixture files
- No free-text user input is injected into LLM prompts in v1
- The prompt instructs the LLM to use brawler names exactly as they appear in the injected stats table, reducing the chance of hallucinated or variant names passing name resolution
- Fixture files (`seeds/brawler_roles.json`, `seeds/maps.json`, `seeds/modes.json`) are committed to the repository and must not be editable by untrusted parties in any deployment path

### SQL Parameterization
- All queries go through SQLAlchemy ORM or parameterized raw queries
- String concatenation into SQL queries is never used

### Error Monitoring
- All pipeline failures write to `pipeline_runs` with `status = "failed"` and an `error_message`
- In production, configure Railway/Render health check alerts and log-based alerting for:
  - Any `pipeline_runs` row where `status = "failed"` — query this on a schedule or use a log grep
  - Repeated 503 responses from the recommendation endpoint (indicates LLM API outage or key exhaustion)
  - `database is locked` in server logs (indicates WAL mode contention)
- For v1, a simple daily cron that queries `pipeline_runs` for recent failures and sends an email or Slack message is sufficient. A third-party service (Sentry, Datadog) is recommended once traffic grows.

---

## 10. Testing Strategy

### Backend

#### Unit Tests — Services
Test each service function in isolation with mocked database responses.

- **`test_recommendation.py`**
  - Given a draft state and mocked stats/synergy/counter data, assert the correct context is built and the prompt is constructed correctly
  - Assert that map/mode mismatch returns 422
  - Assert that overlapping brawler IDs across input lists return 422
  - Assert that inconsistent `current_pick_number` returns 422
  - Assert that `current_pick_number` belonging to red team's turn returns 422
  - Assert that LLM timeout and parse failure return 503
  - Assert that an array with 2 or 4 items triggers the parse-failure retry path
  - Assert that an unresolvable brawler name triggers the parse-failure retry path
  - Assert that a successful response after one parse retry is returned correctly
  - Assert that 503 responses are not written to cache
  - Assert that name resolution is case-insensitive and whitespace-insensitive

- **`test_aggregation.py`**
  - Given raw match data including draws, assert win rates exclude draws and sample sizes include them
  - Assert pick rates include draw matches in the denominator
  - Assert win rates, pick rates, and synergy scores are computed correctly using the defined formulas
  - Assert that both directions of each counter pair are written to the `counters` table with correctly negated values
  - Assert that synergy rows are written to `synergies` (not `counters`)
  - Assert that upsert logic updates existing rows rather than inserting duplicates
  - Assert that pairs below minimum sample size thresholds are not written
  - Assert that mode-scoped `brawler_stats` rows (map_id IS NULL) are produced for each mode touched

- **`test_meta_snapshot.py`**
  - Given aggregated mode-scoped stats, assert the snapshot JSON is structured correctly
  - Assert that brawlers with `sample_size < 200` are excluded from `top_picks`, `top_bans`, and `top_win_rate`
  - Assert that `trending_up` includes both `delta_pick_rate` and `delta_win_rate`
  - Assert that `trending_up` is `[]` when no prior snapshot exists
  - Assert that `week_of` is always the most recent Monday on or before the execution date

#### Integration Tests — Endpoints
Test each API endpoint with a real in-memory SQLite database seeded with test data.

- All `GET` endpoints: assert correct response shape, status codes, and `Cache-Control` headers
- `GET /stats/bulk`: assert returns all brawlers with stats for the given map/mode; assert brawlers with no stats are omitted; assert response includes `last_updated`
- `POST /recommendations`: assert it returns 3 recommendations with required fields including `brawler_id`
- Test validation order: map/mode mismatch, missing fields, non-existent brawler IDs, invalid mode/map combinations, overlapping brawler IDs, inconsistent `current_pick_number`, `current_pick_number` on red's turn, invalid `first_pick_team`
- Internal endpoints: assert 403 is returned without a valid `X-Internal-Key` header; assert correct response shape with valid key; assert `/run` returns `run_ids` that match rows in `pipeline_runs`

#### Pipeline Tests
- **`test_pipeline.py`**
  - Mock the Brawl Stars API response, run the fetch function, assert correct rows are inserted into `matches` and `match_brawlers`
  - Test deduplication: running the pipeline twice with the same data should not create duplicate match rows
  - Test draw handling: matches with outcome `"draw"` are inserted with `winning_team = "draw"`
  - Test 429 handling: mock a 429 response and assert the pipeline retries with backoff before logging failure
  - Test 401/403 handling: mock an auth failure and assert the pipeline aborts immediately with a failed `pipeline_runs` row
  - Test quota exhaustion: mock >50% of players returning 429 exhaustion and assert the pipeline aborts with `status = "failed"`
  - Test tag encoding: assert that a player tag containing `#` is correctly encoded to `%23` in the request URL
  - Test unknown brawler handling: assert that a match containing an unrecognized brawler ID is skipped with a warning rather than causing an FK violation

#### Test Database
All tests use a separate in-memory SQLite database. No test ever touches the production database. Fixtures create and tear down tables per test.

### Frontend

#### Component Tests
Use React Testing Library for component-level tests.

- **`DraftSlot`** — renders correctly in active, filled, and inactive states
- **`BrawlerCard`** — fires correct callback on click; applies greyed-out style when disabled; renders fallback portrait (using slugified name) when CDN URL returns 404; slugification handles accented characters correctly
- **`RecommendationPanel`** — does not render during ban phase; does not render during Red pick turns; renders error message when API returns 503; renders error message on network failure; renders skeleton cards during loading
- **`MetaWidget`** — renders correctly with mocked API response; shows "Ban data not yet available" when `top_bans` is an empty array; shows error message when fetch fails; shows "Not enough data yet for trends" when `trending_up` is empty; renders `delta_pick_rate` and `delta_win_rate` for trending brawlers
- **`TurnIndicator`** — renders "Blue team — Pick {n}" during blue turns; renders "Red's turn — click to record their pick" during red turns; renders "[Blue/Red] team banning" during ban phase
- **`FirstPickSelector`** — toggling updates Zustand store correctly
- **`ModeSelector`** — renders skeleton buttons while loading; renders error message on fetch failure
- **`MapSelector`** — renders skeleton list while loading; renders error message on fetch failure

#### Hook Tests
- **`useDraft`** — assert turn order advances correctly through ban and pick phases for both `first_pick_team = "blue"` and `first_pick_team = "red"`; assert store is reset when hook unmounts; assert that mounted draft page with empty store redirects to lobby
- **`useRecommendations`** — assert API is called with correct draft state after each pick; assert loading state is set during the call; assert error state is set on 503 response; assert error state is set on network failure; assert panel is not rendered (hook returns null/inactive) during ban phase and Red pick turns

#### End-to-End (Optional, v1.5+)
Playwright or Cypress for full user flow tests: select mode → select map → choose first-pick team → complete a full draft → verify recommendations appear at each blue pick turn → navigate back to lobby → verify draft state is cleared → verify forward navigation redirects to lobby.

### Running Tests

```bash
# Backend
cd backend
pytest tests/ -v

# Frontend
cd frontend
npm run test
```

---

## 11. Pipeline & Scheduler

The pipeline runs as a **separate process** from the web server in all environments (see Architecture section). Start it with `python pipeline/scheduler.py`.

### Weekly Seed Refresh (runs Monday at 2:00 AM)
1. Call `GET /brawlers` on the Brawl Stars API to fetch the current roster
2. Upsert brawler rows including refreshed `portrait_url` values
3. Log run to `pipeline_runs` with `run_type = "seed"`

This run refreshes CDN portrait URLs and picks up any new brawlers added by Supercell since the last seed.

### Daily Ingestion (runs at 3:00 AM)
1. Call `GET /rankings/global/players` to fetch the top 200 global player tags. Note: the battle log API returns a maximum of 25 recent matches per player. With 200 players and deduplication (players who appear in each other's logs), expect 200–600 net-new matches per run depending on overlap.
2. For each player tag, encode it using `urllib.parse.quote(tag, safe='')` and call `GET /players/{encoded_tag}/battlelog`
3. On 401/403, abort immediately and record failure
4. On 429 responses, apply exponential backoff with jitter and retry up to 3 times per player. If more than 50% of players exhaust retries, abort and record failure.
5. Filter out non-3v3 modes (`soloShowdown`, `duoShowdown`, etc.)
6. Parse each battle: map, mode, outcome (`victory`/`defeat`/`draw`), and brawlers per team
7. Skip any match containing a brawler ID not present in the `brawlers` table; log a warning
8. Insert new matches into `matches` and `match_brawlers`, skipping rows where `(played_at, source_player_tag)` already exists
9. Log run to `pipeline_runs` with `run_type = "ingestion"`

### Daily Aggregation (runs at 4:00 AM, after ingestion)
1. Identify all `(map_id, game_mode_id)` combinations touched by the current ingestion run
2. For each combination, recompute all `brawler_stats` rows in full (not incrementally)
3. Recompute mode-scoped `brawler_stats` rows (map_id = NULL) for each `game_mode_id` touched
4. Recompute pairwise synergy scores. Write both `(A, B)` and `(B, A)` rows to `synergies`. Skip pairs below minimum sample size. All win rates exclude draws.
5. Recompute pairwise counter scores. Write both `(A, B)` and `(B, A)` rows to `counters`. The `(B, A)` row stores the negated value. Skip pairs below minimum sample size. All win rates exclude draws.
6. Upsert into `brawler_stats`, `synergies`, and `counters` tables
7. Update `last_updated` timestamps
8. Log run to `pipeline_runs` with `run_type = "aggregation"`

### Weekly Meta Snapshot (runs Monday at 5:00 AM)
1. For each game mode, query **mode-scoped** `brawler_stats` rows (map_id IS NULL) for top picks, top bans, top win rates. Apply minimum `sample_size >= 200` threshold.
2. Compare to the most recent prior `meta_snapshots` row for the same `game_mode_id` to identify trending brawlers. Include both `delta_pick_rate` and `delta_win_rate` in `trending_up` entries. If no prior snapshot exists, set `trending_up = []`.
3. Write new row to `meta_snapshots`. Set `week_of` to the most recent Monday on or before the execution date.
4. Log run to `pipeline_runs` with `run_type = "meta_snapshot"`

### Scheduler Configuration
All jobs are configured in `pipeline/scheduler.py` using APScheduler. The scheduler runs as a **separate process** from FastAPI in both development and production. In production, deploy it as a separate worker/container on Railway or Render alongside the web server.

**Scheduled job summary:**
| Job | Schedule | run_type |
|---|---|---|
| Seed refresh | Monday 2:00 AM | `"seed"` |
| Ingestion | Daily 3:00 AM | `"ingestion"` |
| Aggregation | Daily 4:00 AM | `"aggregation"` |
| Meta snapshot | Monday 5:00 AM | `"meta_snapshot"` |

---

## 12. Local Development Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- A Brawl Stars API key (obtain from https://developer.brawlstars.com)
- An Anthropic API key

### First-Time Setup

```bash
# 1. Clone the repo
git clone <repo-url>
cd brawldrafter

# 2. Backend setup
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env and fill in:
#   BRAWLSTARS_API_KEY=your_key_here
#   ANTHROPIC_API_KEY=your_key_here
#   INTERNAL_API_KEY=any_random_string_for_local_use
#   DATABASE_URL=sqlite:///./brawldrafter.db

# 4. Initialize the database
alembic upgrade head

# 5. Seed static data (brawlers, modes, maps)
python -m seeds.seed

# 6. (Optional) Run the ingestion pipeline manually to populate match data
python -m pipeline.fetch
python -m pipeline.aggregate

# 7. Start the web server
uvicorn app.main:app --reload --port 8000

# 8. In a separate terminal, start the pipeline scheduler (optional for local dev)
python pipeline/scheduler.py
```

```bash
# Frontend setup (separate terminal)
cd frontend
npm install
cp .env.example .env
# Edit .env: VITE_API_URL=http://localhost:8000
npm run dev
```

### Environment Variables Reference

**Backend (`.env`):**
| Variable | Required | Description |
|---|---|---|
| `BRAWLSTARS_API_KEY` | Yes | Bearer token for `api.brawlstars.com` |
| `ANTHROPIC_API_KEY` | Yes | API key for Claude recommendations |
| `INTERNAL_API_KEY` | Yes | Secret for internal pipeline endpoints |
| `DATABASE_URL` | Yes | SQLite path, e.g. `sqlite:///./brawldrafter.db` |
| `FRONTEND_ORIGIN` | Yes | CORS allowed origin, e.g. `http://localhost:5173` |

**Frontend (`.env`):**
| Variable | Required | Description |
|---|---|---|
| `VITE_API_URL` | Yes | Backend base URL, e.g. `http://localhost:8000` |

---

## 13. Known Limitations

These are documented tradeoffs, not bugs. They are out of scope for v1 but should be understood before launch.

**High-ELO data bias:** Match data comes exclusively from the top 200 global-ranked players. The resulting recommendations reflect optimal high-ELO strategy, which may differ significantly from general player behavior. A brawler that is dominant at the highest level of play may be unremarkable at lower trophy counts, and vice versa. This is a deliberate choice — high-ELO data is the highest-quality signal available — but users should be aware of it.

**Low match volume per run:** The Brawl Stars battle log API returns at most 25 recent matches per player. With 200 players and typical overlap (players who appear in each other's logs share match records), expect 200–600 genuinely new matches per daily run. New maps, new brawlers, and niche game modes may stay below the `sample_size >= 200` eligibility threshold for weeks or months after launch. During this period, those brawlers/maps will not appear in meta snapshots and may receive lower-quality recommendations (the LLM will have little stats context to reason about).

**No ban data:** The standard Brawl Stars battle log API does not expose ban information. `ban_rate` will be 0.0 for all brawlers, and `top_bans` in meta snapshots will be empty. This is surfaced clearly to users in the meta widget. The schema supports ban data — it requires an alternative data source.

**24-hour stat staleness:** Recommendations are always based on stats from the last completed aggregation run, which may be up to 24 hours old. Following a major balance patch, recommendations could reflect pre-patch data until the next daily pipeline run.

**SQLite on network volumes:** WAL mode may exhibit locking issues on cloud network volumes (Railway, Render). Mitigated by scheduling the pipeline at off-peak hours when the API server has minimal write activity. Monitor for `database is locked` in logs; migrate to Postgres if this occurs.

**In-memory rate limiting:** The recommendation endpoint rate limit resets on server restart. This is acceptable for v1 single-process deployments. Multi-worker deployments require Redis-backed rate limiting.

**Retired or renamed brawlers:** If Supercell removes a brawler from the game, their historical stats rows remain in the database indefinitely. No automated cleanup exists in v1.

---

## 14. Future Considerations

These are out of scope for v1 but worth designing toward.

- **Ban Data Integration** — ingest competitive tournament drafts or community-contributed ban data to populate `ban_rate` and `top_bans`; the schema already supports this via `was_banned`
- **User Auth + Draft History** — allow users to save and review past drafts
- **Postgres Migration** — swap SQLite for Postgres when concurrent write load increases or cloud volume WAL issues arise
- **Redis-backed Rate Limiting** — required if the backend scales beyond a single worker process
- **Map-Level Meta Widget** — once a map is selected in the lobby, optionally switch the meta widget to show map-scoped stats; `brawler_stats` map-scoped rows already support this
- **Meta Over Time** — chart meta trends week-over-week using the `meta_snapshots` history
- **Pro Play Import** — ingest competitive tournament drafts as a separate high-weight source; would also provide ban data
- **Ban Recommendations** — extend the recommendation engine to suggest optimal bans
- **Mobile App** — React Native with shared API
- **Patch Notes Ingestion** — scrape or parse patch notes to flag brawlers with recent buffs/nerfs and weight recent matches more heavily in aggregation
- **Broader Rank Distribution** — supplement top-200 data with matches from lower rank tiers for a more representative general-population meta
- **Pagination** — add `limit`/`offset` to `GET /brawlers` and `GET /maps` before the roster grows large enough to matter
- **E2E Tests** — Playwright or Cypress covering the full draft flow (promoted from optional to planned for v1.5)
- **`INTERNAL_API_KEY` Rotation** — add a key rotation mechanism so the internal key can be changed without full redeployment