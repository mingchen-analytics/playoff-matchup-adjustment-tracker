"""Load the bundled API series for research scripts (no network access)."""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "research" / "results"


def api_series_ids(root=ROOT):
    return sorted(path.stem for path in (Path(root) / "data/snapshots").glob("*_api_*.csv"))


def load_matchups(series_id, root=ROOT):
    path = Path(root) / "data/snapshots" / f"{series_id}.csv"
    return pd.read_csv(path, dtype={"game_id": str})


def load_player_minutes(series_id, root=ROOT):
    """(game_number, player_id) -> full-game seconds for players who played."""
    path = Path(root) / "data/player_context" / f"{series_id}.csv"
    players = pd.read_csv(path, dtype={"game_id": str})
    played = players[players.played.astype(bool) & players.minutes_seconds.notna()]
    return {
        (int(g), int(p)): float(s)
        for g, p, s in zip(played.game_number, played.player_id, played.minutes_seconds)
    }
