"""Versioned processed schema and compatibility boundary for existing analytics."""

from __future__ import annotations
import pandas as pd

from data_pipeline import prepare_matchup_data

SCHEMA_VERSION = 1
RENAME = {
    "game": "game_number",
    "offense_player": "off_player",
    "defense_player": "def_player",
    "off_player_id": "off_player_id",
    "def_player_id": "def_player_id",
    "partial_poss": "partial_possessions",
    "players_pts": "player_points",
    "team_pts": "team_points",
    "3pm": "three_pm",
    "3pa": "three_pa",
    "fgpercent": "fg_pct",
    "3ppercent": "three_pct",
    "sfl": "shooting_fouls",
}
METADATA = [
    "schema_version",
    "season",
    "season_type",
    "playoff_round",
    "series_id",
    "game_id",
    "game_number",
    "game_date",
]
CORE = [
    "off_team_id",
    "off_team",
    "off_player_id",
    "off_player",
    "def_team_id",
    "def_team",
    "def_player_id",
    "def_player",
    "matchup_seconds",
    "partial_possessions",
    "def_time_percent",
    "off_time_percent",
    "both_on_percent",
    "player_points",
    "team_points",
    "ast",
    "potential_ast",
    "tov",
    "blk",
    "fgm",
    "fga",
    "fg_pct",
    "three_pm",
    "three_pa",
    "three_pct",
    "ftm",
    "fta",
    "shooting_fouls",
    "switches_on",
    "help_blk",
    "help_fgm",
    "help_fga",
]
COLUMNS = METADATA + CORE + ["data_source"]
REQUIRED_VALUES = [
    "game_number",
    "off_team",
    "def_team",
    "off_player",
    "def_player",
    "matchup_seconds",
    "partial_possessions",
    "player_points",
    "team_points",
    "ast",
    "tov",
    "blk",
    "fgm",
    "fga",
    "three_pm",
    "three_pa",
    "ftm",
    "fta",
    "shooting_fouls",
]


def _raise_on_errors(report):
    if report["errors"]:
        raise ValueError("Data validation failed: " + "; ".join(report["errors"]))


def to_processed(raw, manifest, data_source):
    cleaned, report = prepare_matchup_data(raw)
    _raise_on_errors(report)
    if cleaned.empty:
        raise ValueError("Series dataset is empty.")
    result = cleaned.rename(columns=RENAME)
    if data_source == "nba_boxscorematchupsv3":
        for col in ("off_player_id", "def_player_id"):
            if col not in result or result[col].isna().any():
                raise ValueError(f"API rows require {col}.")
        for col in (
            "def_time_percent",
            "off_time_percent",
            "both_on_percent",
            "fg_pct",
            "three_pct",
        ):
            if col not in result or result[col].isna().any():
                raise ValueError(f"API rows require {col}.")
    result = result.drop(columns=["min"], errors="ignore")
    for key in ("season", "season_type", "playoff_round", "series_id"):
        result[key] = getattr(manifest, key)
    result["schema_version"] = SCHEMA_VERSION
    result["data_source"] = data_source
    game_info = {g.game_number: g for g in manifest.games}
    if not set(result.game_number).issubset(game_info):
        raise ValueError("Dataset contains game numbers outside its manifest.")
    for number, rows in result.groupby("game_number"):
        game = game_info[number]
        if "game_id" in rows and game.game_id and rows.game_id.notna().any():
            if not rows.game_id.astype("string").eq(game.game_id).all():
                raise ValueError(f"Wrong game ID for Game {number}.")
    result["game_id"] = result.game_number.map(
        {k: g.game_id for k, g in game_info.items()}
    )
    result["game_date"] = result.game_number.map(
        {k: g.game_date for k, g in game_info.items()}
    )
    for col in COLUMNS:
        if col not in result:
            result[col] = pd.NA
    result = result[COLUMNS].copy()
    validate_processed(result, manifest, require_all=False)
    return result, report


