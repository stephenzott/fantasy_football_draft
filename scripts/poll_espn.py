"""
Live draft-day poller for the 3 leagues that are both `platform: espn` AND
`draft_mode: live` (leagues 1, 3, 4 as of leagues.yaml - League 2 is ESPN but
drafts offline, so it's excluded by draft_mode, not platform).

Run this locally during the draft, once picks start happening:

    python scripts/poll_espn.py

What it does, every POLL_INTERVAL_SECONDS, per live-ESPN league:
  1. GET ESPN's unofficial mDraftDetail endpoint for that league.
  2. Read draftDetail.picks[].playerId - the players ESPN says are drafted.
  3. Skip any playerId already handled this run (in-memory `seen` set).
  4. Map each new playerId through data/espn/espn_id_map.json to our
     player_id. A miss (an ESPN id with no entry in the map) is logged
     loudly and skipped - it means build.py's id map is stale, or a player
     ESPN drafted has no projection from any of our sources.
  5. PUT `true` directly to the Firebase REST endpoint for that player's
     drafted path - the exact same path the board's manual DRAFTED button
     writes to, so this poller and manual clicks can never conflict, only
     both end up writing the same `true`.

This is a fallback-friendly design, not a bulletproof one (see CLAUDE.md):
the manual DRAFTED button on the board keeps working the whole time, so a
missed poll, a mapping miss, or a dead ESPN session just means falling back
to clicking the button by hand for that one pick - it does not block the
draft. Accordingly, failures are logged and retried next interval rather
than raised.

Auth: ESPN's private-league API requires the espn_s2 and SWID cookies from a
real logged-in browser session. These are loaded from a local, gitignored
.env file (ESPN_S2=..., SWID=...) - see the "ESPN Projections Refresh" /
"Multi-League Support" sections of CLAUDE.md for how to grab them via
DevTools "Copy as cURL". They are NEVER committed and never touch Firebase
or the frontend - this script is the only thing that reads them, and only
to attach them as request cookies.
"""

import json
import os
import re
import sys
import time

import requests
import yaml

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPTS_DIR)

# How often to poll each live league. 10-15s per the design in CLAUDE.md:
# frequent enough to feel live, infrequent enough not to hammer ESPN's
# unofficial (undocumented, rate-limit-unknown) API.
POLL_INTERVAL_SECONDS = 12

# Season the draft is for. Must match the year embedded in
# data/espn/espn_player_projections_2026.json / scripts/parsers/espn.py's
# SEASON constant - bump both together each year.
SEASON = 2026


def _abs(*parts: str) -> str:
    return os.path.join(REPO_ROOT, *parts)


def load_env_cookies() -> dict[str, str]:
    """Hand-rolled .env reader for ESPN_S2 and SWID.

    Not using python-dotenv here - the project's requirements.txt has no
    dependency for parsing a 2-line KEY=VALUE file, and adding one just for
    this felt like overkill. This only understands plain `KEY=VALUE` lines
    (optionally quoted) and `#`-comments - enough for this file's needs.
    """
    env_path = _abs(".env")
    if not os.path.exists(env_path):
        sys.exit(
            "No .env file found at repo root. Create one with:\n"
            "  ESPN_S2=<your espn_s2 cookie value>\n"
            "  SWID=<your SWID cookie value>\n"
            "See CLAUDE.md's ESPN Projections Refresh section for how to grab these "
            "via DevTools 'Copy as cURL' (same cookies, different use)."
        )

    values: dict[str, str] = {}
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")

    missing = [k for k in ("ESPN_S2", "SWID") if not values.get(k)]
    if missing:
        sys.exit(f".env is missing required key(s): {', '.join(missing)}")

    return {"espn_s2": values["ESPN_S2"], "SWID": values["SWID"]}


def load_live_espn_leagues() -> list[dict]:
    """Read leagues.yaml and keep only platform=espn AND draft_mode=live
    leagues - the only ones with a live draft room to poll (see
    "ESPN Live Draft Polling" in CLAUDE.md for why League 2 is excluded
    despite being ESPN).
    """
    with open(_abs("leagues.yaml"), encoding="utf-8") as f:
        leagues = yaml.safe_load(f)["leagues"]
    return [
        lg for lg in leagues
        if lg["platform"] == "espn" and lg["draft_mode"] == "live"
    ]


def load_id_map() -> tuple[dict[str, str], set[str]]:
    """Return (player_id_map, non_board_espn_ids).

    non_board_espn_ids are K/DST players build.py's ESPN parser drops (the
    board doesn't rank them) - a pick matching one of these is expected and
    silent, not a MAPPING MISS.
    """
    path = _abs("data", "espn", "espn_id_map.json")
    if not os.path.exists(path):
        sys.exit(
            f"{path} not found. Run `python scripts/build.py` first - it "
            "generates the ESPN id map alongside players.json."
        )
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["player_id_map"], set(data["non_board_espn_ids"])


