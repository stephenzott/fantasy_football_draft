"""
Merges the per-source parser outputs into one row per real-world player.

Each parser returns its own list of {player_name, team, position,
projected_stats, source}. The same player shows up in several of those
lists under slightly different spellings ("Michael Penix Jr." vs "Michael
Penix", "D.J. Moore" vs "DJ Moore"). This module:

  1. Normalizes each name to a match key (lowercase, no punctuation, no
     Jr/Sr/III suffix) so those spellings collapse to one player.
  2. Groups all sources' rows by that key.
  3. Picks a single display name, team (majority vote), and position
     (majority vote) per player.
  4. Mints a Firebase-safe player_id from the match key + position.
  5. Joins conduct flags (from the Google Sheet) by normalized name.
  6. Produces a MATCH REPORT so normalization failures are loud: a player
     who matched only 1 of the expected sources is almost always a spelling
     we failed to normalize, not a genuinely single-source player.

SI is intentionally NOT passed into this merge: its projections can't be
converted to points under any league's scoring (only combined total_yd /
total_td, no pass/rush/rec split, no receptions), so it contributes neither
to points nor to the player universe. See build.py.
"""

import re
import unicodedata
from collections import Counter

# Name-suffix tokens to strip before matching. Sources disagree on whether
# they keep these (CBS keeps "Jr."; others often drop it), so removing them
# from the match key lets the same player line up across sources.
NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

# Hand-maintained aliases for players whose names differ in a way plain
# normalization can't fix (nicknames, shortened first names). Keys and
# values are both already-normalized match keys. This table starts small and
# is meant to grow: run build.py, read the match report for 1-source
# players, and add a mapping here whenever the "1-source" player is really
# the same person as an existing multi-source player under another name.
#   e.g. "hollywood brown" -> "marquise brown"
NAME_ALIASES: dict[str, str] = {}


def normalize_name(name: str) -> str:
    """Reduce a raw player name to a match key that's stable across sources.

    Steps: strip accents -> lowercase -> drop anything that isn't a letter,
    digit, or space -> drop trailing Jr/Sr/II.. suffix tokens -> collapse
    whitespace. Finally apply the NAME_ALIASES table for nickname cases
    plain normalization can't reach.
    """
    # Strip accents (e.g. "José" -> "Jose") so accented and plain spellings
    # of the same name match. NFKD splits an accented char into base char +
    # combining mark; encoding to ASCII and back drops the marks.
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = name.lower()
    # Remove punctuation: "d.j." -> "dj", "ja'marr" -> "jamarr". Keep spaces.
    name = re.sub(r"[^a-z0-9 ]", "", name)
    # Drop suffix tokens (Jr/Sr/III/...) wherever they land as whole words.
    tokens = [t for t in name.split() if t not in NAME_SUFFIXES]
    key = " ".join(tokens).strip()
    # Nickname/short-name fixes that normalization alone can't handle.
    return NAME_ALIASES.get(key, key)


def make_player_id(match_key: str, position: str) -> str:
    """Build a stable, Firebase-safe id from the match key and position,
    e.g. ("michael penix", "QB") -> "michael-penix-qb".

    Firebase Realtime Database rejects the characters . $ # [ ] / in keys;
    the match key already contains only lowercase letters, digits, and
    spaces, so turning spaces into hyphens yields a safe id. Position is
    appended so two different players who happen to normalize to the same
    name still get distinct ids.
    """
    slug = match_key.replace(" ", "-")
    return f"{slug}-{position.lower()}"


def _majority(values: list) -> object:
    """Return the most common non-empty value in a list (ties broken by
    whichever Counter sees first). Used to reconcile team/position when
    sources disagree.
    """
    cleaned = [v for v in values if v]
    if not cleaned:
        return None
    return Counter(cleaned).most_common(1)[0][0]


