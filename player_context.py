"""Offline traditional player box scores, kept separate from matchup outcomes."""

import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from artifact_integrity import matches_text_sha256
from game_context import load_game_context
from series_catalog import load_series

STATS = {
    "points": "points",
    "fieldGoalsMade": "fgm",
    "fieldGoalsAttempted": "fga",
    "threePointersMade": "three_pm",
    "freeThrowsMade": "ftm",
    "freeThrowsAttempted": "fta",
    "turnovers": "turnovers",
    "foulsPersonal": "personal_fouls",
    "plusMinusPoints": "plus_minus",
}
COLUMNS = [
    "game_id",
    "game_number",
    "game_date",
    "team",
    "player_id",
    "player",
    "played",
    "starter",
    "comment",
    "minutes_seconds",
    "game_seconds",
    *STATS.values(),
]


def manifest_digest(manifest):
    return hashlib.sha256(
        json.dumps(manifest.to_dict(), sort_keys=True).encode()
    ).hexdigest()


def integer(value, label, *, signed=False):
    if isinstance(value, bool):
        raise ValueError(f"Invalid {label}.")  # noqa: TRY004 - uniform data validation error
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {label}.") from exc
    if not math.isfinite(number) or number % 1 or (not signed and number < 0):
        raise ValueError(f"Invalid {label}.")
    return int(number)


