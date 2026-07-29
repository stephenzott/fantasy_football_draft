# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A custom fantasy football draft board that combines season projections from multiple ranking sources, converts them to the league's specific scoring system, aggregates into a unified ranking with VBD scores, and supports live updates on draft day.

The board also surfaces player flags — concerns like domestic violence arrests or other off-field issues — alongside rankings.

**Multi-league:** Supports 5 leagues from a single codebase — one switchable board, not 5 separate deployments. Every piece of draft-day state (drafted players, live sync) is scoped by `league_id` so two drafts can run simultaneously (e.g. two browser tabs, each pointed at a different league) without state bleeding across leagues. See "Multi-League Support" under Architecture.

---

## Tech Stack

- **Backend:** Python
- **Frontend:** Static HTML/CSS/JS (hosted via GitHub Pages)
- **Draft-day state:** Firebase Realtime Database (real-time listeners, generous free tier for this scale). Replaces `localStorage`. Schema: `/leagues/{league_id}/drafted/{player_id}` — every read/write scoped by `league_id`, never a flat/global drafted list.
- **Version Control / Hosting:** GitHub

---

## Data Sources

Rankings/projections are downloaded before each draft from:
- FantasyPros (free) — direct CSV export
- Sleeper (free) — API script, no manual download option
- ESPN — manual copy
- Yahoo (free) — manual copy
- The Athletic (paid) — manual copy
- NFL.com (free) — manual copy; distinct source from ESPN, not a duplicate
- SI / FantasySports On SI (free) — manual copy

Manual copy/paste is the accepted approach for sources without a clean export; no parser-building planned for those formats at this time.

Files are dropped into `data/` and must be parseable by the pipeline without manual editing.

---

## Architecture

### 1. Data Pipeline (Python) — not yet built
- Input: CSV/XLSX files downloaded from ranking sources, dropped into `data/`
- Normalize player data into a common schema:
  ```
  {
    player_name, team, position,
    projected_stats: { pass_yds, rush_yds, rec, tds, ... },
    source
  }
  ```
- Convert projected stats → fantasy points using the league's scoring settings (see `scoring.yaml`)
- Output: `docs/players.json`

### 2. Aggregation Logic (Python) — not yet built
- Average (or weighted average) the converted point projections across sources
- Rank players by aggregated projected points
- Calculate **Value-Based Drafting (VBD)** score:
  - Find the baseline player at each position (e.g., 12th RB, 12th WR)
  - VBD = player's projected points − baseline projected points

### 3. Multi-League Support — not yet built

**5 leagues total:**
| League | Platform | Draft mode |
|---|---|---|
| League 1 | ESPN (private) | Live — poll ESPN's unofficial API + manual fallback |
| League 2 | ESPN (private) | Live — poll ESPN's unofficial API + manual fallback |
| League 3 | ESPN (private) | Live — poll ESPN's unofficial API + manual fallback |
| League 4 | Offline (non-Sleeper) | Manual only — no API to poll |
| League 5 | Sleeper | Manual only — drafting offline, so Sleeper's API isn't in play despite being available |

**Design requirements:**
- One board (`index.html`/`app.js`), league selected via URL param (e.g. `?league=espn_league_a`) — not in-memory-only state, so two tabs can independently point at two different leagues at once.
- All drafted-state and sync reads/writes scoped by `league_id` — never a flat/global drafted list. This is the guard against state bleeding between simultaneous drafts.
- Each league likely needs its own `scoring.yaml` (different scoring settings) and its own `players.json` (or one combined file keyed by league) since roster sizes / VBD baselines differ per league.
- ESPN private leagues require `espn_s2` and `SWID` auth cookies to hit the API. **Decision:** the ESPN-polling script runs locally on Stephen's laptop during the draft (not a cloud function), so cookies live in a local, gitignored `.env` file (`ESPN_S2=...`, `SWID=...`) and never touch the repo, Firebase, or the frontend.

### 4. Leagues Config — not yet built
A `leagues.yaml` (or `.json`) at the repo root should be the single source of truth for the 5 leagues, e.g.:
```yaml
leagues:
  - id: league_1
    platform: espn
    draft_mode: live
    espn_league_id: <espn numeric league id>
    scoring_file: scoring_league_1.yaml
  - id: league_4
    platform: offline
    draft_mode: manual
    scoring_file: scoring_league_4.yaml
  - id: league_5
    platform: sleeper
    draft_mode: manual   # drafting offline; Sleeper's API isn't used despite being available
    scoring_file: scoring_league_5.yaml
```
The frontend's league selector, the build pipeline, and the ESPN poller should all read from this one file rather than hardcoding league details in multiple places.

### 5. ESPN Live Draft Polling — not yet built
- For the 3 ESPN leagues only. Polls ESPN's unofficial API (`https://fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{league_id}?view=mDraftDetail`) on an interval during the draft.
- Auto-marks players as drafted on the board when they appear in ESPN's draft detail response.
- Manual "DRAFTED" button remains available alongside polling, as a fallback in case of API lag/failure.
- Not applicable to the 2 offline leagues (League 4 and League 5/Sleeper) — no live draft room to poll, manual marking only.

### 6. Frontend (Static HTML/CSS/JS) — built, needs multi-league updates
Files live in `docs/`:
- `index.html` — page structure
- `style.css` — dark theme, position color-coding, scanline texture
- `app.js` — all interactivity
- `players.json` — generated by the pipeline (currently sample data)

