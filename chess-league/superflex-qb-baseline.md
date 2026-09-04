# Feature: Per-League VBD Baseline for Super Flex League

## Context

Adding a new league with a super flex slot (1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 SUPERFLEX). The super flex slot can be filled by any skill position or QB, but in practice QBs almost always win that slot since they typically outscore a second-tier RB/WR/TE — which spikes QB demand and value in this league specifically.

This is scoped to **QB only**. RB/WR/TE flex math (currently a 50/40/10 split) is unaffected and should not change.

## Problem

`build.py` currently computes VBD using a single fixed replacement-rank baseline per position (e.g., QB baseline = 12th-ranked QB), applied the same way across all 5 leagues. That's wrong for the new super flex league, where teams can start 2 QBs, so the effective replacement level is much deeper (roughly the 20th-24th ranked QB, to be confirmed against real numbers once computed).

## Fix

Make the QB VBD baseline configurable **per league** instead of global.

### 1. Config change — `leagues.yaml`

Add a QB baseline rank field to each league's entry. Existing 4 leagues keep the standard baseline; the new super flex league gets a deeper one.

```yaml
leagues:
  - id: existing_league_1
    # ...existing fields...
    vbd_baseline:
      qb: 12   # standard 1-QB baseline

  # ...same for the other 3 existing leagues...

  - id: new_superflex_league
    # ...existing fields...
    vbd_baseline:
      qb: 22   # placeholder — confirm exact number once real point projections are in
```

RB/WR/TE baselines are unchanged and not touched by this feature — only QB gets a per-league override for now.

### 2. Pipeline change — `scripts/build.py`

Wherever VBD is currently calculated using a hardcoded QB baseline rank, change it to read the baseline from that league's `vbd_baseline.qb` config value instead of a fixed constant. RB/WR/TE baseline logic stays exactly as-is.

Rough shape (adapt to actual current code structure):

```python
qb_baseline_rank = league_config["vbd_baseline"]["qb"]
qb_baseline_points = get_points_at_rank("QB", qb_baseline_rank, player_pool)

for player in players_by_position["QB"]:
    player["vbd"] = player["projected_points"] - qb_baseline_points
```

### 3. Validation once implemented

- Confirm the new league's `scoring.yaml` doesn't have unusual QB rushing/passing TD weighting or INT penalties that would change how much QBs should be discounted (a heavily anti-pocket-passer scoring system could reduce the QB baseline depth needed — check before finalizing rank 22 vs. something else).
- Once `players.json` is regenerated for the super flex league, sanity-check that QBs in the 15-25 range show a meaningful VBD bump compared to the standard-league output, and that RB/WR/TE VBD numbers are unchanged from before this change.

## Out of scope (for now)

- Per-league baselines for RB/WR/TE
- Any change to the 50/40/10 flex-eligible split
- Any change to leagues other than the new super flex one
