"""
Per-league aggregation: turn merged players (with each source's raw stats)
into the ranked, VBD-scored rows the board consumes.

For one league this does three things:
  1. Score each source's stats under the league's scoring, then average
     those per-source point totals into one projected_points per player.
  2. Assign a positional rank ("RB1", "RB2", ...) by projected_points within
     each position.
  3. Compute Value-Based Drafting (VBD): projected_points minus the points
     of the "baseline" player at that position - the last player expected
     to be a startable starter across the whole league. Overall `rank` is
     then assigned by VBD (not raw points) - VBD is the actual "who should
     go first" number; ranking on raw points alone would over-favor QBs
     (a deep position where even mediocre starters score a lot) over
     scarcer RB/WR/TE options.

VBD baseline math is the mathematically interesting part, so it's spelled
out in compute_baselines().
"""

from statistics import mean

from scoring import score_stats

# How a single FLEX slot is expected to be filled across RB/WR/TE. FLEX can
# be any of the three, so a FLEX slot doesn't add a full starter to any one
# position - it adds a fractional share. These shares reflect that RBs fill
# FLEX most often, then WRs, then TEs. They sum to 1.0. (Surfaced as a
# tunable because it's a modeling choice, not a hard rule.)
FLEX_SPLIT = {"RB": 0.50, "WR": 0.40, "TE": 0.10}

# Positions the board ranks. QB is never FLEX-eligible in these leagues (no
# superflex/2QB), so QB gets no FLEX share.
POSITIONS = ("QB", "RB", "WR", "TE")


def compute_baselines(roster: dict, vbd_baseline_overrides: dict | None = None) -> dict[str, int]:
    """Given a league's roster block from leagues.yaml, return the baseline
    RANK at each position - i.e. "the Nth-best QB/RB/WR/TE is replacement
    level for this league."

    The idea behind VBD: a player is only worth what they give you ABOVE
    what you could get for free at that position. "Replacement level" is the
    best player you'd expect to still be available / on a bench - roughly
    the last one who clears a starting slot across the whole league.

    For a position with `s` dedicated starting slots per team and `t` teams,
    that's `t * s` players locked into starting lineups. FLEX adds a
    fractional share on top (see FLEX_SPLIT), because each team's FLEX slot
    pulls one more RB/WR/TE out of the pool on average. So:

        baseline_rank(pos) = round( t * starters[pos]
                                    + t * starters[FLEX] * FLEX_SPLIT[pos] )

    Example (12-team, 2 RB + 1 FLEX): 12*2 + 12*1*0.50 = 24 + 6 = 30, so
    the 30th-ranked RB is replacement level and RB VBD is measured against
    that player's projected points.

    `vbd_baseline_overrides` is an optional per-league escape hatch (the
    `vbd_baseline` block in leagues.yaml, e.g. `{"qb": 22}`) for positions
    where the formula above doesn't apply - namely a superflex league's QB
    slot, which can be filled by a 2nd QB and so has no fixed number of
    "dedicated" starters the way QB:1 does elsewhere. When a position has an
    override, its configured rank is used directly and the formula is
    skipped for that position only; every other position (and every league
    that omits vbd_baseline entirely) is completely unaffected. See
    superflex-qb-baseline.md for the full design writeup.
    """
    teams = roster["teams"]
    starters = roster["starters"]
    flex_slots = starters.get("FLEX", 0)
    overrides = vbd_baseline_overrides or {}

    baselines: dict[str, int] = {}
    for pos in POSITIONS:
        override_rank = overrides.get(pos.lower())
        if override_rank is not None:
            baselines[pos] = override_rank
            continue
        dedicated = teams * starters.get(pos, 0)
        flex_share = teams * flex_slots * FLEX_SPLIT.get(pos, 0.0)
        # round() gives the nearest integer rank; max(..,1) guards the
        # degenerate case of a position with no starting slots at all.
        baselines[pos] = max(round(dedicated + flex_share), 1)
    return baselines


