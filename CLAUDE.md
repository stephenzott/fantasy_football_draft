# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A fantasy football draft board aggregator that combines player rankings from multiple sources (ESPN, The Athletic, Yahoo) into a unified board, hosted as a static site via GitHub Pages. Player rankings are sourced from manually downloaded CSV/XLSX files placed in this repository.

The board also surfaces player flags — concerns like domestic violence arrests or other off-field issues — alongside rankings.

## Architecture

### Data pipeline (Python)
- Input: CSV/XLSX files downloaded from ranking sources and dropped into a designated data directory
- Processing: Python scripts normalize, merge, and score rankings across sources into a single aggregate ranking
- Output: JSON files consumed by the static frontend

### Frontend (GitHub Pages)
- Static HTML/CSS/JS — no build step, no framework
- Reads the generated JSON to render the draft board
- Hosted directly from this repo via GitHub Pages

### Data sources
Rankings are downloaded manually each season from:
- ESPN
- The Athletic
- Yahoo

Additional sources may be added closer to draft season. Each source file should be parseable by the Python pipeline without manual editing.

### Player flags
A flags dataset (CSV or similar) tracks off-field concerns per player (e.g., domestic violence arrests). Flags are joined onto the aggregate board at render time.

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
This reads from `data/` and writes JSON output to `docs/` (the GitHub Pages root).

### Serving the site locally
```bash
cd docs && python -m http.server 8000
```

## Conventions

- `data/` — raw downloaded ranking files (CSV/XLSX), one subdirectory per source
- `docs/` — GitHub Pages root; contains HTML/JS/CSS and generated JSON
- `scripts/` — Python data pipeline scripts
- `flags/` — player flag data

When adding a new ranking source, add a dedicated parser in `scripts/parsers/` that normalizes it to a common schema before merging.
