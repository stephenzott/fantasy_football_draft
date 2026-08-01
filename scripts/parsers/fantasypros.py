"""
Parses FantasyPros' per-position CSV exports into the pipeline's common
player schema.

FantasyPros exports one CSV per position (QB.csv, RB.csv, WR.csv, TE.csv,
plus K/DST/FLX which we don't use - see NOTE below). Within a single
position file, the same header name repeats for different stats - e.g.
the QB file has two "YDS" columns (passing yards, then rushing yards) and
two "TDS" columns (passing TDs, then rushing TDs). Because of that, we
can't map columns by header name (there's no way to tell the two "YDS"
columns apart by name alone) - we map by column POSITION instead, using
the header row only as a sanity check that FantasyPros hasn't reordered
their export since this parser was written.

NOTE: K (kickers) and DST (team defense) exports exist in data/fantasypros/
but aren't parsed - the draft board only ranks QB/RB/WR/TE. FLX also isn't
parsed - it's just RB/WR/TE re-ranked together in one FantasyPros-defined
overall order, which would duplicate players already covered by the RB/WR/TE
files.
"""

import csv
import os

SOURCE_NAME = "fantasypros"

# For each position: the exact header row FantasyPros is expected to
# produce (used to fail loudly if their export format ever changes), and
# the column-index -> stat-name mapping for that file.
#
# "FPTS" (FantasyPros' own computed fantasy points) is deliberately left
# out of every mapping below and dropped, not stored as projected_points -
# this pipeline computes projected_points itself from raw stats using each
# league's own scoring_league_*.yaml, the same reasoning as the Athletic
# parser (scripts/parsers/athletic.py).
POSITION_CONFIG = {
    "QB": {
        "filename": "FantasyPros_Fantasy_Football_Projections_QB.csv",
        "expected_header": [
            "Player", "Team", "ATT", "CMP", "YDS", "TDS", "INTS",
            "ATT", "YDS", "TDS", "FL", "FPTS",
        ],
        "columns": {
            0: "player_name", 1: "team",
            2: "pass_att", 3: "pass_cmp", 4: "pass_yd", 5: "pass_td", 6: "pass_int",
            7: "rush_att", 8: "rush_yd", 9: "rush_td",
            10: "fumble_lost",
        },
    },
    "RB": {
        "filename": "FantasyPros_Fantasy_Football_Projections_RB.csv",
        "expected_header": [
            "Player", "Team", "ATT", "YDS", "TDS", "REC", "YDS", "TDS", "FL", "FPTS",
        ],
        "columns": {
            0: "player_name", 1: "team",
            2: "rush_att", 3: "rush_yd", 4: "rush_td",
            5: "rec", 6: "rec_yd", 7: "rec_td",
            8: "fumble_lost",
        },
    },
    "WR": {
        "filename": "FantasyPros_Fantasy_Football_Projections_WR.csv",
        "expected_header": [
            "Player", "Team", "REC", "YDS", "TDS", "ATT", "YDS", "TDS", "FL", "FPTS",
        ],
        "columns": {
            0: "player_name", 1: "team",
            2: "rec", 3: "rec_yd", 4: "rec_td",
            5: "rush_att", 6: "rush_yd", 7: "rush_td",
            8: "fumble_lost",
        },
    },
    "TE": {
        "filename": "FantasyPros_Fantasy_Football_Projections_TE.csv",
        "expected_header": [
            "Player", "Team", "REC", "YDS", "TDS", "FL", "FPTS",
        ],
        "columns": {
            0: "player_name", 1: "team",
            2: "rec", 3: "rec_yd", 4: "rec_td",
            5: "fumble_lost",
        },
    },
}


def _parse_number(value: str) -> float:
    """FantasyPros formats big numbers with a thousands comma (e.g.
    "1,381.0"), which float() can't parse directly - strip it first.
    """
    return float(value.replace(",", ""))


def _parse_position_file(filepath: str, position: str, config: dict) -> list[dict]:
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    header_row = [cell.strip() for cell in rows[0]]
    if header_row != config["expected_header"]:
        raise RuntimeError(
            f"{filepath}: header row {header_row!r} does not match the "
            f"expected layout {config['expected_header']!r}. FantasyPros "
            f"may have changed their export format - update POSITION_CONFIG "
            f"in scripts/parsers/fantasypros.py before trusting this file."
        )

    players = []
    for row in rows[1:]:
        # FantasyPros' export has a stray near-blank row right after the
        # header (just spaces/empty cells) - skip any row with no player
        # name rather than special-casing "row 2" specifically, since that
        # also naturally handles a trailing blank line at EOF.
        if not row or not row[0].strip():
            continue

        player = {
            "player_name": None,
            "team": None,
            "position": position,
            "projected_stats": {},
            "source": SOURCE_NAME,
        }
        for col_idx, field in config["columns"].items():
            value = row[col_idx].strip() if col_idx < len(row) else ""
            if field in ("player_name", "team"):
                player[field] = value
            else:
                player["projected_stats"][field] = _parse_number(value) if value else 0.0

        players.append(player)

    return players


def parse_fantasypros(data_dir: str = "data/fantasypros") -> list[dict]:
    """Parse all four FantasyPros position files in data_dir and return one
    combined list of player dicts in the pipeline's common schema.
    """
    all_players = []
    for position, config in POSITION_CONFIG.items():
        filepath = os.path.join(data_dir, config["filename"])
        all_players.extend(_parse_position_file(filepath, position, config))
    return all_players


if __name__ == "__main__":
    import sys
    from collections import Counter

    directory = sys.argv[1] if len(sys.argv) > 1 else "data/fantasypros"
    parsed = parse_fantasypros(directory)

    print(f"Parsed {len(parsed)} players from {directory}")
    print("By position:", Counter(p["position"] for p in parsed))
    print("\nSample:")
    for p in parsed[:3]:
        print(p)
