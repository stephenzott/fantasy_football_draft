# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A custom fantasy football draft board that combines season projections from multiple ranking sources, converts them to the league's specific scoring system, aggregates into a unified ranking with VBD scores, and supports live updates on draft day.

The board also surfaces player flags — concerns like domestic violence arrests or other off-field issues — alongside rankings.

---

## Tech Stack

- **Backend:** Python
- **Frontend:** Static HTML/CSS/JS (hosted via GitHub Pages)
- **Draft-day state:** `localStorage` (tracks drafted players client-side, no backend needed)
- **Version Control / Hosting:** GitHub
- **Automation:** GitHub Actions (scheduled data pulls)

---

## Data Sources

Rankings/projections are sourced from:
- ESPN
- The Athletic
- Yahoo
- FantasyPros
- Sleeper (free tier)

Pull **season projections** (not pre-built rankings) where possible so they can be normalized to the league's scoring system. Files may be manually downloaded CSVs/XLSX or pulled via API; each source should be parseable by the pipeline without manual editing.

---

## Architecture

### 1. Data Pipeline (Python)
- Input: CSV/XLSX files downloaded from ranking sources, dropped into `data/`
- Normalize player data into a common schema:
  ```
  {
    player_name, team, position,
    projected_stats: { pass_yds, rush_yds, rec, tds, ... },
    source
  }
  ```
- Convert projected stats → fantasy points using the league's scoring settings (see `scoring.yaml`)
- Output: JSON files written to `docs/` (the GitHub Pages root)

### 2. Aggregation Logic (Python)
- Average (or weighted average) the converted point projections across sources
- Rank players by aggregated projected points
- Calculate **Value-Based Drafting (VBD)** score:
  - Find the baseline player at each position (e.g., 12th RB, 12th WR)
  - VBD = player's projected points − baseline projected points
  - Use VBD to identify undervalued players relative to ADP

### 3. Frontend (Static HTML/CSS/JS)
- Reads generated JSON at page load
- Sortable table with columns:
  - Combined rank
  - Position rank
  - Aggregated projected points
  - VBD score
  - Individual source projections (expandable)
  - Player flags (off-field concerns)
  - Drafted status
- Toggle to show/hide drafted players
- "Mark as Drafted" button per player — state persisted in `localStorage`

### Player Flags
A flags dataset (CSV or similar) in `flags/` tracks off-field concerns per player (e.g., domestic violence arrests). Flags are joined onto the aggregate board at render time.

---

## Scoring System Configuration

Define league scoring settings in `scoring.yaml`. Example:

```yaml
pass_td: 4
pass_yd: 0.04
rush_yd: 0.1
rush_td: 6
reception: 0.5   # PPR
rec_yd: 0.1
rec_td: 6
```

Apply this config to raw projected stats from each source to produce a standardized points value.

---

## Draft Day Workflow

1. Open the board on draft day
2. As players are drafted, click "Mark as Drafted" — state is saved to `localStorage`
3. Board filters/re-ranks remaining players immediately in the browser
4. State survives page refreshes on the same device for the duration of the draft

---

## Development

### Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Running the pipeline
```bash
python scripts/build.py
```
Reads from `data/` and writes JSON output to `docs/` (the GitHub Pages root).

### Serving the site locally
```bash
cd docs && python -m http.server 8000
```

---

## Conventions

- `data/` — raw downloaded ranking files (CSV/XLSX), one subdirectory per source
- `docs/` — GitHub Pages root; contains HTML/JS/CSS and generated JSON
- `scripts/` — Python data pipeline scripts
- `scripts/parsers/` — one parser per source, each normalizing to the common schema
- `flags/` — player flag data

When adding a new ranking source, add a dedicated parser in `scripts/parsers/` that normalizes it to the common schema before merging.

---

## Build Order

1. Build one data source pipeline — get one source working end-to-end (normalize → convert → write JSON)
2. Add remaining sources — repeat the pattern
3. Build aggregation + VBD logic
4. Build static frontend — display board, sorting, filtering, flags
5. Add draft day UI — mark drafted players via `localStorage`
6. Set up GitHub Actions — automate scheduled data pulls
7. Test full flow — mock a draft day scenario

---

## Future Enhancements

- ADP comparison overlay (pull ADP from FantasyPros)
- Positional scarcity alerts
- Trade value calculator
- Mobile-friendly layout for draft day on a tablet