def load_database_url() -> str:
    """Pull databaseURL out of docs/firebase-config.js by regex rather than
    hardcoding it a second time here - firebase-config.js is already the
    single source of truth the frontend reads, so this keeps it that way
    instead of letting the two drift.
    """
    path = _abs("docs", "firebase-config.js")
    with open(path, encoding="utf-8") as f:
        contents = f.read()

    match = re.search(r'databaseURL:\s*"([^"]+)"', contents)
    if not match:
        sys.exit(f"Could not find databaseURL in {path}")
    url = match.group(1)
    if "PASTE" in url:
        sys.exit(
            f"{path} still has placeholder Firebase config - "
            "finish the one-time Firebase console setup first (see CLAUDE.md)."
        )
    return url.rstrip("/")


def fetch_draft_picks(league: dict, cookies: dict[str, str]) -> list[int]:
    """GET ESPN's mDraftDetail view for one league; return the list of
    ESPN playerIds that have been drafted so far (empty pre-draft).
    """
    url = (
        f"https://fantasy.espn.com/apis/v3/games/ffl/seasons/{SEASON}"
        f"/segments/0/leagues/{league['espn_league_id']}?view=mDraftDetail"
    )
    resp = requests.get(url, cookies=cookies, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    picks = data.get("draftDetail", {}).get("picks", [])
    return [pick["playerId"] for pick in picks]


def mark_drafted(database_url: str, league_id: str, player_id: str) -> None:
    """PUT true to the same Firebase path the board's manual DRAFTED button
    writes to: /leagues/{league_id}/drafted/{player_id}.
    """
    url = f"{database_url}/leagues/{league_id}/drafted/{player_id}.json"
    resp = requests.put(url, data="true", timeout=10)
    resp.raise_for_status()


def verify_auth(leagues: list[dict], cookies: dict[str, str]) -> None:
    """One GET per league before the polling loop starts.

    Pre-draft, a *successful* poll also returns no picks, and a *failed*
    poll (expired cookies) gets silently swallowed by the loop's normal
    "will retry next interval" handling - so without this check, dead
    cookies and "the draft just hasn't started yet" look identical for up
    to however long you leave the poller running. This turns that into an
    immediate, loud failure instead. Per CLAUDE.md, this same GET is also
    the one hop in the whole pipeline that can't be tested until you have
    real cookies in .env - so this doubles as that test, every run.
    """
    print("Verifying ESPN auth (pre-draft leagues respond with an empty picks list)...")
    for league in leagues:
        try:
            picks = fetch_draft_picks(league, cookies)
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status in (401, 403):
                sys.exit(
                    f"ESPN auth rejected for {league['name']} (HTTP {status}). "
                    "Cookies are likely expired - grab fresh espn_s2/SWID via DevTools "
                    "'Copy as cURL' (see CLAUDE.md) and update .env. Note SWID must "
                    "include its literal surrounding {braces}."
                )
            sys.exit(f"Unexpected HTTP error for {league['name']}: {e}")
        except requests.RequestException as e:
            sys.exit(f"Could not reach ESPN for {league['name']}: {e}")
        print(f"  [{league['name']}] OK - {len(picks)} pick(s) so far")
    print()


def poll_forever() -> None:
    cookies = load_env_cookies()
    leagues = load_live_espn_leagues()
    id_map, non_board_ids = load_id_map()
    database_url = load_database_url()

    if not leagues:
        sys.exit("No leagues in leagues.yaml have platform=espn and draft_mode=live.")

    verify_auth(leagues, cookies)

    print(f"Polling {len(leagues)} live ESPN league(s) every {POLL_INTERVAL_SECONDS}s:")
    for lg in leagues:
        print(f"  - {lg['name']} ({lg['id']}, espn_league_id={lg['espn_league_id']})")
    print("Manual DRAFTED button remains a fallback throughout - Ctrl+C to stop.\n")

    # Picks already pushed to Firebase this run, per league. Starts empty
    # every run (not persisted), so a fresh start re-pushes the current
    # drafted set once - harmless, since the write is idempotent (`true`
    # over `true`), and useful as a catch-up after a restart.
    seen: dict[str, set[int]] = {lg["id"]: set() for lg in leagues}

    while True:
        for league in leagues:
            league_id = league["id"]
            try:
                espn_player_ids = fetch_draft_picks(league, cookies)
            except requests.RequestException as e:
                print(f"[{league['name']}] poll failed, will retry next interval: {e}")
                continue

            new_ids = [pid for pid in espn_player_ids if pid not in seen[league_id]]
            for espn_id in new_ids:
                if str(espn_id) in non_board_ids:
                    # Expected: a K/DST pick. The board doesn't rank kickers
                    # or defenses, so there's nothing to mark - silent by
                    # design (see espn.py / build.py).
                    seen[league_id].add(espn_id)
                    continue

                player_id = id_map.get(str(espn_id))
                if player_id is None:
                    print(f"[{league['name']}] MAPPING MISS - no player_id for "
                          f"espn_id={espn_id}; mark this pick manually on the board.")
                    seen[league_id].add(espn_id)  # don't retry a miss every interval
                    continue

                try:
                    mark_drafted(database_url, league_id, player_id)
                    print(f"[{league['name']}] drafted: {player_id} (espn_id={espn_id})")
                    seen[league_id].add(espn_id)
                except requests.RequestException as e:
                    print(f"[{league['name']}] Firebase write failed for {player_id}, "
                          f"will retry next interval: {e}")
                    # Not added to `seen` - retried next poll.

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        poll_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
