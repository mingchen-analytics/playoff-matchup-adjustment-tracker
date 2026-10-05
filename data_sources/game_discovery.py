"""NBA game discovery with a reusable, cached LeagueGameFinder boundary."""

from __future__ import annotations
import time
import re
import pandas as pd

from series_manifest import manifest_from_dict


def discover_from_game_log(frame, season, team_a, team_b):
    """Filter defensively even if the endpoint ignores its request filters."""
    required = {
        "SEASON_ID",
        "TEAM_ABBREVIATION",
        "GAME_ID",
        "GAME_DATE",
        "MATCHUP",
        "WL",
    }
    if required - set(frame.columns):
        raise ValueError(
            f"Game log missing columns: {sorted(required - set(frame.columns))}"
        )
    if not re.fullmatch(r"\d{4}-\d{2}", season):
        raise ValueError("season must use YYYY-YY.")
    f = frame.copy()
    for col in required - {"GAME_DATE"}:
        f[col] = f[col].astype("string").str.strip()
    expected_season = "4" + season[:4]
    f = f[(f.SEASON_ID == expected_season) & (f.TEAM_ABBREVIATION == team_a)]
    f = f[
        f.MATCHUP.str.fullmatch(
            rf"{re.escape(team_a)} (?:vs\.|@) {re.escape(team_b)}", na=False
        )
    ]
    f = f[f.GAME_ID.str.fullmatch(rf"004{season[2:4]}\d{{5}}", na=False)]
    if f.empty:
        raise ValueError(
            f"No played {season} playoff games found for {team_a} vs {team_b}."
        )
    f = f[["GAME_ID", "GAME_DATE", "WL"]].drop_duplicates()
    if f.GAME_ID.duplicated().any():
        raise ValueError("Conflicting duplicate game IDs in game log.")
    dates = pd.to_datetime(f.GAME_DATE, format="%Y-%m-%d", errors="coerce")
    if dates.isna().any() or dates.duplicated().any():
        raise ValueError("Invalid or duplicate game dates in game log.")
    f["GAME_DATE"] = dates.dt.strftime("%Y-%m-%d")
    f = f.sort_values(["GAME_DATE", "GAME_ID"])
    if len(f) > 7 or not f.WL.isin(["W", "L"]).all():
        raise ValueError("Expected one to seven played games with W/L results.")
    # Playoff IDs encode conference/round/series and the final digit is game number.
    if f.GAME_ID.str[:-1].nunique() != 1 or [int(v[-1]) for v in f.GAME_ID] != list(
        range(1, len(f) + 1)
    ):
        raise ValueError("Game log has gaps or mixes playoff series.")
    wins = int(f.WL.eq("W").sum())
    losses = int(f.WL.eq("L").sum())
    if (
        max(wins, losses) > 4
        or max(int(f.WL.iloc[:-1].eq("W").sum()), int(f.WL.iloc[:-1].eq("L").sum()))
        >= 4
    ):
        raise ValueError("Games appear after the series was already decided.")
    complete = max(wins, losses) == 4
    rounds = {
        "1": "First Round",
        "2": "Conference Semifinals",
        "3": "Conference Finals",
        "4": "NBA Finals",
    }
    round_number = f.GAME_ID.iloc[0][7]
    playoff_round = rounds.get(round_number, "Playoffs")
    return manifest_from_dict(
        {
            "series_id": f"{season.replace('-', '_')}_{team_a}_{team_b}".lower(),
            "season": season,
            "season_type": "Playoffs",
            "playoff_round": playoff_round,
            "team_a": team_a,
            "team_b": team_b,
            "series_complete": complete,
            "games": [
                {"game_number": i, "game_id": r.GAME_ID, "game_date": r.GAME_DATE}
                for i, r in enumerate(f.itertuples(), 1)
            ],
            "notes": "Discovered from NBA LeagueGameFinder played-game results; complete means one team reached four wins.",
        }
    )


def fetch_game_log(season, team_a, team_b, timeout=20, retries=2):
    if timeout <= 0 or retries < 1:
        raise ValueError("timeout and retries must be positive.")
    try:
        from nba_api.stats.endpoints import leaguegamefinder
        from nba_api.stats.static import teams
    except ImportError as exc:
        raise RuntimeError(
            "Install requirements-data.txt to discover live games."
        ) from exc
    ids = {t["abbreviation"]: t["id"] for t in teams.get_teams()}
    if team_a not in ids or team_b not in ids or team_a == team_b:
        raise ValueError("Use two different NBA team abbreviations.")
    last = None
    for attempt in range(retries):
        try:
            return leaguegamefinder.LeagueGameFinder(
                team_id_nullable=ids[team_a],
                vs_team_id_nullable=ids[team_b],
                season_nullable=season,
                season_type_nullable="Playoffs",
                league_id_nullable="00",
                timeout=timeout,
            ).league_game_finder_results.get_data_frame()
        except Exception as exc:
            last = exc
            if attempt + 1 < retries:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(
        f"Game discovery failed after {retries} attempts: {last}"
    ) from last
