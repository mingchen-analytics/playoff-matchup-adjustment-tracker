"""Validated, offline game results; never aggregate matchup rows into box scores."""

import json
from pathlib import Path

import pandas as pd

from artifact_integrity import matches_text_sha256
from data_sources.game_discovery import discover_from_game_log


def build_game_context(frame, manifest):
    """Build scores from a team game log, with opponent PTS = PTS - PLUS_MINUS."""
    if {"PTS", "PLUS_MINUS"} - set(frame.columns):
        raise ValueError("Game context requires PTS and PLUS_MINUS.")
    discovered = discover_from_game_log(
        frame, manifest.season, manifest.team_a, manifest.team_b
    )
    if (
        discovered.games != manifest.games
        or discovered.series_complete != manifest.series_complete
    ):
        raise ValueError("Game context coverage or dates differ from the manifest.")
    log = (
        frame[
            frame.TEAM_ABBREVIATION.eq(manifest.team_a)
            & frame.SEASON_ID.astype(str).eq("4" + manifest.season[:4])
            & frame.GAME_ID.isin([g.game_id for g in manifest.games])
        ]
        .drop_duplicates()
        .copy()
    )
    if log.GAME_ID.duplicated().any():
        raise ValueError("Conflicting game context rows.")
    log = log.set_index("GAME_ID")
    wins_a = wins_b = 0
    rows = []
    for game in manifest.games:
        row = log.loc[game.game_id]
        points = pd.to_numeric(row.PTS, errors="coerce")
        margin = pd.to_numeric(row.PLUS_MINUS, errors="coerce")
        if (
            pd.isna(points)
            or pd.isna(margin)
            or points in (float("inf"), float("-inf"))
            or margin in (float("inf"), float("-inf"))
            or points % 1
            or margin % 1
            or points < 0
            or points - margin < 0
            or margin == 0
        ):
            raise ValueError(
                "Game context scores and margins must be finite valid integers."
            )
        if (margin > 0) != (row.WL == "W"):
            raise ValueError("Game context result contradicts its point differential.")
        home = row.MATCHUP == f"{manifest.team_a} vs. {manifest.team_b}"
        if not home and row.MATCHUP != f"{manifest.team_a} @ {manifest.team_b}":
            raise ValueError("Game context has an invalid home/away matchup.")
        before_a, before_b = wins_a, wins_b
        wins_a += margin > 0
        wins_b += margin < 0
        rows.append(
            {
                "game_number": game.game_number,
                "game_id": game.game_id,
                "game_date": game.game_date,
                "team_a_home": home,
                "team_a_points": int(points),
                "team_b_points": int(points - margin),
                "team_a_margin": int(margin),
                "team_a_wins_before": before_a,
                "team_b_wins_before": before_b,
                "team_a_wins_after": wins_a,
                "team_b_wins_after": wins_b,
            }
        )
    return pd.DataFrame(rows)


def load_game_context(manifest, project_root, *, source_path=None):
    """Optional published game log, bound to the original snapshot discovery hash."""
    root = Path(project_root)
    path = (
        Path(source_path)
        if source_path is not None
        else root / "data/context" / f"{manifest.series_id}.csv"
    )
    if not path.exists():
        if source_path is not None:
            raise ValueError("Game context source file is unavailable.")
        return None
    report_path = root / "data/snapshots" / f"{manifest.series_id}.report.json"
    if not report_path.exists():
        raise ValueError("Game context is missing its source evidence.")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("series_id") != manifest.series_id or not matches_text_sha256(
        path, report.get("discovery_sha256")
    ):
        raise ValueError("Game context hash differs from its discovery evidence.")
    return build_game_context(
        pd.read_csv(path, dtype={"GAME_ID": str, "SEASON_ID": str}), manifest
    )


def context_for_team(context, manifest, team):
    """Display scores and series records consistently from the selected team's view."""
    if team not in (manifest.team_a, manifest.team_b):
        raise ValueError("Context team must belong to the series.")
    side, other = ("a", "b") if team == manifest.team_a else ("b", "a")
    opponent = manifest.team_b if side == "a" else manifest.team_a
    rows = []
    for row in context.to_dict("records"):
        home = row["team_a_home"] if side == "a" else not row["team_a_home"]
        margin = row["team_a_margin"] * (1 if side == "a" else -1)
        rows.append(
            {
                "Game": f"Game {row['game_number']}",
                "Date": row["game_date"],
                "Venue": "Home" if home else "Away",
                "Score": f"{team} {row[f'team_{side}_points']} – {opponent} {row[f'team_{other}_points']}",
                "Result": "W" if margin > 0 else "L",
                "Margin": margin,
                "Series before": f"{row[f'team_{side}_wins_before']}–{row[f'team_{other}_wins_before']}",
                "Series after": f"{row[f'team_{side}_wins_after']}–{row[f'team_{other}_wins_after']}",
            }
        )
    return pd.DataFrame(rows)
