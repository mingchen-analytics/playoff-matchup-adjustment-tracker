"""Data preparation and validation for matchup data."""

from __future__ import annotations

import math
import re

import pandas as pd


REQUIRED_COLUMNS = {
    "game",
    "offense_player",
    "off_team",
    "defense_player",
    "def_team",
    "min",
    "partial_poss",
    "players_pts",
    "team_pts",
    "ast",
    "tov",
    "blk",
    "fgm",
    "fga",
    "3pm",
    "3pa",
    "ftm",
    "fta",
    "sfl",
}

TEXT_COLUMNS = [
    "offense_player",
    "defense_player",
    "off_team",
    "def_team",
]

NUMERIC_COLUMNS = [
    "partial_poss",
    "players_pts",
    "team_pts",
    "ast",
    "tov",
    "blk",
    "fgm",
    "fga",
    "3pm",
    "3pa",
    "ftm",
    "fta",
    "sfl",
]


def normalize_column_name(name):
    """Convert source column names to stable snake_case-style names."""
    return (
        str(name)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("%", "percent")
    )


def parse_matchup_time(value):
    """
    Convert matchup time to seconds.

    Supported inputs:
    - MM:SS
    - HH:MM:SS
    - Excel time fractions between 0 and 1
    - numeric seconds

    Invalid values return NaN so validation can surface them instead of
    silently converting them to zero.
    """
    if pd.isna(value):
        return math.nan

    text = str(value).strip()

    if not text:
        return math.nan

    if ":" in text:
        parts = text.split(":")

        try:
            numbers = [int(part) for part in parts]
        except ValueError:
            return math.nan

        if len(numbers) == 2:
            minutes, seconds = numbers
            if minutes < 0 or not 0 <= seconds < 60:
                return math.nan
            return minutes * 60 + seconds

        if len(numbers) == 3:
            hours, minutes, seconds = numbers
            if (
                hours < 0
                or not 0 <= minutes < 60
                or not 0 <= seconds < 60
            ):
                return math.nan
            return hours * 3600 + minutes * 60 + seconds

        return math.nan

    try:
        numeric_value = float(text)
    except ValueError:
        return math.nan

    if numeric_value < 0:
        return math.nan

    if 0 < numeric_value < 1:
        return numeric_value * 24 * 60 * 60

    return numeric_value


def _blank_mask(series):
    normalized = (
        series.astype("string")
        .str.replace("\xa0", " ", regex=False)
        .str.strip()
    )
    return normalized.isna() | normalized.eq("")


def _format_issue(label, count):
    return f"{label}: {count} row{'s' if count != 1 else ''}"


def prepare_matchup_data(raw_df):
    """
    Normalize, validate, and prepare matchup data for analysis.

    Returns
    -------
    cleaned_df : pandas.DataFrame
        Normalized dataframe with matchup_seconds and numeric fields prepared.
    report : dict
        Data-quality summary with errors and warnings.

    The function does not silently remove invalid observations. Callers should
    stop downstream analysis when report["errors"] is non-empty.
    """
    df = raw_df.copy()

    df.columns = [normalize_column_name(column) for column in df.columns]

    duplicate_column_names = (
        pd.Series(df.columns)
        .value_counts()
        .loc[lambda counts: counts > 1]
        .index
        .tolist()
    )

    missing_columns = sorted(REQUIRED_COLUMNS - set(df.columns))

    report = {
        "status": "pass",
        "rows": len(df),
        "games": 0,
        "offensive_players": 0,
        "teams": [],
        "duplicate_rows": 0,
        "zero_matchup_time_rows": 0,
        "errors": [],
        "warnings": [],
    }

    if duplicate_column_names:
        report["errors"].append(
            "Duplicate normalized column names: "
            + ", ".join(duplicate_column_names)
        )

    if missing_columns:
        report["errors"].append(
            "Missing required columns: " + ", ".join(missing_columns)
        )
        report["status"] = "fail"
        return df, report

    for column in TEXT_COLUMNS:
        df[column] = (
            df[column]
            .astype("string")
            .str.replace("\xa0", " ", regex=False)
            .str.strip()
        )

        blank_count = int(_blank_mask(df[column]).sum())
        if blank_count:
            report["errors"].append(
                _format_issue(f"Blank {column}", blank_count)
            )

    raw_game = df["game"].copy()
    df["game"] = pd.to_numeric(df["game"], errors="coerce")

    invalid_game_mask = (
        df["game"].isna()
        | (df["game"] <= 0)
        | (df["game"] % 1 != 0)
    )
    invalid_game_count = int(invalid_game_mask.sum())

    if invalid_game_count:
        report["errors"].append(
            _format_issue("Invalid game number", invalid_game_count)
        )
    else:
        df["game"] = df["game"].astype(int)

    df["matchup_seconds"] = df["min"].apply(parse_matchup_time)
    invalid_time_count = int(df["matchup_seconds"].isna().sum())

    if invalid_time_count:
        report["errors"].append(
            _format_issue("Invalid matchup time", invalid_time_count)
        )

    for column in NUMERIC_COLUMNS:
        source = df[column].copy()
        converted = pd.to_numeric(source, errors="coerce")

        invalid_numeric_mask = (
            converted.isna()
            & ~_blank_mask(source)
        )
        invalid_numeric_count = int(invalid_numeric_mask.sum())

        if invalid_numeric_count:
            report["errors"].append(
                _format_issue(
                    f"Non-numeric {column}",
                    invalid_numeric_count,
                )
            )

        missing_numeric_count = int(_blank_mask(source).sum())
        if missing_numeric_count:
            report["errors"].append(
                _format_issue(
                    f"Missing {column}",
                    missing_numeric_count,
                )
            )

        negative_count = int((converted < 0).fillna(False).sum())
        if negative_count:
            report["errors"].append(
                _format_issue(
                    f"Negative {column}",
                    negative_count,
                )
            )

        df[column] = converted

    duplicate_rows = int(df.duplicated().sum())
    report["duplicate_rows"] = duplicate_rows

    if duplicate_rows:
        report["errors"].append(
            _format_issue("Exact duplicate rows", duplicate_rows)
        )

    if not invalid_time_count:
        zero_time_rows = int((df["matchup_seconds"] == 0).sum())
        report["zero_matchup_time_rows"] = zero_time_rows

        if zero_time_rows:
            report["warnings"].append(
                _format_issue(
                    "Zero matchup-time observations",
                    zero_time_rows,
                )
            )

    if not invalid_game_count:
        games = sorted(df["game"].dropna().unique().tolist())
        report["games"] = len(games)

        if games:
            expected_games = list(range(min(games), max(games) + 1))
            if games != expected_games:
                report["warnings"].append(
                    "Game sequence contains gaps: "
                    + ", ".join(str(game) for game in games)
                )

    same_team_count = int(
        (
            df["off_team"].notna()
            & df["def_team"].notna()
            & df["off_team"].eq(df["def_team"])
        ).sum()
    )
    if same_team_count:
        report["errors"].append(
            _format_issue(
                "Rows with identical offense and defense teams",
                same_team_count,
            )
        )

    report["offensive_players"] = int(
        df["offense_player"].nunique(dropna=True)
    )
    report["teams"] = sorted(
        set(df["off_team"].dropna())
        | set(df["def_team"].dropna())
    )

    if report["errors"]:
        report["status"] = "fail"
    elif report["warnings"]:
        report["status"] = "warning"

    return df, report