def to_analytics(frame):
    """Adapt processed names; seconds never pass through Excel-fraction parsing."""
    reverse = {new: old for old, new in RENAME.items() if old != new}
    result = frame.rename(columns=reverse).copy()
    # Use numeric seconds directly. A string fraction <1 otherwise means Excel time.
    result["min"] = result.matchup_seconds.map(
        lambda v: f"{int(v) // 60}:{int(v) % 60:02d}" if pd.notna(v) else ""
    )
    cleaned, report = prepare_matchup_data(result)
    # Preserve fractional seconds exactly; legacy MM:SS is only a validation bridge.
    cleaned["matchup_seconds"] = pd.to_numeric(
        frame.matchup_seconds, errors="coerce"
    ).values
    report["warnings"] = [
        warning
        for warning in report["warnings"]
        if not warning.startswith("Zero matchup-time observations:")
    ]
    zero_rows = int(cleaned["matchup_seconds"].eq(0).sum())
    report["zero_matchup_time_rows"] = zero_rows
    if zero_rows:
        report["warnings"].append(f"Zero matchup-time observations: {zero_rows} rows")
    report["status"] = (
        "fail" if report["errors"] else "warning" if report["warnings"] else "pass"
    )
    return cleaned, report


def validate_processed(frame, manifest, require_all=True):
    missing = set(COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"Processed schema missing columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError("Series dataset is empty.")
    for key in ("season", "season_type", "playoff_round", "series_id"):
        if not frame[key].eq(getattr(manifest, key)).all():
            raise ValueError(f"Processed {key} does not match manifest.")
    if not frame.schema_version.eq(SCHEMA_VERSION).all():
        raise ValueError("Unsupported processed schema version.")
    if frame[REQUIRED_VALUES].isna().any().any():
        raise ValueError("Missing required processed values.")
    numbers = pd.to_numeric(frame.game_number, errors="coerce")
    expected = {g.game_number for g in manifest.games}
    if not set(numbers).issubset(expected) or (
        require_all and set(numbers) != expected
    ):
        raise ValueError("Processed game coverage differs from manifest.")
    if set(frame.off_team) | set(frame.def_team) != {manifest.team_a, manifest.team_b}:
        raise ValueError("Processed teams do not match manifest.")
    for game in manifest.games:
        rows = frame[numbers == game.game_number]
        if rows.empty:
            continue
        if game.game_id and not rows.game_id.astype("string").eq(game.game_id).all():
            raise ValueError("Processed game IDs do not match manifest.")
        if (
            game.game_date
            and not rows.game_date.astype("string").eq(game.game_date).all()
        ):
            raise ValueError("Processed game dates do not match manifest.")
    numeric = [
        c for c in CORE if c not in {"off_team", "off_player", "def_team", "def_player"}
    ]
    for col in numeric:
        values = pd.to_numeric(frame[col], errors="coerce")
        if (
            (frame[col].notna() & values.isna())
            | (values < 0)
            | (values.abs() == float("inf"))
        ).any():
            raise ValueError(f"Invalid processed numeric values: {col}")
    for col in ("off_team_id", "def_team_id", "off_player_id", "def_player_id"):
        values = pd.to_numeric(frame[col], errors="coerce").dropna()
        if ((values <= 0) | (values % 1 != 0)).any():
            raise ValueError(f"Invalid positive integer ID: {col}")
    if not frame.data_source.isin(["manual_nba_com", "nba_boxscorematchupsv3"]).all():
        raise ValueError("Unsupported or missing data_source provenance.")
    for col in (
        "def_time_percent",
        "off_time_percent",
        "both_on_percent",
        "fg_pct",
        "three_pct",
    ):
        if (pd.to_numeric(frame[col], errors="coerce") > 100).any():
            raise ValueError(f"Percentage outside 0–100: {col}")
    zero_distributions = (
        frame.groupby(["game_number", "off_team", "off_player"])
        .matchup_seconds.sum()
        .le(0)
    )
    if zero_distributions.any():
        raise ValueError(
            "A player-game has zero total matchup time; its matchup-share distribution is undefined."
        )
    keys = ["game_number", "off_team", "off_player", "def_team", "def_player"]
    if frame.duplicated(keys).any():
        raise ValueError("Duplicate matchup identities in a game.")
    _, report = to_analytics(frame)
    _raise_on_errors(report)
    return report
