"""
Parses CBS Sports' fantasy projections CSV into the pipeline's common
player schema. Added in place of Yahoo, which doesn't publish full stat
projections.

Unlike Athletic/FantasyPros/SI, CBS's file is one flat table covering all
four positions (QB/RB/WR/TE) with unique column names - no repeated
"YDS"/"TDS" headers to disambiguate by position, so this parser can map
columns by header name via csv.DictReader instead of hardcoded column
indices.

CBS also doesn't give player/position/team as separate columns - they're
all crammed into one "Player" cell, e.g. "Michael Penix Jr. QB  ATL". We
split that from the RIGHT: the last whitespace-separated token is the team,
the second-to-last is the position, and everything before that (rejoined)
is the player's name - this correctly keeps multi-word suffixes like
"Jr."/"Sr."/"II" as part of the name no matter how many words are in it.
"""

import csv

SOURCE_NAME = "cbs"

# CBS's own header text -> this pipeline's common stat name. Columns not
# listed here (gp, passing yards/game, passer rating, rushing yards per
# attempt, receiving yards per game, receiving yards per reception) are
# either derived/redundant stats or not fantasy-relevant, and are dropped.
#
# "fpts"/"fppg" (CBS's own computed fantasy points, total and per-game) are
# also deliberately dropped rather than mapped to projected_points - same
# reasoning as every other parser in this pipeline (see athletic.py,
# fantasypros.py, si.py): projected_points gets computed per-league from
# raw stats via scoring_league_*.yaml, so passing through CBS's own point
# total would give every league identical CBS-scored numbers.
STAT_COLUMN_MAP = {
    "passing att": "pass_att",
    "passing completions": "pass_cmp",
    "passing yards": "pass_yd",
    "passing tds": "pass_td",
    "passing interceptions": "pass_int",
    "rushing attempts": "rush_att",
    "rushing yards": "rush_yd",
    "rushing tds": "rush_td",
    "targets": "rec_tgt",
    "receptions": "rec",
    "receiving yards": "rec_yd",
    "receiving tds": "rec_td",
    "fumbles": "fumble_lost",
}

VALID_POSITIONS = {"QB", "RB", "WR", "TE", "FB"}

# CBS lists fullbacks under their own "FB" tag, which the board has no
# column for - fold them into RB, since FBs are typically RB/FLEX-eligible
# on most fantasy platforms anyway.
POSITION_ALIASES = {"FB": "RB"}


def _split_player_cell(cell: str) -> tuple[str, str, str]:
    """Split e.g. "Michael Penix Jr. QB  ATL" into
    ("Michael Penix Jr.", "QB", "ATL").
    """
    tokens = cell.split()
    if len(tokens) < 3 or tokens[-2] not in VALID_POSITIONS:
        raise ValueError(
            f"Could not parse name/position/team out of CBS Player cell {cell!r} - "
            f"expected '<name> <QB|RB|WR|TE|FB> <TEAM>'."
        )
    team = tokens[-1]
    position = POSITION_ALIASES.get(tokens[-2], tokens[-2])
    name = " ".join(tokens[:-2])
    return name, position, team


def _parse_number(value: str) -> float:
    return float(value.replace(",", "")) if value.strip() else 0.0


def parse_cbs(filepath: str) -> list[dict]:
    """Parse CBS's 'CBS Sports Fantasy Projections - QB-WR-RB-TE.csv' export
    into a list of player dicts matching the pipeline's common schema:
        {player_name, team, position, projected_stats, source}
    """
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    players = []
    for row in rows:
        name, position, team = _split_player_cell(row["Player"])

        projected_stats = {}
        for cbs_header, field in STAT_COLUMN_MAP.items():
            projected_stats[field] = _parse_number(row[cbs_header])

        players.append({
            "player_name": name,
            "team": team,
            "position": position,
            "projected_stats": projected_stats,
            "source": SOURCE_NAME,
        })

    return players


if __name__ == "__main__":
    import sys
    from collections import Counter

    path = sys.argv[1] if len(sys.argv) > 1 else (
        "data/cbs/CBS Sports Fantasy Projections - QB-WR-RB-TE.csv"
    )
    parsed = parse_cbs(path)

    print(f"Parsed {len(parsed)} players from {path}")
    print("By position:", Counter(p["position"] for p in parsed))
    print("\nSample:")
    for p in parsed[:3]:
        print(p)
