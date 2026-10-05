"""Bounded NBA PlayByPlayV3 acquisition, separate from the offline app."""

import re
import time

from requests import RequestException


def fetch_play_by_play(game_id, timeout=20, retries=2):
    if not isinstance(game_id, str) or not re.fullmatch(r"004\d{7}", game_id):
        raise ValueError("Expected a quoted 10-digit playoff Game ID.")
    if timeout <= 0 or retries < 1:
        raise ValueError("Timeout and retries must be positive.")
    try:
        from nba_api.stats.endpoints.playbyplayv3 import PlayByPlayV3
    except ImportError as exc:
        raise RuntimeError(
            "Install requirements-data.txt for live play-by-play."
        ) from exc
    last = None
    for attempt in range(retries):
        try:
            return PlayByPlayV3(game_id=game_id, timeout=timeout).get_dict()
        except (RequestException, ValueError, KeyError, TypeError) as exc:
            last = exc
            if attempt + 1 < retries:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(
        f"Play-by-play {game_id} failed after {retries} attempts: {last}"
    ) from last
