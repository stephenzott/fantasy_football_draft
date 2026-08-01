"""
Parses The Athletic's ranking export into the pipeline's common player schema.

The Athletic's CSV is NOT one table with a position column - it's four
separate tables (QB, RB, WR, TE) sitting side by side in the same rows,
each with its own repeated header (RK, Player, TM, ...) and separated by a
blank column. A generic CSV/DataFrame reader would rename the duplicate
"Player"/"RK" columns to "Player.1", "Player.2", etc, which just shifts the
same problem elsewhere - so we read the file with the plain csv module and
split each row into its four blocks ourselves, using the blank separator
columns as the split points.
"""

import csv

SOURCE_NAME = "athletic"

# Maps The Athletic's column headers to this pipeline's common stat names.
# Any header not listed here (BYE, AUC$, AUC Calc, RK) is intentionally
# dropped - The Athletic's own "FPS" (fantasy points under ITS scoring) is
# also dropped rather than mapped to projected_points, because this
# pipeline computes projected_points itself from raw stats using each
# league's own scoring_league_*.yaml. If FPS leaked through as
# projected_points, every league would end up with identical
# Athletic-scored numbers and the per-league scoring configs would have no
# effect on this source.
STAT_COLUMN_MAP = {
    "PASS ATT": "pass_att",
    "COMP": "pass_cmp",
    "PASS YARDS": "pass_yd",
    "PASS TD": "pass_td",
    "INT": "pass_int",
    "RUSH ATT": "rush_att",
    "RUSH YARDS": "rush_yd",
    "RUSH TD": "rush_td",
    "TGTS": "rec_tgt",
    "REC": "rec",
    "RECV YARDS": "rec_yd",
    "RECV TD": "rec_td",
}


def _split_header_into_blocks(header_row: list[str]) -> list[list[tuple[int, str]]]:
    """Group header cells into blocks, breaking on each blank cell.

    Returns a list of blocks; each block is a list of
    (column_index, header_name) pairs for that block's non-blank columns.
    Blank columns (The Athletic uses them as visual spacers between the
    four position tables) are consumed as separators and don't appear in
    any block.
    """
    blocks: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    for idx, cell in enumerate(header_row):
        if cell.strip() == "":
            if current:
                blocks.append(current)
                current = []
        else:
            current.append((idx, cell.strip()))
    if current:
        blocks.append(current)
    return blocks


def _infer_position(header_names: set[str]) -> str:
    """Work out which position a block belongs to from its own headers,
    rather than assuming a fixed left-to-right order - The Athletic could
    reorder the four tables in a future export without warning.
    """
    if "PASS YARDS" in header_names:
        return "QB"
    if "RUSH ATT" in header_names:
        return "RB"
    if "RUSH YARDS" in header_names:
        return "WR"
    return "TE"


def parse_athletic(filepath: str) -> list[dict]:
    """Parse a raw 'The Athletic - Ranks w Proj.csv' export into a list of
    player dicts matching the pipeline's common schema:
        {player_name, team, position, projected_stats, source}
    """
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    header_row, data_rows = rows[0], rows[1:]
    blocks = _split_header_into_blocks(header_row)

    players: list[dict] = []
    for block in blocks:
        header_names = {name for _, name in block}
        position = _infer_position(header_names)

        # column_index -> field name ("player_name", "team", or a stat key)
        # for just this block, so each block is decoded independently even
        # though blocks have different sets/orders of stat columns.
        field_by_column: dict[int, str] = {}
        for col_idx, name in block:
            if name == "Player":
                field_by_column[col_idx] = "player_name"
            elif name == "TM":
                field_by_column[col_idx] = "team"
            elif name in STAT_COLUMN_MAP:
                field_by_column[col_idx] = STAT_COLUMN_MAP[name]
            # anything else in this block (RK, BYE, FPS, AUC$, AUC Calc) is
            # left out of field_by_column and so silently skipped below.

        for row in data_rows:
            # Rows run to the length of the file's longest block (QB has
            # the most columns), so shorter blocks like TE just have empty
            # cells past their own player count. A blank player-name cell
            # means "no player at this row for this block" - skip it,
            # otherwise we'd manufacture a phantom player with a blank name
            # and all-zero stats that would corrupt VBD baselines later.
            player_col = next(
                col for col, field in field_by_column.items() if field == "player_name"
            )
            if player_col >= len(row) or not row[player_col].strip():
                continue

            player = {
                "player_name": None,
                "team": None,
                "position": position,
                "projected_stats": {},
                "source": SOURCE_NAME,
            }
            for col_idx, field in field_by_column.items():
                value = row[col_idx].strip() if col_idx < len(row) else ""
                if field in ("player_name", "team"):
                    player[field] = value
                else:
                    # Every stat column here is numeric; empty means 0
                    # (e.g. a WR with 0 rush attempts on the season).
                    player["projected_stats"][field] = float(value) if value else 0.0

            players.append(player)

    return players


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "data/athletic/The Athletic - Ranks w Proj.csv"
    parsed = parse_athletic(path)

    from collections import Counter

    print(f"Parsed {len(parsed)} players from {path}")
    print("By position:", Counter(p["position"] for p in parsed))
    print("\nSample:")
    for p in parsed[:3]:
        print(p)
