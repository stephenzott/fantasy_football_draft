"""
Build pipeline entry point. Run the morning of the draft:

    python scripts/build.py

It reads every ranking source once, merges them into one player per person,
then - for each league in leagues.yaml - scores and ranks those players
under that league's own scoring settings, and writes a single combined
docs/players.json keyed by league_id.

Why parse once, up front (outside the per-league loop): the raw projected
stats are the same no matter which league's scoring you apply. Two of the
sources (Sleeper and the flags Google Sheet) are fetched live over the
network, so pulling them once - rather than 5 times inside the league loop -
avoids 5x the requests and guarantees all leagues score against the exact
same snapshot of the data.

SI is deliberately excluded from the whole pipeline: its export only gives
combined total_yd / total_td (no pass/rush/rec split, no receptions), which
can't be converted to points under any of these leagues' scoring, so it
would contribute neither valid points nor a valid per-source breakdown.

Output shape (combined, keyed by league_id):
    { "league_1": [ {player}, ... ], "league_2": [ ... ], ... }
NOTE: the current docs/app.js still expects a flat array from a single
players.json - updating the frontend to read this per-league object (via
the ?league= URL param) is a separate, already-planned task.
"""

import json
import os
import sys

# Make sibling modules (scoring, merge, aggregate) and the parsers subpackage
# importable no matter what directory the script is launched from. This is a
# standard-practice shim, not anything mathematical: we compute the absolute
# path of scripts/ and put it at the front of Python's import search path.
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPTS_DIR)
sys.path.insert(0, SCRIPTS_DIR)

import yaml  # noqa: E402  (import after sys.path shim, intentionally)

from scoring import load_scoring  # noqa: E402
from merge import merge_sources, print_match_report  # noqa: E402
from aggregate import aggregate_league  # noqa: E402

from parsers.fantasypros import parse_fantasypros  # noqa: E402
from parsers.athletic import parse_athletic  # noqa: E402
from parsers.cbs import parse_cbs  # noqa: E402
from parsers.espn import parse_espn  # noqa: E402
from parsers.sleeper import parse_sleeper  # noqa: E402
from parsers.flags_sheet import fetch_flags  # noqa: E402


def _abs(*parts: str) -> str:
    """Join path parts onto the repo root and return an absolute path, so
    file locations don't depend on the caller's current directory.
    """
    return os.path.join(REPO_ROOT, *parts)


def parse_all_sources() -> list[list[dict]]:
    """Run every scoring-eligible parser once and return their player lists.

    Each entry is one source's list of players in the common parser schema.
    SI is not included here (see module docstring). Order doesn't matter -
    merge.py groups by player, not by source position.
    """
    print("Parsing sources...")

    fantasypros = parse_fantasypros(_abs("data", "fantasypros"))
    print(f"  fantasypros: {len(fantasypros)} players")

    athletic = parse_athletic(_abs("data", "athletic", "The Athletic - Ranks w Proj.csv"))
    print(f"  athletic:    {len(athletic)} players")

    cbs = parse_cbs(_abs("data", "cbs", "CBS Sports Fantasy Projections - QB-WR-RB-TE.csv"))
    print(f"  cbs:         {len(cbs)} players")

    espn = parse_espn(_abs("data", "espn", "espn_player_projections_2026.json"))
    print(f"  espn:        {len(espn)} players")

    sleeper = parse_sleeper()  # live fetch from Sleeper's public API
    print(f"  sleeper:     {len(sleeper)} players (live)")

    return [fantasypros, athletic, cbs, espn, sleeper]


def load_leagues() -> list[dict]:
    """Read leagues.yaml (the single source of truth for the 5 leagues)."""
    with open(_abs("leagues.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)["leagues"]


def build() -> None:
    # --- 1. Parse every source once (league-independent raw stats) ---
    source_lists = parse_all_sources()

    # --- 2. Fetch conduct flags once (live from the Google Sheet) ---
    print("Fetching player flags...")
    flags = fetch_flags()
    print(f"  {len(flags)} flagged player(s)")

    # --- 3. Merge into one row per player (league-independent) ---
    print("Merging sources...")
    merged = merge_sources(source_lists, flags)
    print_match_report(merged, expected_sources=len(source_lists))

    # --- 4. Per league: score + rank + VBD under that league's settings ---
    leagues = load_leagues()
    output: dict[str, list[dict]] = {}
    for league in leagues:
        league_id = league["id"]
        scoring = load_scoring(_abs(league["scoring_file"]))
        players = aggregate_league(merged, scoring, league["roster"])
        output[league_id] = players
        print(f"  {league_id} ({league['name']}): {len(players)} players ranked")

    # --- 5. Write the combined, per-league-keyed players.json ---
    out_path = _abs("docs", "players.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {out_path}")

    # --- 6. Write docs/leagues.json for the frontend's league selector ---
    # The frontend can't read leagues.yaml (it lives at the repo root, while
    # GitHub Pages only serves docs/), so we emit just the id + display name
    # of each league here. leagues.yaml stays the single source of truth -
    # this file is derived from it every build, never hand-edited.
    leagues_out = [{"id": lg["id"], "name": lg["name"]} for lg in leagues]
    leagues_path = _abs("docs", "leagues.json")
    with open(leagues_path, "w", encoding="utf-8") as f:
        json.dump(leagues_out, f, indent=2, ensure_ascii=False)
    print(f"Wrote {leagues_path}")


if __name__ == "__main__":
    build()