**Features:**
- Fetches `players.json` at load time
- Sortable columns: overall rank, position, projected points, VBD
- Position filters: ALL / QB / RB / WR / TE / FLEX (RB+WR+TE)
- "DRAFTED" button per player — dims and strikes through the row, state saved to `localStorage` key `draftboard_v1_drafted`
- "HIDE DRAFTED" toggle — removes drafted players from view
- "DV LIST" toggle — removes any player with entries in their `flags` array
- Click a row to expand per-source projection breakdown and flag details
- Red dot indicator on player name for flagged players

### `players.json` schema
Each player object must have:
```json
{
  "name": "Christian McCaffrey",
  "team": "SF",
  "position": "RB",
  "rank": 1,
  "pos_rank": "RB1",
  "projected_points": 412.3,
  "vbd": 252.1,
  "sources": { "fantasypros": 418.2, "sleeper": 405.1, "espn": 413.6, "yahoo": 410.0, "athletic": 415.8, "nfl": 409.2, "si": 411.4 },
  "flags": [],
  "injuries": []
}
```
- `flags` — conduct/legal concerns, format `"{incident} — {resolution}"`. Empty array if none.
- `injuries` — injury/availability concerns, plain strings. Empty array if none.

### Player Flags
Flags are stored directly on each player object in `players.json`. The pipeline fetches them live from a Google Sheet at build time and joins them onto players. An empty `flags: []` means no concerns.

**Source:** Google Sheet ID `1PdD1hmkFPRgOJ_lDb4bhieYV4B4hy0zcBsIkDxJAkEs`
**Parser:** `scripts/parsers/flags_sheet.py` → `fetch_flags()` returns `dict[lowercase_name → list[str]]`
**Sharing:** Sheet must be set to "Anyone with the link can view" for the CSV export URL to work.
**Format:** Columns — Date | First Name | Last Name | Team | Incident | Resolution. Multiple rows per player are merged into one flags list.

---

## Scoring System Configuration

Define league scoring settings in `scoring.yaml`:

```yaml
pass_td: 4
pass_yd: 0.04
rush_yd: 0.1
rush_td: 6
reception: 0.5   # PPR
rec_yd: 0.1
rec_td: 6
```

---

## Draft Day Workflow

1. Run `python scripts/build.py` the morning of the draft to regenerate `players.json` for all 5 leagues (reads `leagues.yaml` + each league's `scoring.yaml`)
2. Open `docs/index.html` (or the GitHub Pages URL), select the correct league from the league selector — the URL updates to `?league={league_id}`
3. For the 3 ESPN leagues: start the local ESPN-polling script (reads cookies from local `.env`) before the draft begins so picks auto-sync to Firebase
4. For the 2 offline leagues (League 4, Sleeper League 5): no polling script — mark players manually as they're drafted
5. Optionally toggle "DV LIST" to hide flagged players
6. As players are taken, click "DRAFTED" (manual leagues) or let the poller auto-mark them (ESPN leagues) — both write to the same Firebase path, `/leagues/{league_id}/drafted/{player_id}`, so manual clicks work as a fallback on ESPN leagues too
7. Toggle "HIDE DRAFTED" to clear them from view and focus on remaining players
8. State syncs live via Firebase across every open tab/device pointed at that `league_id` — no per-device state to lose on refresh
9. Running two drafts simultaneously: open two tabs, each with a different `?league=` param; each is fully independent

---

## Development

### Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Running the pipeline
```bash
python scripts/build.py
```
Reads from `data/` and writes `docs/players.json`.

### Serving the site locally
```bash
cd docs && python -m http.server 8000
```

---

## Conventions

- `data/` — raw downloaded ranking files (CSV/XLSX), one subdirectory per source
- `docs/` — GitHub Pages root; `index.html`, `style.css`, `app.js`, `players.json`
- `scripts/` — Python data pipeline scripts
- `scripts/parsers/` — one parser per source, each normalizing to the common schema
- `flags/` — player flag source data (joined onto players during pipeline build)
- `leagues.yaml` — single source of truth for the 5 leagues (platform, draft mode, ESPN league ID, scoring file)
- `scoring_{league_id}.yaml` — one per league (5 total), not a single shared `scoring.yaml`
- `.env` (gitignored, local only) — ESPN `espn_s2`/`SWID` cookies for the local polling script

When adding a new ranking source, add a dedicated parser in `scripts/parsers/` that normalizes it to the common schema before merging.

---

## What's Left to Build

1. Python parsers for each data source (`scripts/parsers/`)
2. Aggregation + VBD scoring logic
3. `scripts/build.py` orchestration script
4. `scoring.yaml` config — one per league (5 total)
5. Real-time sync backend decision + implementation (replaces `localStorage`)
6. Multi-league support in frontend (league selector via URL param, league-scoped state)
7. ESPN live draft polling (3 ESPN leagues) with manual fallback
8. ESPN auth cookie handling (`espn_s2`, `SWID`) for private leagues

**Done:**
- `scripts/parsers/flags_sheet.py` — fetches flags live from Google Sheet at build time

---

## Future Enhancements

- ADP comparison overlay
- Positional scarcity alerts
- Trade value calculator
- Mobile-friendly layout
