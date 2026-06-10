"""
Central data access layer.
All file I/O goes through here — cogs never touch JSON directly.
"""
import json
import os
import uuid
from datetime import date

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS_DIR   = os.path.join(BASE_DIR, "data", "runs")
HOF_FILE   = os.path.join(BASE_DIR, "data", "halloffame.json")
STATE_FILE = os.path.join(BASE_DIR, "data", "state.json")

os.makedirs(RUNS_DIR, exist_ok=True)
os.makedirs(os.path.dirname(HOF_FILE), exist_ok=True)

# ── helpers ───────────────────────────────────────────────────────────────────

def _read(path: str):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def _write(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def _run_dir(run_id: str) -> str:
    return os.path.join(RUNS_DIR, run_id)

def _meta_path(run_id: str)   -> str: return os.path.join(_run_dir(run_id), "meta.json")
def _routes_path(run_id: str) -> str: return os.path.join(_run_dir(run_id), "routes.json")
def _stats_path(run_id: str)  -> str: return os.path.join(_run_dir(run_id), "stats.json")

# ── state (active run) ────────────────────────────────────────────────────────

def get_active_run_id() -> str | None:
    state = _read(STATE_FILE)
    return state.get("active_run_id")

def set_active_run_id(run_id: str) -> None:
    _write(STATE_FILE, {"active_run_id": run_id})

# ── runs ──────────────────────────────────────────────────────────────────────

def list_runs() -> list[dict]:
    runs = []
    if not os.path.isdir(RUNS_DIR):
        return runs
    for entry in sorted(os.listdir(RUNS_DIR)):
        meta_path = os.path.join(RUNS_DIR, entry, "meta.json")
        if os.path.exists(meta_path):
            runs.append(_read(meta_path))
    return runs

def get_run_meta(run_id: str) -> dict | None:
    path = _meta_path(run_id)
    return _read(path) if os.path.exists(path) else None

def create_run(name: str, game: str, players: list[str]) -> dict:
    run_id = str(uuid.uuid4())[:8]
    os.makedirs(_run_dir(run_id), exist_ok=True)
    meta = {
        "id": run_id,
        "name": name,
        "game": game,
        "players": players,
        "status": "active",
        "created_at": str(date.today()),
        "completed_at": None,
    }
    _write(_meta_path(run_id), meta)
    _write(_routes_path(run_id), {})
    _write(_stats_path(run_id), _default_stats(players))
    set_active_run_id(run_id)
    return meta

def complete_run(run_id: str) -> dict | None:
    meta = get_run_meta(run_id)
    if not meta:
        return None
    meta["status"] = "completed"
    meta["completed_at"] = str(date.today())
    _write(_meta_path(run_id), meta)
    return meta

# ── routes ────────────────────────────────────────────────────────────────────

def get_routes(run_id: str) -> dict:
    return _read(_routes_path(run_id))

def save_routes(run_id: str, routes: dict) -> None:
    _write(_routes_path(run_id), routes)

# ── stats ─────────────────────────────────────────────────────────────────────

def _default_stats(players: list[str]) -> dict:
    base = {p: 0 for p in players}
    return {
        "deaths":                    dict(base),
        "alldeaths":                 dict(base),
        "missed_encounters":         dict(base),
        "overall_missed_encounters": dict(base),
        "wipes":                     dict(base),
        "resets":                    0,
        "dead_pokemon":              [],   # list of lowercase pokemon names
        "soul_links":                {},   # {player: linked_player} for soul link pairs
    }

def get_stats(run_id: str) -> dict:
    stats = _read(_stats_path(run_id))
    # Ensure new fields exist on older stat files
    stats.setdefault("dead_pokemon", [])
    stats.setdefault("soul_links", {})
    return stats

def save_stats(run_id: str, stats: dict) -> None:
    _write(_stats_path(run_id), stats)

def ensure_player_in_stats(run_id: str, player: str) -> None:
    stats = get_stats(run_id)
    changed = False
    for key in ("deaths", "alldeaths", "missed_encounters", "overall_missed_encounters", "wipes"):
        if player not in stats.get(key, {}):
            stats.setdefault(key, {})[player] = 0
            changed = True
    if changed:
        save_stats(run_id, stats)

def mark_pokemon_dead(run_id: str, pokemon_name: str) -> None:
    """Add a pokemon (lowercase) to the dead list."""
    stats = get_stats(run_id)
    name  = pokemon_name.lower()
    if name not in stats["dead_pokemon"]:
        stats["dead_pokemon"].append(name)
        save_stats(run_id, stats)

def unmark_pokemon_dead(run_id: str, pokemon_name: str) -> None:
    """Remove a pokemon from the dead list."""
    stats = get_stats(run_id)
    name  = pokemon_name.lower()
    if name in stats["dead_pokemon"]:
        stats["dead_pokemon"].remove(name)
        save_stats(run_id, stats)

def get_dead_pokemon(run_id: str) -> set[str]:
    """Return set of lowercase dead pokemon names."""
    stats = get_stats(run_id)
    return set(stats.get("dead_pokemon", []))

def find_soul_link_partner(run_id: str, player: str, routes: dict) -> tuple[str, list[str]] | None:
    """
    Find the linked player and their pokemon on the same route as the given player.
    Returns (linked_player, evo_line) or None.
    Soul link pairs are determined by player order in the run — player 0 links to player 1, player 2 to player 3.
    """
    meta = get_run_meta(run_id)
    if not meta:
        return None
    players = meta["players"]
    if player not in players:
        return None

    idx = players.index(player)
    # Pair by index: 0↔1, 2↔3, etc.
    if idx % 2 == 0:
        partner_idx = idx + 1
    else:
        partner_idx = idx - 1

    if partner_idx >= len(players):
        return None

    partner = players[partner_idx]

    # Find which route the player's pokemon is on
    for route_name, route_players in routes.items():
        if player in route_players and partner in route_players:
            return (partner, route_players[partner])

    return None

# ── hall of fame ──────────────────────────────────────────────────────────────

def get_hof() -> list[dict]:
    data = _read(HOF_FILE)
    return data if isinstance(data, list) else []

def add_to_hof(entry: dict) -> None:
    hof = get_hof()
    hof.append(entry)
    _write(HOF_FILE, hof)