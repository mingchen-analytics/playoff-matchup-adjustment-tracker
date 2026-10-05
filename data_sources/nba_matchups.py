"""NBA.com matchup-data adapter.

This module keeps network access separate from the dashboard and analytics layers.
The normalized output intentionally mirrors the current manual matchup CSV schema
so existing validation and analytics can be reused unchanged.
"""

from __future__ import annotations

import re
import time

import pandas as pd


GAME_ID_PATTERN = re.compile(r"^\d{10}$")

API_REQUIRED_COLUMNS = {
    "gameId",
    "teamTricode",
    "personIdOff",
    "firstNameOff",
    "familyNameOff",
    "personIdDef",
    "firstNameDef",
    "familyNameDef",
    "matchupMinutes",
    "partialPossessions",
    "percentageDefenderTotalTime",
    "percentageOffensiveTotalTime",
    "percentageTotalTimeBothOn",
    "switchesOn",
    "playerPoints",
    "teamPoints",
    "matchupAssists",
    "matchupPotentialAssists",
    "matchupTurnovers",
    "matchupBlocks",
    "matchupFieldGoalsMade",
    "matchupFieldGoalsAttempted",
    "matchupFieldGoalsPercentage",
    "matchupThreePointersMade",
    "matchupThreePointersAttempted",
    "matchupThreePointersPercentage",
    "helpBlocks",
    "helpFieldGoalsMade",
    "helpFieldGoalsAttempted",
    "matchupFreeThrowsMade",
    "matchupFreeThrowsAttempted",
    "shootingFouls",
}


def _full_name(first_name, family_name):
    first = "" if pd.isna(first_name) else str(first_name).strip()
    family = "" if pd.isna(family_name) else str(family_name).strip()
    return " ".join(part for part in [first, family] if part)


def _format_matchup_minutes(value):
    """Normalize NBA API matchup time such as 0:17 to the manual CSV style 00:17."""
    if pd.isna(value):
        return ""

    text = str(value).strip()
    parts = text.split(":")

    if len(parts) == 2:
        minutes, seconds = parts
        return f"{int(minutes):02d}:{int(seconds):02d}"

    if len(parts) == 3:
        hours, minutes, seconds = parts
        total_minutes = int(hours) * 60 + int(minutes)
        return f"{total_minutes:02d}:{int(seconds):02d}"

    return text


def _pct_to_display(value):
    """NBA matchup endpoint returns fractions; NBA.com table displays percentages."""
    if pd.isna(value):
        return 0.0
    return float(value) * 100


def normalize_boxscore_matchups(api_df, game_number):
    """
    Convert BoxScoreMatchupsV3 PlayerStats into the project's matchup schema.

    The V3 response is organized by the defender's team. Therefore teamTricode
    is treated as DEF Team and OFF Team is the other team in the game.
    """
    missing = sorted(API_REQUIRED_COLUMNS - set(api_df.columns))
    if missing:
        raise ValueError(
            "BoxScoreMatchupsV3 response is missing required columns: "
            + ", ".join(missing)
        )

    team_codes = sorted(
        api_df["teamTricode"].dropna().astype(str).str.strip().unique().tolist()
    )

    if len(team_codes) != 2:
        raise ValueError(
            "Expected exactly two teams in BoxScoreMatchupsV3 response; "
            f"found {team_codes!r}."
        )

    opponent = {
        team_codes[0]: team_codes[1],
        team_codes[1]: team_codes[0],
    }

    result = pd.DataFrame({
        "Game": int(game_number),
        "Game ID": api_df["gameId"].astype(str),
        "OFF Player ID": api_df["personIdOff"],
        "Offense Player": [
            _full_name(first, family)
            for first, family in zip(
                api_df["firstNameOff"],
                api_df["familyNameOff"],
            )
        ],
        "OFF Team": api_df["teamTricode"].map(opponent),
        "DEF Player ID": api_df["personIdDef"],
        "Defense Player": [
            _full_name(first, family)
            for first, family in zip(
                api_df["firstNameDef"],
                api_df["familyNameDef"],
            )
        ],
        "DEF Team": api_df["teamTricode"].astype(str).str.strip(),
        "MIN": api_df["matchupMinutes"].map(_format_matchup_minutes),
        "Partial Poss": api_df["partialPossessions"],
        "DEF Time Percent": api_df["percentageDefenderTotalTime"].map(
            _pct_to_display
        ),
        "OFF Time Percent": api_df["percentageOffensiveTotalTime"].map(
            _pct_to_display
        ),
        "Both On Percent": api_df["percentageTotalTimeBothOn"].map(
            _pct_to_display
        ),
        "Players PTS": api_df["playerPoints"],
        "Team PTS": api_df["teamPoints"],
        "AST": api_df["matchupAssists"],
        "Potential AST": api_df["matchupPotentialAssists"],
        "TOV": api_df["matchupTurnovers"],
        "BLK": api_df["matchupBlocks"],
        "FGM": api_df["matchupFieldGoalsMade"],
        "FGA": api_df["matchupFieldGoalsAttempted"],
        "FG%": api_df["matchupFieldGoalsPercentage"].map(_pct_to_display),
        "3PM": api_df["matchupThreePointersMade"],
        "3PA": api_df["matchupThreePointersAttempted"],
        "3P%": api_df["matchupThreePointersPercentage"].map(_pct_to_display),
        "FTM": api_df["matchupFreeThrowsMade"],
        "FTA": api_df["matchupFreeThrowsAttempted"],
        "SFL": api_df["shootingFouls"],
        "Switches On": api_df["switchesOn"],
        "Help BLK": api_df["helpBlocks"],
        "Help FGM": api_df["helpFieldGoalsMade"],
        "Help FGA": api_df["helpFieldGoalsAttempted"],
    })

    return result


def fetch_boxscore_matchups(game_id, timeout=30, retries=3, backoff_seconds=2):
    """
    Fetch BoxScoreMatchupsV3 PlayerStats through nba_api.

    Network calls are intentionally kept out of automated tests because NBA.com
    can rate-limit or time out. The normalization logic is tested separately.
    """
    game_id = str(game_id).strip()

    if not GAME_ID_PATTERN.fullmatch(game_id):
        raise ValueError("game_id must be a 10-digit NBA game ID.")

    try:
        from nba_api.stats.endpoints import boxscorematchupsv3
    except ImportError as exc:
        raise RuntimeError(
            "nba_api is not installed. Run: "
            "pip install -r requirements-data.txt"
        ) from exc

    last_error = None

    for attempt in range(1, retries + 1):
        try:
            endpoint = boxscorematchupsv3.BoxScoreMatchupsV3(
                game_id=game_id,
                timeout=timeout,
            )
            frame = endpoint.player_stats.get_data_frame()

            if frame.empty:
                raise RuntimeError(
                    f"NBA matchup endpoint returned no rows for game {game_id}."
                )

            return frame

        except Exception as exc:  # network/API errors vary across nba_api versions
            last_error = exc

            if attempt < retries:
                time.sleep(backoff_seconds * attempt)

    raise RuntimeError(
        f"Failed to fetch NBA matchup data for game {game_id} "
        f"after {retries} attempts."
    ) from last_error


def fetch_and_normalize_game(
    game_id,
    game_number,
    timeout=30,
    retries=3,
):
    """Fetch one NBA game and return data ready for the project's pipeline."""
    raw = fetch_boxscore_matchups(
        game_id=game_id,
        timeout=timeout,
        retries=retries,
    )
    return normalize_boxscore_matchups(raw, game_number=game_number)
