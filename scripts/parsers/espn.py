"""
Parses ESPN's fantasy football player-projections API response into the
pipeline's common player schema.

Unlike every other source in this pipeline, ESPN doesn't offer a clean CSV
export or an easy manual copy - their projections page is a JavaScript app
with no static HTML to scrape. The data here (data/espn/espn_player_projections_2026.json)
was instead pulled directly from ESPN's own internal API
(lm-api-reads.fantasy.espn.com/.../kona_player_info), the same one their
website's JS calls to render the page, using a real logged-in browser
session's cookies. That fetch was a one-time, transient operation - the
session cookies/auth tokens used to make it were NEVER written to any file
in this repo (see the project's CLAUDE.md .env convention for how ESPN
auth is meant to be handled). This parser only ever reads the already-saved
JSON response, which contains no credentials, just player stats.

ESPN's stat fields are keyed by opaque numeric IDs (e.g. "23", "24") with
no human-readable names anywhere in the payload. STAT_ID_MAP below was
derived empirically, not from documentation: real, already-verified season
projections for Josh Allen and Christian McCaffrey (cross-checked against
Athletic/FantasyPros/CBS's parsed numbers for the same two players) were
compared value-by-value against ESPN's raw numbers until they lined up.
Likewise, TEAM_ID_MAP (ESPN's numeric proTeamId -> team abbreviation) was
confirmed by checking it against ~20 players with well-known teams before
being trusted for the full dataset. If ESPN ever changes these ID schemes,
this mapping needs to be re-derived the same way, not just re-guessed.
"""

import json

SOURCE_NAME = "espn"
SEASON = 2026

# ESPN's `player.stats` list holds several stat-window entries per player
# (season totals, various weekly splits, actual vs. projected, etc.),
# distinguished by an opaque "id" string. Empirically, "10" + season year
# (e.g. "102026") is the season-long PROJECTION entry (statSourceId=1);
# "00" + season year is season-long ACTUALS (statSourceId=0, not useful
# before the season starts). We want the projection.
PROJECTION_STAT_ID = f"10{SEASON}"

# player.defaultPositionId -> the board's four supported positions.
# Any position not listed here (5=K, 16=D/ST, etc.) is dropped - the board
# doesn't rank kickers or defenses (see scoring_league_*.yaml comments).
POSITION_ID_MAP = {
    1: "QB",
    2: "RB",
    3: "WR",
    4: "TE",
}

# ESPN's numeric proTeamId -> team abbreviation. 0 = no current team
# (free agent / between rosters) - real, not a mapping bug (e.g. an
# injured/unsigned player can show up this way).
TEAM_ID_MAP = {
    1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN",
    8: "DET", 9: "GB", 10: "TEN", 11: "IND", 12: "KC", 13: "LV", 14: "LAR",
    15: "MIA", 16: "MIN", 17: "NE", 18: "NO", 19: "NYG", 20: "NYJ",
    21: "PHI", 22: "ARI", 23: "PIT", 24: "LAC", 25: "SF", 26: "SEA",
    27: "TB", 28: "WSH", 29: "CAR", 30: "JAX", 33: "BAL", 34: "HOU",
}

# ESPN's numeric stat id -> this pipeline's common stat name. Derived
# empirically (see module docstring) - do not extend this table by
# guessing new ids without cross-checking against a known source first.
STAT_ID_MAP = {
    "0": "pass_att",
    "1": "pass_cmp",
    "3": "pass_yd",
    "4": "pass_td",
    "20": "pass_int",
    "23": "rush_att",
    "24": "rush_yd",
    "25": "rush_td",
    "58": "rec_tgt",
    "53": "rec",
    "42": "rec_yd",
    "43": "rec_td",
}


def parse_espn(filepath: str) -> list[dict]:
    """Parse ESPN's saved player-projections JSON into a list of player
    dicts matching the pipeline's common schema:
        {player_name, team, position, projected_stats, source}

    Players with no season-projection stat entry (e.g. free agents with no
    current team) are skipped, since there's nothing to project.
    """
    with open(filepath, encoding="utf-8") as f:
        raw_entries = json.load(f)

    players = []
    for entry in raw_entries:
        player = entry["player"]

        position = POSITION_ID_MAP.get(player["defaultPositionId"])
        if position is None:
            continue

        projection = next(
            (s for s in player.get("stats", []) if s.get("id") == PROJECTION_STAT_ID),
            None,
        )
        if projection is None:
            continue

        raw_stats = projection["stats"]
        projected_stats = {
            field: raw_stats[espn_id]
            for espn_id, field in STAT_ID_MAP.items()
            if espn_id in raw_stats
        }

        players.append({
            "player_name": player["fullName"],
            "team": TEAM_ID_MAP.get(player["proTeamId"]),
            "position": position,
            "projected_stats": projected_stats,
            "source": SOURCE_NAME,
        })

    return players


if __name__ == "__main__":
    import sys
    from collections import Counter

    path = sys.argv[1] if len(sys.argv) > 1 else "data/espn/espn_player_projections_2026.json"
    parsed = parse_espn(path)

    print(f"Parsed {len(parsed)} players from {path}")
    print("By position:", Counter(p["position"] for p in parsed))
    print("\nSample:")
    for p in parsed[:3]:
        print(p)