def _display_name(raw_names: list[str]) -> str:
    """Pick the display name shown on the board from the raw spellings seen
    across sources: the most common one, with ties broken toward the
    longest (so "Michael Penix Jr." wins over "Michael Penix" - the fuller
    form is friendlier to read on the board).
    """
    counts = Counter(raw_names)
    top = counts.most_common()
    best_count = top[0][1]
    tied = [name for name, c in top if c == best_count]
    return max(tied, key=len)


def merge_sources(source_lists: list[list[dict]], flags: dict[str, list[str]]) -> list[dict]:
    """Merge several parsers' player lists into one row per player.

    `source_lists` is a list of per-source lists (each already in the common
    parser schema). `flags` maps lowercase "first last" -> list of flag
    strings (from scripts/parsers/flags_sheet.py).

    Returns a list of merged player dicts, each shaped like:
        {
          player_id, name, team, position,
          flags: [...],
          per_source_stats: { source: projected_stats, ... },
        }
    Point totals are NOT computed here - that's per-league (build.py),
    since it depends on each league's scoring. This merge is
    league-independent and runs once.
    """
    # Re-key the flags dict through the SAME name normalizer used to match
    # players. fetch_flags() keys on the raw "first last" lowercased, with no
    # accent/punctuation/suffix stripping - so a sheet entry like "Marvin
    # Harrison Jr." (stored as "marvin harrison jr.") would never line up
    # with the merged player's match key "marvin harrison". Normalizing both
    # sides through normalize_name closes that gap. Since flags drive the
    # DV-list toggle, a silent miss would make a flagged player show clean.
    normalized_flags: dict[str, list[str]] = {}
    for raw_key, entries in flags.items():
        normalized_flags.setdefault(normalize_name(raw_key), []).extend(entries)

    # Group every source row under its normalized match key.
    groups: dict[str, list[dict]] = {}
    for source_players in source_lists:
        for player in source_players:
            key = normalize_name(player["player_name"])
            if not key:
                continue  # blank/garbage name; skip rather than make a phantom
            groups.setdefault(key, []).append(player)

    merged: list[dict] = []
    for match_key, rows in groups.items():
        position = _majority([r["position"] for r in rows])
        team = _majority([r["team"] for r in rows])
        name = _display_name([r["player_name"] for r in rows])

        # Keep each source's raw projected_stats keyed by source name, so
        # build.py can score each source separately per league and also show
        # the per-source point breakdown on the board.
        per_source_stats = {r["source"]: r["projected_stats"] for r in rows}

        # Look flags up by the same normalized key both sides now share.
        player_flags = normalized_flags.get(match_key, [])

        merged.append({
            "player_id": make_player_id(match_key, position),
            "name": name,
            "team": team,
            "position": position,
            "flags": player_flags,
            "per_source_stats": per_source_stats,
            # kept only for the match report / debugging; stripped before output
            "_match_key": match_key,
            "_source_count": len(per_source_stats),
        })

    return merged


def print_match_report(merged: list[dict], expected_sources: int) -> None:
    """Print how many sources each player matched, so normalization gaps are
    visible. Players matching just 1 source are flagged first - those are
    the likely spelling mismatches worth adding to NAME_ALIASES.
    """
    by_count = Counter(p["_source_count"] for p in merged)
    print("\n=== MERGE MATCH REPORT ===")
    print(f"Merged players: {len(merged)}  (expected up to {expected_sources} sources each)")
    for count in sorted(by_count):
        print(f"  matched {count} source(s): {by_count[count]} players")

    weak = sorted(
        (p for p in merged if p["_source_count"] == 1),
        key=lambda p: p["name"],
    )
    if weak:
        print(f"\n  {len(weak)} player(s) matched only 1 source "
              f"(likely name-normalization misses - candidates for NAME_ALIASES):")
        for p in weak:
            src = next(iter(p["per_source_stats"]))
            print(f"    - {p['name']} ({p['position']}, {p['team']}) only in {src}")
    print("=== END MATCH REPORT ===\n")
