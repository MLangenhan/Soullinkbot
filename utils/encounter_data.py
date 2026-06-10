"""
Multi-game encounter location lookup.
Maps a user-supplied game name to the right location list via fuzzy matching,
then fuzzy-matches logged route keys against that list.
"""
import json
import os
from rapidfuzz import fuzz, process

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE  = os.path.join(BASE_DIR, "data", "encounter_locations.json")

# ── Load data ─────────────────────────────────────────────────────────────────

with open(DATA_FILE, "r", encoding="utf-8") as f:
    _RAW: dict = json.load(f)

# Flat list of (region_key, alias) for game name matching
_GAME_ALIASES: list[tuple[str, str]] = [
    (region_key, alias)
    for region_key, region_data in _RAW.items()
    for alias in region_data["names"]
]

# ── Game detection ────────────────────────────────────────────────────────────

GAME_THRESHOLD = 70

def detect_region(game_name: str) -> str | None:
    """
    Given a user-supplied game name (e.g. "Platin Randomizer", "Pokemon X"),
    return the region key (e.g. "sinnoh", "kalos") or None if no match.
    """
    if not game_name:
        return None

    aliases = [alias for _, alias in _GAME_ALIASES]
    result  = process.extractOne(
        game_name,
        aliases,
        scorer=fuzz.WRatio,
        score_cutoff=GAME_THRESHOLD,
    )
    if result is None:
        return None

    matched_alias = result[0]
    for region_key, alias in _GAME_ALIASES:
        if alias == matched_alias:
            return region_key
    return None


def get_locations(region_key: str) -> list[str]:
    """Return the canonical location list for a region key."""
    return _RAW.get(region_key, {}).get("locations", [])


def get_region_display_name(region_key: str) -> str:
    """Return a human-readable region name."""
    return {
        "kanto":  "Kanto",
        "johto":  "Johto",
        "hoenn":  "Hoenn",
        "sinnoh": "Sinnoh",
        "einall": "Einall",
        "kalos":  "Kalos",
    }.get(region_key, region_key.title())


# ── Route fuzzy matching ──────────────────────────────────────────────────────

ROUTE_THRESHOLD = 82

def best_route_match(logged_name: str, candidates: list[str]) -> str | None:
    """
    Match a logged route key against a canonical location list.
    Same logic as encounters.py but extracted here for reuse.
    """
    result = process.extractOne(
        logged_name,
        candidates,
        scorer=fuzz.WRatio,
        score_cutoff=ROUTE_THRESHOLD,
    )
    if result is None:
        return None
    match_name, score, _ = result
    ratio = len(logged_name) / len(match_name)
    if ratio < 0.65:
        return None
    if match_name.lower().startswith(logged_name.lower()) and ratio < 0.90:
        return None
    return match_name


def resolve_logged_routes(logged_keys: list[str], region_key: str) -> dict[str, str]:
    """
    For each logged route key, find the best canonical match in the given region.
    Returns {logged_key: canonical_name}. Unmatched keys excluded.
    """
    candidates = get_locations(region_key)
    resolved   = {}
    for key in logged_keys:
        match = best_route_match(key, candidates)
        if match:
            resolved[key] = match
    return resolved