def aggregate_league(
    merged: list[dict],
    scoring: dict[str, float],
    roster: dict,
    vbd_baseline_overrides: dict | None = None,
) -> list[dict]:
    """Produce the final ranked player rows for one league.

    `merged` are the league-independent merged players (from merge.py),
    each carrying per_source_stats. `scoring` is that league's flattened
    scoring dict (from scoring.load_scoring). `roster` is the league's
    roster block from leagues.yaml. `vbd_baseline_overrides` is that
    league's optional `vbd_baseline` block from leagues.yaml (see
    compute_baselines' docstring) - omitted/None for every league that
    doesn't need one.

    Returns a list of player dicts in the board's players.json schema:
      {name, team, position, rank, pos_rank, projected_points, vbd,
       sources, flags, injuries, player_id}
    """
    baselines = compute_baselines(roster, vbd_baseline_overrides)

    # --- Step 1: score each source, average into projected_points ---
    scored: list[dict] = []
    for p in merged:
        # Score every source that has this player, keeping the per-source
        # point totals for the board's expandable breakdown.
        sources = {
            src: round(score_stats(stats, scoring), 1)
            for src, stats in p["per_source_stats"].items()
        }
        projected_points = round(mean(sources.values()), 1) if sources else 0.0

        scored.append({
            "player_id": p["player_id"],
            "name": p["name"],
            "team": p["team"],
            "position": p["position"],
            "projected_points": projected_points,
            "sources": sources,
            "flags": p["flags"],
            "injuries": [],  # no injuries data source exists yet; always empty
        })

    # --- Step 2: a points-sorted ordering drives pos_rank AND the VBD baseline ---
    # Sort by projected points high-to-low, breaking ties by name. The name
    # tiebreaker matters: projected_points is rounded to 1 decimal, so exact
    # ties are common, and Python's sort is stable - without a tiebreaker,
    # tied players would keep their arbitrary merge/parse order, so labels
    # like "RB24" vs "RB25" (and which player defines the VBD baseline) could
    # silently flip between builds with no change in the data. Sorting by
    # name makes every build deterministic.
    scored.sort(key=lambda p: (-p["projected_points"], p["name"]))

    # Positional rank ("RB1", "RB2", ...) in that order. We also keep each
    # position's players in this order (by_position) so the VBD baseline is
    # read from the identical ordering - i.e. the player labeled "RB30" is
    # exactly the player whose points define the RB baseline, with no risk of
    # a separately-sorted list disagreeing. Note: within a single position,
    # points-order and VBD-order are identical (VBD is just points minus a
    # constant baseline for that position), so this ordering is unaffected by
    # Step 4 switching the OVERALL rank to be VBD-based below.
    by_position: dict[str, list[dict]] = {}
    for p in scored:
        bucket = by_position.setdefault(p["position"], [])
        bucket.append(p)
        p["pos_rank"] = f"{p['position']}{len(bucket)}"

    # --- Step 3: VBD vs the baseline (replacement-level) player ---
    for pos, players in by_position.items():
        baseline_rank = baselines.get(pos)
        if baseline_rank is None:
            # A position with no configured baseline (shouldn't happen for
            # QB/RB/WR/TE); leave VBD at 0 rather than crash.
            for p in players:
                p["vbd"] = 0.0
            continue
        # Baseline player = the one at baseline_rank in this ordering. If the
        # pool is thinner than the baseline rank (e.g. a shallow TE pool in a
        # deep league), fall back to the last available player.
        idx = min(baseline_rank, len(players)) - 1  # ranks are 1-based
        baseline_pts = players[idx]["projected_points"]
        for p in players:
            p["vbd"] = round(p["projected_points"] - baseline_pts, 1)

    # --- Step 4: overall rank reflects VBD, not raw points ---
    # Raw points alone over-favors QBs (a deep position where even mediocre
    # starters score a lot) over scarcer RB/WR/TE options with far more value
    # above replacement. VBD is the "who should actually go first" number, so
    # that's what the board's default rank/sort should reflect. Same name
    # tiebreak as Step 2, for the same determinism reason.
    scored.sort(key=lambda p: (-p["vbd"], p["name"]))
    for i, p in enumerate(scored, start=1):
        p["rank"] = i

    return scored
