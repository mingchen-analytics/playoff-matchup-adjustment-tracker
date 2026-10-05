"""Bounded NBA box-score acquisition; imported only by the ingestion CLI."""

import re
import time

from requests import RequestException


def fetch_player_boxscore(game_id, timeout=20, retries=2):
    if not isinstance(game_id, str) or not re.fullmatch(r"004\d{7}", game_id):
        raise ValueError("Expected a quoted 10-digit playoff Game ID.")
    if timeout <= 0 or retries < 1:
        raise ValueError("Timeout and retries must be positive.")
    try:
        from nba_api.stats.endpoints.boxscoretraditionalv3 import BoxScoreTraditionalV3
    except ImportError as exc:
        raise RuntimeError(
            "Install requirements-data.txt for live box scores."
        ) from exc
    last = None
    for attempt in range(retries):
        try:
            return BoxScoreTraditionalV3(game_id=game_id, timeout=timeout).get_dict()
        except (RequestException, ValueError, KeyError, TypeError) as exc:
            last = exc
            if attempt + 1 < retries:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(
        f"Box score {game_id} failed after {retries} attempts: {last}"
    ) from last
