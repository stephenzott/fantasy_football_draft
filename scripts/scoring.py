"""
Converts a player's raw projected stats into fantasy points under one
league's scoring settings.

Every parser in scripts/parsers/ emits a player's `projected_stats` as a
dict of common stat names (pass_yd, rush_td, rec, ...). Each league's
scoring_league_*.yaml assigns a point value to each scorable stat. This
module multiplies the two together.

Two things here are deliberate and easy to get wrong:

1. NAME MISMATCH (the important one). Parsers call the reception count
   `rec`; the scoring YAMLs call it `reception`. If we just looped over the
   scoring keys and did `projected_stats[key]`, `reception` would never
   find a match, PPR would silently score zero, and a full-PPR league would
   under-count a 100-catch WR by ~100 points - enough to completely
   reorder the board while still looking plausible. SCORING_TO_STAT below
   maps `reception -> rec` explicitly so this can't happen.

2. FAIL LOUD ON UNKNOWN KEYS. If a scoring file ever grows a key we don't
   recognize (a typo, or a real new category), we raise rather than
   silently ignore it - a dropped category is exactly the kind of bug that
   produces believable-but-wrong numbers. Keys we intentionally don't score
   in v1 (the 2-point conversions) are listed explicitly so they're
   "known and skipped," not "unknown and skipped."
"""

import yaml

# The only three scoring-file sections that drive the board. The board ranks
# QB/RB/WR/TE only, so `kicking` and `defense_special_teams` (K/DST) are
# ignored here - they're kept in the YAML for parity with each league's real
# ESPN settings, per the project's scoring-config notes.
SCORED_SECTIONS = ("passing", "rushing", "receiving")

# scoring-YAML key -> the stat key the parsers actually emit. Every pair is
# identity EXCEPT reception -> rec (see point 1 in the module docstring).
SCORING_TO_STAT = {
    "pass_yd": "pass_yd",
    "pass_td": "pass_td",
    "pass_int": "pass_int",
    "rush_yd": "rush_yd",
    "rush_td": "rush_td",
    "rec_yd": "rec_yd",
    "rec_td": "rec_td",
    "reception": "rec",   # <-- the alias that prevents silently zeroing PPR
}

# Scoring keys we knowingly do NOT score in v1. Listed so the "unknown key"
# guard below treats them as intentional rather than raising on them.
#
# 2-point conversions: only the Sleeper parser projects these, and at tiny
# magnitude. Scoring them would make the same player total differently from
# one league to the next for a reason unrelated to that league's real
# scoring differences (since the other five sources contribute 0), so we
# skip them uniformly across all sources for now.
INTENTIONALLY_UNSCORED = {"pass_2pt", "rush_2pt", "rec_2pt"}


def load_scoring(path: str) -> dict[str, float]:
    """Read a scoring_league_*.yaml file and flatten its passing/rushing/
    receiving sections into one flat {scoring_key: point_value} dict.

    Only the three scored sections are pulled in; everything else in the
    file (kicking, defense_special_teams) is left out because the board
    doesn't rank those positions.
    """
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    flat: dict[str, float] = {}
    for section in SCORED_SECTIONS:
        # A league could in principle omit a whole section; treat a missing
        # section as "no scoring keys from it" rather than erroring.
        for key, value in (raw.get(section) or {}).items():
            flat[key] = float(value)
    return flat


def score_stats(projected_stats: dict[str, float], scoring: dict[str, float]) -> float:
    """Convert one source's projected_stats for one player into fantasy
    points under the given (already-flattened) scoring dict.

    A stat the player has no value for (e.g. a WR's pass_yd) simply
    contributes 0 - `.get(stat_key, 0.0)` handles that. What we do NOT do
    is quietly skip a scoring key we don't recognize; that raises.
    """
    total = 0.0
    for scoring_key, point_value in scoring.items():
        if scoring_key in SCORING_TO_STAT:
            stat_key = SCORING_TO_STAT[scoring_key]
            total += point_value * projected_stats.get(stat_key, 0.0)
        elif scoring_key in INTENTIONALLY_UNSCORED:
            continue  # known category we've chosen not to score in v1
        else:
            # Unknown scoring key: fail loudly instead of producing
            # plausible-but-wrong totals. If this fires, either add the key
            # to SCORING_TO_STAT (with the stat the parsers emit for it) or
            # to INTENTIONALLY_UNSCORED if it's meant to be ignored.
            raise RuntimeError(
                f"scoring.py: scoring key {scoring_key!r} is neither mapped "
                f"to a projected-stat name nor listed as intentionally "
                f"unscored. Update SCORING_TO_STAT or INTENTIONALLY_UNSCORED "
                f"in scripts/scoring.py before trusting these point totals."
            )
    return total
