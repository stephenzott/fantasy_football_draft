"""
Parses Sports Illustrated's (SI / FantasySports On SI) PPR projections CSV
into the pipeline's common player schema.

Like The Athletic's export (scripts/parsers/athletic.py), this file is four
position tables (QB, RB, WR, TE) sitting side by side rather than one table
with a position column - but unlike Athletic's file, there's no blank
separator column between them, so the four 6-column blocks are simply
adjacent: QB = columns 0-5, RB = columns 6-11, WR = columns 12-17,
TE = columns 18-23. Row 0 is a section-title row (not real headers) and
row 1 is the real header row; data starts at row 2.

SI's data is much thinner than Athletic/FantasyPros: no pass/rush/rec
split, no attempts/completions/receptions/interceptions/fumbles - just one
combined total-yards figure and one combined TD figure per player, both
reported as PER-GAME rates (TOT YPG, TD/G) rather than season totals. This
parser multiplies both by SEASON_GAMES to produce season totals so this
source's numbers are on the same footing as Athletic's/FantasyPros' season
totals once they're all merged later - per-game vs season-total is a unit
mismatch that would otherwise silently corrupt any average across sources.

TE's header row is a known labeling glitch in SI's own sheet: QB/RB/WR all
end "..., TOT YPG, TD/G", but TE's ends "..., YPG, TOT YPG" (no "TD/G" at
all). The actual numbers in TE's last two columns are the same magnitude as
the other three blocks' TOT YPG/TD-G pattern (e.g. a ~60 yd/g figure
followed by a ~0.5 td/g figure), so this parser reads TE positionally -
5th column of the block = yards/game, 6th = TDs/game - rather than trusting
SI's literal (seemingly copy-pasted-and-not-updated) header text for that
one block.

Also dropped: SI's own "Projection" (season fantasy points) and "FPPG"
(fantasy points per game) columns - same reasoning as Athletic's FPS and
FantasyPros' FPTS (see those parsers): this pipeline computes
projected_points itself from raw stats via each league's own
scoring_league_*.yaml, so passing through SI's own point total would make
every league show identical SI-scored numbers regardless of that league's
real scoring settings.
"""

import csv

SOURCE_NAME = "si"
SEASON_GAMES = 17  # NFL regular season length, used to turn SI's per-game rates into season totals

# column_index -> (position, expected label at that column, for a sanity check)
BLOCK_STARTS = {
    "QB": (0, "Quarterback"),
    "RB": (6, "Running Back"),
    "WR": (12, "Wide Receiver"),
    "TE": (18, "Tight End"),
}
# Within each 6-column block: rank, name, projection, fppg, yards/game, tds/game
RANK_OFFSET = 0
NAME_OFFSET = 1
YARDS_PER_GAME_OFFSET = 4
TDS_PER_GAME_OFFSET = 5
BLOCK_WIDTH = 6


def _parse_number(value: str) -> float:
    return float(value.replace(",", "")) if value.strip() else 0.0


def parse_si(filepath: str) -> list[dict]:
    """Parse SI's 'Fantasy Football Projections - PPR Projections.csv'
    export into a list of player dicts matching the pipeline's common
    schema: {player_name, team, position, projected_stats, source}.

    Note: SI's export has no Team column, so `team` is left as None here -
    the merge step will need to join on player_name against a source that
    does have team, or look it up separately, if team is needed downstream.
    """
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    header_row = rows[1]  # row 0 is the section-title row, not real headers
    data_rows = rows[2:]

    for position, (start_col, expected_label) in BLOCK_STARTS.items():
        actual_rank_label = header_row[start_col + RANK_OFFSET].strip()
        actual_name_label = header_row[start_col + NAME_OFFSET].strip()
        if actual_rank_label != "Rank" or actual_name_label != expected_label:
            raise RuntimeError(
                f"SI header at column {start_col} is {actual_rank_label!r}/"
                f"{actual_name_label!r}, expected 'Rank'/{expected_label!r}. "
                f"SI may have changed their export layout - update "
                f"BLOCK_STARTS in scripts/parsers/si.py before trusting this file."
            )

    players = []
    for position, (start_col, _label) in BLOCK_STARTS.items():
        name_col = start_col + NAME_OFFSET
        yards_col = start_col + YARDS_PER_GAME_OFFSET
        tds_col = start_col + TDS_PER_GAME_OFFSET

        for row in data_rows:
            if name_col >= len(row) or not row[name_col].strip():
                continue  # this block has run out of players for this row

            yards_per_game = _parse_number(row[yards_col])
            tds_per_game = _parse_number(row[tds_col])

            players.append({
                "player_name": row[name_col].strip(),
                "team": None,
                "position": position,
                "projected_stats": {
                    "total_yd": round(yards_per_game * SEASON_GAMES, 1),
                    "total_td": round(tds_per_game * SEASON_GAMES, 1),
                },
                "source": SOURCE_NAME,
            })

    return players


if __name__ == "__main__":
    import sys
    from collections import Counter

    path = sys.argv[1] if len(sys.argv) > 1 else (
        "data/si/Fantasy Football Projections (7-23) - PPR Projections.csv"
    )
    parsed = parse_si(path)

    print(f"Parsed {len(parsed)} players from {path}")
    print("By position:", Counter(p["position"] for p in parsed))
    print("\nSample:")
    for p in parsed[:3]:
        print(p)