def minutes_seconds(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d+:[0-5]\d(?:\.\d+)?", value):
        raise ValueError("Invalid box-score minutes.")
    minutes, seconds = value.split(":")
    return int(minutes) * 60 + float(seconds)


def normalize_player_boxscore(payload, game, manifest):
    """Normalize the nested V3 response without requiring nba_api in the app."""
    if not isinstance(payload, dict) or not payload:
        raise ValueError("Box-score response must be a nonempty JSON object.")
    box = payload.get("boxScoreTraditional", {})
    if not isinstance(box, dict) or box.get("gameId") != game.game_id:
        raise ValueError("Box score belongs to a different game.")
    rows = []
    for side in ("homeTeam", "awayTeam"):
        team = box.get(side, {})
        if not isinstance(team, dict) or not team:
            raise ValueError("Box score is missing a team object.")
        code = team.get("teamTricode")
        if code not in (manifest.team_a, manifest.team_b):
            raise ValueError("Box score contains an unexpected team.")
        players = team.get("players")
        if not isinstance(players, list) or not players:
            raise ValueError("Box score is missing its player roster.")
        duration = minutes_seconds(team.get("statistics", {}).get("minutes")) / 5
        for player in players:
            if not isinstance(player, dict) or not player:
                raise ValueError("Invalid player object in box score.")
            stats = player.get("statistics", {})
            if (
                not isinstance(stats, dict)
                or set(STATS) - set(stats)
                or "minutes" not in stats
            ):
                raise ValueError("Box score is missing required player statistics.")
            comment = str(player.get("comment") or "").strip()
            position = str(player.get("position") or "").strip()
            if position not in ("", "G", "F", "C"):
                raise ValueError("Unrecognized box-score starting position.")
            raw_minutes = stats["minutes"]
            played = isinstance(raw_minutes, str) and bool(raw_minutes.strip())
            if not played and not comment:
                raise ValueError(
                    "Missing minutes without a non-participation explanation."
                )
            if played and comment:
                raise ValueError("Box-score participation contradicts its comment.")
            if not played and position:
                raise ValueError("A non-participant cannot be marked as a starter.")
            name = " ".join(
                str(player.get(k) or "").strip() for k in ("firstName", "familyName")
            ).strip()
            values = {}
            for raw, column in STATS.items():
                if played:
                    values[column] = integer(
                        stats[raw], raw, signed=column == "plus_minus"
                    )
                else:
                    if (
                        stats[raw] is not None
                        and integer(stats[raw], raw, signed=column == "plus_minus") != 0
                    ):
                        raise ValueError(
                            "Non-participant has nonzero box-score statistics."
                        )
                    values[column] = None
            rows.append(
                {
                    "game_id": game.game_id,
                    "game_number": game.game_number,
                    "game_date": game.game_date,
                    "team": code,
                    "player_id": integer(player.get("personId"), "personId"),
                    "player": name,
                    "played": played,
                    "starter": bool(position) if played else None,
                    "comment": comment,
                    "minutes_seconds": minutes_seconds(raw_minutes.strip())
                    if played
                    else None,
                    "game_seconds": duration,
                    **values,
                }
            )
    return pd.DataFrame(rows, columns=COLUMNS)


def validate_player_context(frame, manifest, game_context, matchups):
    if set(COLUMNS) - set(frame.columns) or frame.empty:
        raise ValueError("Player context is empty or missing required columns.")
    if game_context is None:
        raise ValueError(
            "Verified team game context is required for box-score validation."
        )
    if frame.duplicated(["game_id", "player_id"]).any():
        raise ValueError("Duplicate player IDs in a box score.")
    if set(frame.game_id) != {g.game_id for g in manifest.games}:
        raise ValueError("Player context has incomplete or unexpected game coverage.")
    if frame.player.isna().any() or frame.player.astype(str).str.strip().eq("").any():
        raise ValueError("Player context has a blank player identity.")
    for value in frame.player_id:
        if integer(value, "player_id") <= 0:
            raise ValueError("Player IDs must be positive integers.")
    if frame.groupby("player_id").team.nunique().gt(1).any():
        raise ValueError("Player team identity changes within the series.")
    for game in manifest.games:
        group = frame[frame.game_id == game.game_id]
        if (
            not group.game_number.eq(game.game_number).all()
            or not group.game_date.eq(game.game_date).all()
        ):
            raise ValueError(
                "Player context dates or game numbers differ from its manifest."
            )
        if set(group.team) != {manifest.team_a, manifest.team_b}:
            raise ValueError("Player context must include both teams for every game.")
        if group.game_seconds.nunique(dropna=False) != 1:
            raise ValueError("Game duration must agree for both team rosters.")
        duration = integer(group.game_seconds.iloc[0], "game duration")
        if duration < 48 * 60 or (duration - 48 * 60) % (5 * 60):
            raise ValueError(
                "Game duration must be 48 minutes plus five-minute overtimes."
            )
        for row in group.to_dict("records"):
            if not isinstance(row["played"], bool):
                raise ValueError("Invalid player participation flag.")  # noqa: TRY004 - uniform data validation error
            if row["played"]:
                if (
                    not isinstance(row["starter"], bool)
                    or pd.notna(row["comment"])
                    and str(row["comment"]).strip()
                ):
                    raise ValueError("Invalid starter or participation evidence.")
                sec = pd.to_numeric(row["minutes_seconds"], errors="coerce")
                if (
                    pd.isna(sec)
                    or not math.isfinite(sec)
                    or sec < 0
                    or sec > duration + 1
                ):
                    raise ValueError("Invalid player minutes.")
                for column in STATS.values():
                    integer(row[column], column, signed=column == "plus_minus")
                if (
                    row["fgm"] > row["fga"]
                    or row["ftm"] > row["fta"]
                    or row["three_pm"] > row["fgm"]
                ):
                    raise ValueError("Impossible shooting counts in box score.")
                if row["points"] != 2 * row["fgm"] + row["three_pm"] + row["ftm"]:
                    raise ValueError("Box-score points contradict scoring counts.")
            elif (
                pd.isna(row["comment"])
                or not str(row["comment"]).strip()
                or any(
                    pd.notna(row[c])
                    for c in ["starter", "minutes_seconds", *STATS.values()]
                )
            ):
                raise ValueError(
                    "Non-participant statistics must remain missing with a source comment."
                )
        result = game_context[game_context.game_id == game.game_id].iloc[0]
        for side, team in (("a", manifest.team_a), ("b", manifest.team_b)):
            played = group[group.team.eq(team) & group.played]
            if played.starter.eq(True).sum() != 5:
                raise ValueError("Box score must contain five starters per team.")
            if abs(played.minutes_seconds.sum() - 5 * duration) > len(played):
                raise ValueError(
                    "Player minutes do not reconcile with team playing time."
                )
            if int(played.points.sum()) != result[f"team_{side}_points"]:
                raise ValueError(
                    "Player points do not reconcile with verified team score."
                )
            # Summed on-court +/- is five times the final team differential.
            margin = result.team_a_margin * (1 if side == "a" else -1)
            if int(played.plus_minus.sum()) != 5 * margin:
                raise ValueError(
                    "Player plus/minus does not reconcile with team margin."
                )
        game_matchups = matchups[matchups.game_id == game.game_id]
        for role in ("off", "def"):
            identities = game_matchups[
                [f"{role}_team", f"{role}_player_id"]
            ].drop_duplicates()
            available = set(zip(group.team, group.player_id))
            if not set(
                zip(identities[f"{role}_team"], identities[f"{role}_player_id"])
            ).issubset(available):
                raise ValueError(
                    "Matchup player IDs do not align with box-score rosters."
                )
    return frame


def load_player_context(manifest, project_root):
    root = Path(project_root)
    path = root / "data/player_context" / f"{manifest.series_id}.csv"
    if not path.exists():
        return None
    report_path = path.with_suffix(".report.json")
    if not report_path.exists():
        raise ValueError("Player context is missing its provenance report.")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or not report:
        raise ValueError("Player context provenance must be a JSON object.")
    if (
        report.get("status") != "complete"
        or report.get("schema_version") != 1
        or report.get("endpoint") != "NBA BoxScoreTraditionalV3"
        or report.get("series_id") != manifest.series_id
        or report.get("manifest_sha256") != manifest_digest(manifest)
        or not matches_text_sha256(path, report.get("dataset_sha256"))
    ):
        raise ValueError("Player context integrity or manifest verification failed.")
    for relative, field in [
        ("data/context", "team_game_log_sha256"),
        ("data/snapshots", "matchup_dataset_sha256"),
    ]:
        dependency = root / relative / f"{manifest.series_id}.csv"
        if not dependency.exists() or not matches_text_sha256(
            dependency, report.get(field)
        ):
            raise ValueError(
                "Player context belongs to different team or matchup evidence."
            )
    frame = pd.read_csv(path, dtype={"game_id": str, "game_date": str})
    evidence = report.get("games", [])
    if not isinstance(evidence, list) or any(
        not isinstance(item, dict) for item in evidence
    ):
        raise ValueError("Invalid player context game evidence.")
    if report.get("rows") != len(frame) or [g.get("game_id") for g in evidence] != [
        g.game_id for g in manifest.games
    ]:
        raise ValueError(
            "Player context report has inconsistent game coverage or row counts."
        )
    for item in evidence:
        acquisition = item.get("acquisition", {})
        if not isinstance(acquisition, dict) or not acquisition:
            raise ValueError("Player context is missing acquisition evidence.")
        stamp = acquisition.get("fetched_at")
        try:
            timestamp = (
                datetime.fromisoformat(stamp) if isinstance(stamp, str) else None
            )
        except ValueError as exc:
            raise ValueError(
                "Player context has invalid acquisition evidence."
            ) from exc
        if (
            item.get("status") not in ("cached", "fetched")
            or item.get("rows") != len(frame[frame.game_id == item["game_id"]])
            or timestamp is None
            or timestamp.tzinfo is None
            or acquisition.get("game_id") != item["game_id"]
            or acquisition.get("endpoint") != report["endpoint"]
            or not re.fullmatch(r"[0-9a-f]{64}", str(acquisition.get("raw_sha256", "")))
        ):
            raise ValueError("Player context has invalid acquisition evidence.")
    matchups, _, _ = load_series(manifest, root)
    return validate_player_context(
        frame, manifest, load_game_context(manifest, root), matchups
    )


def player_context_display(context, matchups, manifest, team, player):
    ids = (
        matchups.loc[
            matchups.off_team.eq(team) & matchups.offense_player.eq(player),
            "off_player_id",
        ]
        .dropna()
        .unique()
    )
    if len(ids) != 1:
        raise ValueError("Selected player has no unique NBA identity in matchup data.")
    selected = context[context.team.eq(team) & context.player_id.eq(ids[0])].set_index(
        "game_id"
    )
    rows = []
    for game in manifest.games:
        row = selected.loc[game.game_id] if game.game_id in selected.index else None
        played = row is not None and row.played
        seconds = row.minutes_seconds if played else None
        rows.append(
            {
                "Game": f"Game {game.game_number}",
                "Date": game.game_date,
                "Status": "Played"
                if played
                else str(row.comment)
                if row is not None
                else "Not listed in box score",
                "Starter": "Yes"
                if played and row.starter
                else "No"
                if played
                else None,
                "Minutes": f"{int(seconds) // 60}:{int(seconds) % 60:02d}"
                if played
                else None,
                **{
                    label: int(row[column]) if played else None
                    for label, column in {
                        "PTS": "points",
                        "FGA": "fga",
                        "FTA": "fta",
                        "TOV": "turnovers",
                        "PF": "personal_fouls",
                        "+/-": "plus_minus",
                    }.items()
                },
            }
        )
    return pd.DataFrame(rows)
