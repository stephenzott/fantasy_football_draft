"""
Fetches Sleeper's live season projections for QB/RB/WR/TE and normalizes
them into the pipeline's common player schema.

Sleeper has no manual-download option for projections (see CLAUDE.md's
Data Sources section), so - like scripts/parsers/flags_sheet.py does for
the Google Sheet - this parser fetches live from Sleeper's public API at
build time rather than reading a file out of data/sleeper/. The endpoint
needs no login or API key.

Unlike ESPN's API (scripts/parsers/espn.py), Sleeper's stat fields already
have clear, human-readable names (pass_yd, rec_td, fum_lost, ...), so no
empirical ID-mapping was needed here - confirmed by checking Josh Allen's
and Jahmyr Gibbs' Sleeper numbers against their already-verified
Athletic/FantasyPros/CBS/ESPN projections, which all lined up.
"""

import requests

SOURCE_NAME = "sleeper"
SEASON = 2026
VALID_POSITIONS = ("QB", "RB", "WR", "TE")

# Sleeper's own stat field name -> this pipeline's common stat name. Most
# names already match; only fum_lost is renamed, for consistency with the
# other parsers (fantasypros.py, cbs.py) that call this fumble_lost.
#
# Sleeper's own computed point totals (pts_ppr, pts_std, pts_half_ppr) are
# deliberately excluded, along with ADP, first-down, and reception-distance
# -bucket fields - same reasoning as every other parser in this pipeline:
# projected_points gets computed per-league from raw stats via each
# league's scoring_league_*.yaml, not taken from a source's own scoring.
STAT_FIELD_MAP = {
    "pass_att": "pass_att",
    "pass_cmp": "pass_cmp",
    "pass_yd": "pass_yd",
    "pass_td": "pass_td",
    "pass_int": "pass_int",
    "pass_2pt": "pass_2pt",
    "rush_att": "rush_att",
    "rush_yd": "rush_yd",
    "rush_td": "rush_td",
    "rush_2pt": "rush_2pt",
    "rec": "rec",
    "rec_yd": "rec_yd",
    "rec_td": "rec_td",
    "rec_2pt": "rec_2pt",
    "fum_lost": "fumble_lost",
}


def parse_sleeper(season: int = SEASON) -> list[dict]:
    """Fetch Sleeper's live season projections and return a list of player
    dicts matching the pipeline's common schema:
        {player_name, team, position, projected_stats, source}
    """
    position_query = "&".join(f"position[]={pos}" for pos in VALID_POSITIONS)
    url = (
        f"https://api.sleeper.app/projections/nfl/{season}"
        f"?season_type=regular&{position_query}"
    )

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    raw_entries = response.json()

    players = []
    for entry in raw_entries:
        player = entry.get("player")
        if player is None:
            continue

        position = player.get("position")
        if position not in VALID_POSITIONS:
            continue

        raw_stats = entry.get("stats") or {}
        projected_stats = {
            field: raw_stats[sleeper_key]
            for sleeper_key, field in STAT_FIELD_MAP.items()
            if sleeper_key in raw_stats
        }
        if not projected_stats:
            continue  # no meaningful projection for this player (e.g. deep bench/inactive)

        players.append({
            "player_name": f"{player['first_name']} {player['last_name']}",
            "team": player.get("team"),
            "position": position,
            "projected_stats": projected_stats,
            "source": SOURCE_NAME,
        })

    return players


if __name__ == "__main__":
    from collections import Counter

    parsed = parse_sleeper()
    print(f"Parsed {len(parsed)} players from Sleeper's live API")
    print("By position:", Counter(p["position"] for p in parsed))
    print("\nSample:")
    for p in parsed[:3]:
        print(p)
