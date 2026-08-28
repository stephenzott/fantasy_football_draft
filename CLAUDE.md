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

Rankings/projections are downloaded before each draft from (NFL.com dropped as a source - their fantasy projections are now powered by ESPN, so it would just be a duplicate of the ESPN source below):
- FantasyPros (free) — direct CSV export
- Sleeper (free) — no manual download option; `scripts/parsers/sleeper.py` fetches live season projections from Sleeper's public read API at build time (no login/API key needed), the same live-fetch pattern as `scripts/parsers/flags_sheet.py`. Unlike ESPN, Sleeper's stat fields already have clear, human-readable names, so no empirical ID-mapping was needed. Note: this is a different use of Sleeper's API than League 5's live draft (see Multi-League Support below) - that one stays manual regardless.
- ESPN — no clean export or copyable table (JS-rendered projections page); pulled from ESPN's own internal fantasy API instead. This requires a real logged-in browser session's cookies (grabbed via DevTools "Copy as cURL"), used once to fetch a raw JSON snapshot into `data/espn/` - the cookies/auth tokens themselves are never written to any file in this repo, only the resulting player data. Since ESPN's stat fields are opaque numeric IDs with no documented mapping, `scripts/parsers/espn.py`'s `STAT_ID_MAP`/`TEAM_ID_MAP` were derived empirically by cross-checking known players' values against Athletic/FantasyPros/CBS, not from ESPN docs - re-derive the same way if ESPN ever changes these IDs. See "ESPN Projections Refresh" below for the exact manual steps.
- CBS Sports (free) — manual copy; replaces Yahoo, which doesn't offer full stat projections
- The Athletic (paid) — manual copy
- SI / FantasySports On SI (free) — manual copy

### ESPN Projections Refresh (manual steps, re-derived 2026-08-18)

`scripts/parsers/espn.py` expects `data/espn/espn_player_projections_2026.json` to be a **flat JSON array** of ~1,000+ entries, each shaped like `{"player": {..., "stats": [{"id": "10<season>", "stats": {...}}, ...]}, "ratings": ..., ...}`. Getting that exact shape out of ESPN's API takes a few non-obvious steps:

1. Log into ESPN Fantasy in Chrome with an account that has access to your leagues, open any league, and go to the **Players** tab. Switch it to a view that shows **projected stats/points** (not just a bio list) — the stats-bearing request only fires once the page needs stat data.
2. Open DevTools → **Network** tab, and filter requests using the box at the top for `kona_player_info`. This isolates the right endpoint from ESPN's many similar-looking `players`-related requests (there's also a lightweight bio-only endpoint and a paginated free-agent-search endpoint that both look plausible but lack what's needed).
3. Click the matching request → **Headers** tab → **Request Headers** → find `x-fantasy-filter`. Its value is a JSON string containing `"limit":50` (or similar) — this caps the response to 50 players. This header has no auth/cookies in it, so it's safe to inspect/edit directly.
4. Right-click the request → **Copy → Copy as cURL (bash)**.
5. Paste the copied command into a **plain-text** editor (not TextEdit's default rich-text mode — that silently saves `.rtf` even with a `.sh` name and breaks the script; use `Format → Make Plain Text` first, or just use `nano` from the terminal) as a script, e.g. `fetch_espn.sh`.
6. In that script, edit the `x-fantasy-filter` header's `"limit":50` up to something like `"limit":2000` so the response includes the full player pool, not just the top 50.
7. The raw response from this endpoint is wrapped as `{"players": [...]}`, but the parser needs the bare array. Replace the command's `-o "data/espn/espn_player_projections_2026.json"` ending with a pipe into Python to unwrap it before saving:
   ```
   | python3 -c "import json,sys; json.dump(json.load(sys.stdin)['players'], open('data/espn/espn_player_projections_2026.json','w'))"
   ```
8. Run it: `bash fetch_espn.sh` from the repo root (relative path in step 7 depends on cwd).
9. Verify: the file should be a flat list of ~1,000+ entries, each with a nested `player.stats` list containing an entry with `"id": "10<season>"` (e.g. `"102026"`). Spot-check a well-known player (e.g. Christian McCaffrey) has real stats. Running `python3 scripts/parsers/espn.py` directly prints a parsed count/position breakdown as a sanity check.
10. **Delete the script file** (`fetch_espn.sh`) once done — it contains your session cookies. Never commit it.

Manual copy/paste is the accepted approach for sources without a clean export or usable API; no parser-building planned for further sources beyond what's listed above.

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
| League 2 | ESPN (private) | Manual only — draft happens offline, so no polling despite being an ESPN league |
| League 3 | ESPN (private) | Live — poll ESPN's unofficial API + manual fallback |
| League 4 | ESPN (private) | Live — poll ESPN's unofficial API + manual fallback |
| League 5 | Sleeper | Manual only — drafting offline, so Sleeper's API isn't in play despite being available |

All 5 leagues are on a real platform (`espn` or `sleeper`) — there is no `platform: offline`. Whether a league gets live polling is controlled entirely by `draft_mode`, not by platform. 4 of the 5 leagues are ESPN; only 3 of those 4 are polled live (League 2's ESPN draft happens offline).

**Design requirements:**
- One board (`index.html`/`app.js`), league selected via URL param (e.g. `?league=espn_league_a`) — not in-memory-only state, so two tabs can independently point at two different leagues at once.
- All drafted-state and sync reads/writes scoped by `league_id` — never a flat/global drafted list. This is the guard against state bleeding between simultaneous drafts.
- Each league likely needs its own `scoring.yaml` (different scoring settings) and its own `players.json` (or one combined file keyed by league) since roster sizes / VBD baselines differ per league.
- ESPN private leagues require `espn_s2` and `SWID` auth cookies to hit the API. **Decision:** the ESPN-polling script runs locally on Stephen's laptop during the draft (not a cloud function), so cookies live in a local, gitignored `.env` file (`ESPN_S2=...`, `SWID=...`) and never touch the repo, Firebase, or the frontend.

### 4. Leagues Config — built
`leagues.yaml` at the repo root is the single source of truth for the 5 leagues. `id` is a stable slug used in file names, URL params (`?league=`), and Firebase paths — it never changes even if the league's real-world name does. `name` is the human-readable label shown in the frontend's league selector.
```yaml
leagues:
  - id: league_1
    name: "DC Brewnited"
    platform: espn
    draft_mode: live
    espn_league_id: 520090
    scoring_file: scoring_league_1.yaml
  - id: league_2
    name: "The League"
    platform: espn
    draft_mode: manual   # ESPN league, but draft happens offline; no polling
    espn_league_id: 215523
    scoring_file: scoring_league_2.yaml
  - id: league_3
    name: "Family League"
    platform: espn
    draft_mode: live
    espn_league_id: 37313507
    scoring_file: scoring_league_3.yaml
  - id: league_4
    name: "Guillotine"
    platform: espn
    draft_mode: live
    espn_league_id: 873883121
    scoring_file: scoring_league_4.yaml
  - id: league_5
    name: "LA Champions"
    platform: sleeper
    draft_mode: manual   # drafting offline; Sleeper's API isn't used despite being available
    scoring_file: scoring_league_5.yaml
```
The frontend's league selector, the build pipeline, and the ESPN poller should all read from this one file rather than hardcoding league details in multiple places.

### 5. ESPN Live Draft Polling — not yet built
- For leagues with `platform: espn` AND `draft_mode: live` only (3 of the 5 leagues). Polls ESPN's unofficial API (`https://fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{league_id}?view=mDraftDetail`) on an interval during the draft.
- Auto-marks players as drafted on the board when they appear in ESPN's draft detail response.
- Manual "DRAFTED" button remains available alongside polling, as a fallback in case of API lag/failure.
- Not applicable to the 2 manual-draft leagues (League 2, despite being ESPN, and League 5/Sleeper) — no live draft room to poll, manual marking only. Gate on `draft_mode`, not `platform`.

**Design (sketched 2026-08-23, build targeted for 2026-08-27/28 ahead of the first ESPN draft on 2026-08-28 or 2026-08-30):**
- **ID mapping** (`data/espn/espn_id_map.json`, generated alongside the existing projections parse in `scripts/parsers/espn.py` or `scripts/build.py`) — ESPN's draft picks are keyed by ESPN's own numeric player ID, not our `player_id` slug. The projections snapshot already has each player's ESPN ID + name, so build a `{espn_id: player_id}` lookup by running the name through the same normalization `scripts/merge.py` uses. Only as fresh as the last projections pull — re-running `build.py` before the draft refreshes it.
- **Poller** (`scripts/poll_espn.py`, not yet created) — loads `.env` cookies + `leagues.yaml` (filtered to the 3 `platform: espn` + `draft_mode: live` leagues) + the ID map. On an interval (~10-15s) per league: GET `mDraftDetail` with the `espn_s2`/`SWID` cookies, diff `draftDetail.picks[].playerId` against picks already written this session, map new ones through the ID table, and `PUT` `true` directly to the Firebase REST endpoint `{databaseURL}/leagues/{league_id}/drafted/{player_id}.json` — no Firebase Admin SDK needed, since `firebase-rules.json` already allows open boolean writes to that exact path (the same one the manual DRAFTED button uses). Logs each pick to the console so a mapping miss is visible immediately; failures just log and retry next interval — the manual button is the fallback, so the poller doesn't need to be bulletproof.
- **What can be tested ahead of draft day:** the ID-mapping output; a live GET against each league's `mDraftDetail` endpoint (it responds pre-draft with an empty `picks: []`, so this validates cookies + league IDs + response shape without an open draft room); and the Firebase REST write path itself via a manual `curl PUT` against a scratch player (watch it show up live on the board).
- **What has to wait for closer to draft day:** a fresh `espn_s2`/`SWID` cookie grab (same DevTools "Copy as cURL" method as the projections refresh) — these expire/rotate, so grabbing them today doesn't guarantee they're still valid by the actual draft.

### 6. Frontend (Static HTML/CSS/JS) — built, multi-league + Firebase sync
Files live in `docs/`:
- `index.html` — page structure (league `<select>` in the header, sync-status pill in the subbar). Loads `app.js` as an ES module (`<script type="module">`).
- `style.css` — dark theme, position color-coding, scanline texture
- `app.js` — all interactivity (ES module)
- `firebase-config.js` — Firebase web config; **committed as a placeholder** (values contain `PASTE`) until filled in. Public-by-design, safe to commit. See "Firebase setup" below.
- `players.json` — generated by the pipeline; an object keyed by `league_id` (`{"league_1": [...], ...}`)
- `leagues.json` — generated by the pipeline from `leagues.yaml`; `[{id, name}]` for the league selector

**Features:**
- Fetches `leagues.json` + `players.json` once at load; all leagues stay in memory, so switching leagues just re-indexes (no re-fetch)
- League selector (header-left) driven by the `?league=` URL param; a missing/unknown param falls back to the first league and rewrites the URL. Two tabs with different `?league=` run fully independently. Per-league tab titles (`{league name} · 2026`).
- Sortable columns: overall rank, position, projected points, VBD
- Position filters: ALL / QB / RB / WR / TE / FLEX (RB+WR+TE)
- "DRAFTED" button per player — dims and strikes through the row. Draft-day state lives in **Firebase Realtime Database** at `/leagues/{league_id}/drafted/{player_id}` (value `true`; `remove()` on undo), keyed by `player_id`, scoped per league. Firebase is the single source of truth: the button only *writes*; an `onValue` listener rebuilds the drafted set from the snapshot and re-renders (RTDB fires it immediately from local cache, so the UI stays instant). The listener is torn down and re-subscribed on every league switch, so state can't bleed across leagues.
- Sync-status pill (subbar): **SYNCED** (green) / **OFFLINE** (red) / **NOT SYNCED** (amber, when `firebase-config.js` is still the placeholder). Firebase is a **hard replacement** for localStorage — no localStorage fallback, so an outage is visible rather than silently saving locally.
- Resilience: the Firebase SDK is loaded via lazy `import()` inside `initFirebase()`, and the board renders before Firebase comes up — so an unreachable CDN or missing config degrades to an unsynced board that still shows rankings (picks become ephemeral/in-memory), never a blank page.
- "HIDE DRAFTED" toggle — removes drafted players from view
- "DV LIST" toggle — shows all players with entries in their `flags` array
- Click a row to expand per-source projection breakdown and flag details
- Red dot indicator on player name for flagged players

**Firebase setup (one-time, done by Stephen in the Firebase console):**
1. Create a project at <https://console.firebase.google.com> and add a **Web App** — Firebase shows a `firebaseConfig` object.
2. Enable **Realtime Database** (not Firestore).
3. Paste the config values into `docs/firebase-config.js` (replacing the `PASTE_*` placeholders).
4. In Realtime Database → Rules, paste the contents of `firebase-rules.json` (repo root). These are structure-scoped: the only writable path is `/leagues/{league_id}/drafted/{player_id}`, booleans only — anyone with the DB URL could add/clear drafted picks but can't write anything else. (Chosen for a semi-private 2-person board.)
5. Commit the filled-in `firebase-config.js` (public-by-design). Sync then works across all tabs/devices pointed at the same `league_id`.

### `players.json` schema
Top level is an object keyed by `league_id`; each value is that league's ranked player array. Each player object:
```json
{
  "player_id": "christian-mccaffrey-rb",
  "name": "Christian McCaffrey",
  "team": "SF",
  "position": "RB",
  "rank": 1,
  "pos_rank": "RB1",
  "projected_points": 412.3,
  "vbd": 252.1,
  "sources": { "fantasypros": 418.2, "sleeper": 405.1, "espn": 413.6, "cbs": 410.0, "athletic": 415.8 },
  "flags": [],
  "injuries": []
}
```
- `player_id` — Firebase-safe slug (`{normalized-name}-{position}`), the stable identity used for drafted state + future Firebase sync.
- `sources` — per-source converted points. SI is **not** included (its combined-only stats can't be scored); the other 5 sources appear when they have the player.
- `flags` — conduct/legal concerns, format `"{incident} — {resolution}"`. Empty array if none.
- `injuries` — injury/availability concerns, plain strings. Currently always empty (no injuries source yet).

### Player Flags
Flags are stored directly on each player object in `players.json`. The pipeline fetches them live from a Google Sheet at build time and joins them onto players. An empty `flags: []` means no concerns.

**Source:** Google Sheet ID `1PdD1hmkFPRgOJ_lDb4bhieYV4B4hy0zcBsIkDxJAkEs`
**Parser:** `scripts/parsers/flags_sheet.py` → `fetch_flags()` returns `dict[lowercase_name → list[str]]`
**Sharing:** Sheet must be set to "Anyone with the link can view" for the CSV export URL to work.
**Format:** Columns — Date | First Name | Last Name | Team | Incident | Resolution. Multiple rows per player are merged into one flags list.

---

## Scoring System Configuration

Define each league's scoring settings in `scoring_{league_id}.yaml`, mirroring ESPN's own scoring-settings categories so values can be copy-checked directly against the league's ESPN "Scoring Settings" page:

```yaml
passing:
  pass_yd: 0.04
  pass_td: 4
  pass_int: -2      # interception thrown, applies to QB
  pass_2pt: 2
rushing:
  rush_yd: 0.1
  rush_td: 6
  rush_2pt: 2
receiving:
  reception: 1      # points per reception (PPR) — varies by league (0, 0.5, 1, etc.)
  rec_yd: 0.1
  rec_td: 6
  rec_2pt: 2
kicking:            # captured for potential future K support; board doesn't rank kickers yet
  pat_made: 1
  fg_missed: -1
  fg_0_39: 3
  fg_40_49: 4
  fg_50_59: 5
  fg_60_plus: 5
defense_special_teams:   # captured for potential future D/ST support; board doesn't rank DST yet
  kickoff_return_td: 6
  punt_return_td: 6
  int_return_td: 6
  fumble_return_td: 6
  blocked_return_td: 6
  two_pt_return: 2
  safety_1pt: 1
  sack: 1
  blocked_kick: 2
  interception: 2
  fumble_recovery: 2
  safety: 2
  points_allowed:
    "0": 5
    "1-6": 4
    "7-13": 3
    "14-17": 1
    "18-27": 0
    "28-34": -1
    "35-45": -3
    "46+": -5
  yards_allowed:
    "<100": 5
    "100-199": 3
    "200-299": 2
    "300-349": 0
    "350-399": -1
    "400-449": -3
    "450-499": -5
    "500-549": -6
    "550+": -7
```

Only the `passing`, `rushing`, and `receiving` sections are used by the pipeline today, since the board's position filters are QB/RB/WR/TE only (no K/DST). The `kicking` and `defense_special_teams` sections are stored for parity with each league's real ESPN settings in case K/DST support is added later.

---

## Draft Day Workflow

1. Run `python scripts/build.py` the morning of the draft to regenerate `players.json` for all 5 leagues (reads `leagues.yaml` + each league's `scoring.yaml`)
2. Open `docs/index.html` (or the GitHub Pages URL), select the correct league from the league selector — the URL updates to `?league={league_id}`
3. For the 3 live-draft ESPN leagues: start the local ESPN-polling script (reads cookies from local `.env`) before the draft begins so picks auto-sync to Firebase
4. For the 2 manual-draft leagues (League 2/ESPN drafted offline, League 5/Sleeper): no polling script — mark players manually as they're drafted
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
- `docs/` — GitHub Pages root; `index.html`, `style.css`, `app.js`, `players.json`, `leagues.json`, `firebase-config.js`
- `firebase-rules.json` (repo root) — Realtime Database security rules, pasted into the Firebase console
- `scripts/` — Python data pipeline scripts
- `scripts/parsers/` — one parser per source, each normalizing to the common schema
- `flags/` — player flag source data (joined onto players during pipeline build)
- `leagues.yaml` — single source of truth for the 5 leagues (platform, draft mode, ESPN league ID, scoring file)
- `scoring_{league_id}.yaml` — one per league (5 total), not a single shared `scoring.yaml`
- `.env` (gitignored, local only) — ESPN `espn_s2`/`SWID` cookies for the local polling script

When adding a new ranking source, add a dedicated parser in `scripts/parsers/` that normalizes it to the common schema before merging.

---

## What's Left to Build

1. **Firebase project creation (Stephen, in the console)** — the sync *code* is done; going live needs the one-time console setup in "Firebase setup" above (create project, enable Realtime Database, paste config into `docs/firebase-config.js`, paste rules from `firebase-rules.json`). Until then the board runs unsynced ("NOT SYNCED" pill, in-memory picks).
2. ESPN live draft polling (3 ESPN leagues) with manual fallback — design sketched under "ESPN Live Draft Polling" above (2026-08-23); build targeted for 2026-08-27/28, ahead of the first ESPN draft (2026-08-28 or 2026-08-30)
3. ESPN auth cookie handling (`espn_s2`, `SWID`) for private leagues — note this is a separate concern from the one-time projections pull above: draft-day polling needs a persistent local `.env`, the projections pull was a one-time transient fetch; grab fresh cookies close to the build/draft date since they expire

**Done:**
- Mobile-friendly board — a COMPACT toggle (header) shrinks each row to rank/name/DV-flag/position; team, pos-rank, FPTS, VBD, and the DRAFTED button move into the existing tap-to-expand detail row instead of disappearing. Below 640px the header itself collapses to a single sticky row (title + league select + a FILTERS button) that opens search/position-filters/toggles as a dropdown panel, rather than overflowing several always-visible rows. Verified in-browser (compact toggle, header collapse/dropdown open-close, DV-flag tap-target sizing, no horizontal scroll at phone width).
- Firebase realtime sync (code) — drafted state at `/leagues/{league_id}/drafted/{player_id}` in Realtime Database, keyed by `player_id`, scoped per league; write-only button + `onValue` listener as single source of truth; listener re-subscribed on league switch; hard replacement for localStorage with a live sync-status pill; SDK lazy-imported so a CDN/config failure degrades to an unsynced-but-working board. `firebase-rules.json` (repo root) holds the structure-scoped security rules. Code-complete and self-verified in-browser (board renders, unconfigured→"NOT SYNCED", configured wiring loads the SDK and reports OFFLINE against an unreachable DB); **live cross-device sync unverified until the Firebase project is created** (item 1 above).
- Multi-league frontend — league `<select>` populated from `docs/leagues.json`, active league via `?league=` (bad/missing param falls back to first league + rewrites URL), drafted state scoped per league and keyed by `player_id`, per-league tab titles. Combined `players.json` fetched once and re-indexed in memory on switch. Verified in-browser: two-tab isolation and in-tab switching keep drafted sets separate; same WR shows the expected full-PPR vs no-PPR point gap per league.
- `scripts/scoring.py` — converts a player's raw `projected_stats` to fantasy points under one league's scoring; maps `reception` (scoring key) → `rec` (parser stat key) explicitly, and raises on any unmapped scoring key. 2pt conversions + `fumble_lost` intentionally unscored in v1 (only some sources emit them; scoring them would make the same player differ across leagues for non-scoring reasons).
- `scripts/merge.py` — normalizes names (accent/punctuation/suffix stripping + a `NAME_ALIASES` table for nicknames), mints a Firebase-safe `player_id`, merges the 5 scoring-eligible sources into one row per player (majority-vote team/position), joins flags, and prints a **match report** (source-count per player; 1-source players flagged as likely normalization misses). SI excluded — its combined-only stats can't be scored.
- `scripts/aggregate.py` — per league: scores each source then averages → `projected_points`, ranks overall + positionally, computes VBD vs a positional baseline. Baseline rank = `teams × starters[pos] + teams × FLEX × FLEX_SPLIT[pos]` with `FLEX_SPLIT = {RB:0.50, WR:0.40, TE:0.10}`.
- `scripts/build.py` — orchestrates: parse 6 sources + flags once (network fetches happen once, outside the per-league loop), merge, then per league score/rank/VBD → combined `docs/players.json`. Run `python scripts/build.py`. **Requires network** (Sleeper + flags sheet fetch live).
- `leagues.yaml` `roster` blocks — per-league `teams` + `starters` (QB/RB/WR/TE/FLEX), the source for VBD baselines.
- `scripts/parsers/flags_sheet.py` — fetches flags live from Google Sheet at build time
- `scripts/parsers/athletic.py` — parses The Athletic's 4-block side-by-side CSV export
- `scripts/parsers/fantasypros.py` — parses FantasyPros' 4 per-position CSV exports (QB/RB/WR/TE; K/DST/FLX intentionally not parsed)
- `scripts/parsers/si.py` — parses SI's 4-block CSV; converts per-game rates to season totals, only has combined total_yd/total_td (no pass/rush/rec split)
- `scripts/parsers/cbs.py` — parses CBS's flat combined CSV; FB position folded into RB
- `scripts/parsers/espn.py` — parses a saved ESPN API JSON snapshot (see Data Sources above for how it's obtained); stat/team ID mappings derived empirically, not from docs
- `scripts/parsers/sleeper.py` — fetches live from Sleeper's public projections API (no manual file); human-readable stat field names, no ID-mapping needed
- `leagues.yaml` — single source of truth for all 5 leagues (id, name, platform, draft_mode, espn_league_id, scoring_file)
- `scoring_league_1.yaml` (DC Brewnited, ESPN) — full PPR, pass_int -2
- `scoring_league_2.yaml` (The League, ESPN) — standard/no PPR, pass_int -2
- `scoring_league_3.yaml` (Family League, ESPN) — full PPR, pass_int -2; FG 60+ = 6, no yards-allowed bonus, adds misc fumble-lost/fumble-recovery-TD
- `scoring_league_4.yaml` (Guillotine, ESPN) — half-PPR, pass_int -1, no FG-missed penalty
- `scoring_league_5.yaml` (LA Champions, Sleeper) — half-PPR; structurally different from the ESPN leagues (no yards-allowed bonus, adds fumble_lost penalty, separate special-teams-player scoring)

---

## Future Enhancements

- ADP comparison overlay
- Positional scarcity alerts
- Trade value calculator
