"""Validated substitution/foul observations, without lineup or intent inference."""

import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from artifact_integrity import matches_text_sha256
from game_context import load_game_context
from player_context import integer, load_player_context, manifest_digest

EVENT_TYPES = ("Substitution", "Foul")
COLUMNS = [
    "game_id",
    "game_number",
    "game_date",
    "source_order",
    "action_number",
    "action_id",
    "period",
    "clock",
    "remaining_seconds",
    "elapsed_seconds",
    "team",
    "person_id",
    "recorded_player",
    "event_type",
    "subtype",
    "description",
]


def clock_seconds(clock, period):
    period = integer(period, "period")
    if period < 1:
        raise ValueError("Play-by-play periods must start at one.")
    match = re.fullmatch(r"PT(\d+)M(\d+(?:\.\d+)?)S", str(clock))
    if not match or float(match[2]) >= 60:
        raise ValueError("Invalid play-by-play clock.")
    remaining = int(match[1]) * 60 + float(match[2])
    duration = 720 if period <= 4 else 300
    if remaining > duration:
        raise ValueError("Play-by-play clock exceeds its period duration.")
    before = (period - 1) * 720 if period <= 4 else 2880 + (period - 5) * 300
    return remaining, before + duration - remaining


def normalize_events(payload, game, manifest, game_context, players):
    if not isinstance(payload, dict) or not isinstance(payload.get("game"), dict):
        raise ValueError("Play-by-play response must contain a game object.")  # noqa: TRY004 - uniform data validation error
    source = payload["game"]
    actions = source.get("actions")
    if (
        source.get("gameId") != game.game_id
        or not isinstance(actions, list)
        or not actions
    ):
        raise ValueError("Play-by-play game identity or action coverage is invalid.")
    roster = players[players.game_id == game.game_id]
    duration = integer(roster.game_seconds.iloc[0], "game duration")
    expected_periods = 4 + (duration - 2880) // 300
    starts, ends, rows = {}, {}, []
    for order, action in enumerate(actions):
        required = {
            "period",
            "clock",
            "actionType",
            "subType",
            "actionNumber",
            "actionId",
        }
        if not isinstance(action, dict) or required - set(action):
            raise ValueError("Play-by-play action is missing required fields.")
        period = integer(action["period"], "period")
        if not 1 <= period <= expected_periods:
            raise ValueError(
                "Play-by-play period differs from box-score game duration."
            )
        remaining, elapsed = clock_seconds(action["clock"], period)
        if action["actionType"] == "period":
            subtype = action["subType"]
            if subtype == "start":
                if period in starts or remaining != (720 if period <= 4 else 300):
                    raise ValueError("Invalid or duplicate period start.")
                starts[period] = order
            elif subtype == "end":
                if period in ends or remaining != 0:
                    raise ValueError("Invalid or duplicate period end.")
                ends[period] = (order, action)
        if action["actionType"] not in EVENT_TYPES:
            continue
        team = action.get("teamTricode")
        unassigned_technical = (
            team == ""
            and action["actionType"] == "Foul"
            and action["subType"] in ("Technical", "Bench Technical")
        )
        if team not in (manifest.team_a, manifest.team_b) and not unassigned_technical:
            raise ValueError("Timeline event has an unexpected team.")
        person = integer(action.get("personId"), "event personId")
        identified = roster[roster.team.eq(team) & roster.player_id.eq(person)]
        if action["actionType"] == "Substitution" and (
            identified.empty or not identified.iloc[0].played
        ):
            raise ValueError(
                "Substitution player ID is absent from the playing roster."
            )
        if (
            person
            and identified.empty
            and action["actionType"] == "Foul"
            and action["subType"] not in ("Technical", "Bench Technical")
        ):
            raise ValueError("Foul player ID does not align with the game roster.")
        description = action.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ValueError("Timeline event is missing its original description.")
        rows.append(
            {
                "game_id": game.game_id,
                "game_number": game.game_number,
                "game_date": game.game_date,
                "source_order": order,
                "action_number": integer(action["actionNumber"], "actionNumber"),
                "action_id": integer(action["actionId"], "actionId"),
                "period": period,
                "clock": action["clock"],
                "remaining_seconds": remaining,
                "elapsed_seconds": elapsed,
                "team": team,
                "person_id": person,
                "recorded_player": identified.iloc[0].player
                if not identified.empty
                else str(action.get("playerName") or "Non-player / unresolved"),
                "event_type": action["actionType"],
                "subtype": str(action["subType"] or ""),
                "description": description,
            }
        )
    if set(starts) != set(range(1, expected_periods + 1)) or set(ends) != set(starts):
        raise ValueError("Play-by-play is missing complete period boundaries.")
    for period, start in starts.items():
        if start >= ends[period][0] or (period > 1 and ends[period - 1][0] >= start):
            raise ValueError("Play-by-play period boundaries are out of source order.")
    result = game_context[game_context.game_id == game.game_id].iloc[0]
    final = ends[expected_periods][1]
    home, away = (
        (manifest.team_a, manifest.team_b)
        if result.team_a_home
        else (manifest.team_b, manifest.team_a)
    )
    home_pts = result.team_a_points if result.team_a_home else result.team_b_points
    away_pts = result.team_b_points if result.team_a_home else result.team_a_points
    if (
        integer(final.get("scoreHome"), "final home score") != home_pts
        or integer(final.get("scoreAway"), "final away score") != away_pts
    ):
        raise ValueError("Play-by-play final score differs from verified team results.")
    frame = pd.DataFrame(rows, columns=COLUMNS)
    validate_event_frame(frame, game, manifest, players)
    summary = {
        "raw_actions": len(actions),
        "periods": expected_periods,
        "game_seconds": duration,
        "home_team": home,
        "away_team": away,
        "final_home_score": int(home_pts),
        "final_away_score": int(away_pts),
        "duplicate_action_numbers": len(actions)
        - len({a["actionNumber"] for a in actions}),
        "substitutions": int(frame.event_type.eq("Substitution").sum()),
        "fouls": int(frame.event_type.eq("Foul").sum()),
    }
    return frame.sort_values(["elapsed_seconds", "source_order"]).reset_index(
        drop=True
    ), summary


def validate_event_frame(frame, game, manifest, players):
    if set(COLUMNS) - set(frame.columns) or frame.empty:
        raise ValueError("Timeline is empty or missing required columns.")
    if (
        not frame.game_id.eq(game.game_id).all()
        or not frame.game_number.eq(game.game_number).all()
        or not frame.game_date.eq(game.game_date).all()
    ):
        raise ValueError("Timeline game metadata differs from its manifest.")
    if frame.source_order.duplicated().any() or frame.action_id.duplicated().any():
        raise ValueError("Duplicate timeline source rows or action IDs.")
    roster = players[players.game_id == game.game_id]
    max_period = 4 + (int(roster.game_seconds.iloc[0]) - 2880) // 300
    for row in frame.to_dict("records"):
        for key in ("source_order", "action_number", "action_id", "person_id"):
            integer(row[key], key)
        period = integer(row["period"], "period")
        unassigned_technical = (
            row["team"] == ""
            and row["event_type"] == "Foul"
            and row["subtype"] in ("Technical", "Bench Technical")
        )
        if (
            not 1 <= period <= max_period
            or row["event_type"] not in EVENT_TYPES
            or row["team"] not in (manifest.team_a, manifest.team_b, "")
            or (row["team"] == "" and not unassigned_technical)
        ):
            raise ValueError("Invalid timeline event period, type or team.")
        remaining, elapsed = clock_seconds(row["clock"], period)
        if row["remaining_seconds"] != remaining or row["elapsed_seconds"] != elapsed:
            raise ValueError("Timeline elapsed time differs from its source clock.")
        if not isinstance(row["description"], str) or not row["description"].strip():
            raise ValueError("Missing timeline source description.")
        person = roster[
            roster.team.eq(row["team"]) & roster.player_id.eq(row["person_id"])
        ]
        if row["event_type"] == "Substitution" and (
            person.empty or not person.iloc[0].played
        ):
            raise ValueError("Invalid substitution player identity.")
        if (
            person.empty
            and row["person_id"]
            and row["event_type"] == "Foul"
            and row["subtype"] not in ("Technical", "Bench Technical")
        ):
            raise ValueError("Invalid foul player identity.")
        if not person.empty and row["recorded_player"] != person.iloc[0].player:
            raise ValueError(
                "Timeline player name does not match its recorded player ID."
            )
    return frame


def load_event_context(manifest, project_root):
    root = Path(project_root)
    folder = root / "data/event_context" / manifest.series_id
    if not folder.exists():
        return None
    report_path = folder / "report.json"
    if not report_path.exists():
        raise ValueError("Timeline is missing its provenance report.")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if (
        not isinstance(report, dict)
        or report.get("status") != "complete"
        or report.get("schema_version") != 1
        or report.get("endpoint") != "NBA PlayByPlayV3"
        or report.get("manifest_sha256") != manifest_digest(manifest)
        or report.get("series_id") != manifest.series_id
    ):
        raise ValueError("Invalid timeline provenance or manifest evidence.")
    games = report.get("games", [])
    if (
        not isinstance(games, list)
        or any(not isinstance(g, dict) for g in games)
        or [g.get("game_id") for g in games] != [g.game_id for g in manifest.games]
    ):
        raise ValueError("Timeline report has incomplete game coverage.")
    for directory, field in [
        ("context", "team_game_log_sha256"),
        ("player_context", "player_dataset_sha256"),
    ]:
        path = root / "data" / directory / f"{manifest.series_id}.csv"
        if not path.exists() or not matches_text_sha256(path, report.get(field)):
            raise ValueError("Timeline depends on different team/player snapshots.")
    players = load_player_context(manifest, root)
    results = load_game_context(manifest, root)
    if players is None or results is None:
        raise ValueError("Timeline requires verified team and player context.")
    frames = []
    for game, item in zip(manifest.games, games):
        path = folder / f"{game.game_id}.csv"
        if not path.exists() or not matches_text_sha256(
            path, item.get("dataset_sha256")
        ):
            raise ValueError("Timeline data hash differs from its ingestion evidence.")
        frame = pd.read_csv(
            path, dtype={"game_id": str, "game_date": str}, keep_default_na=False
        )
        validate_event_frame(frame, game, manifest, players)
        acquisition = item.get("acquisition", {})
        if (
            not isinstance(acquisition, dict)
            or acquisition.get("game_id") != game.game_id
            or acquisition.get("endpoint") != report["endpoint"]
        ):
            raise ValueError("Invalid timeline acquisition evidence.")
        stamp = acquisition.get("fetched_at")
        if (
            not isinstance(stamp, str)
            or datetime.fromisoformat(stamp).tzinfo is None
            or not re.fullmatch(r"[0-9a-f]{64}", str(acquisition.get("raw_sha256", "")))
        ):
            raise ValueError("Missing timestamped timeline acquisition evidence.")
        expected_periods = (
            4
            + (
                int(players[players.game_id == game.game_id].game_seconds.iloc[0])
                - 2880
            )
            // 300
        )
        if (
            item.get("rows") != len(frame)
            or item.get("periods") != expected_periods
            or item.get("status") not in ("cached", "fetched")
            or item.get("game_number") != game.game_number
            or item.get("game_seconds")
            != int(players[players.game_id == game.game_id].game_seconds.iloc[0])
            or not isinstance(item.get("raw_actions"), int)
            or item["raw_actions"] < len(frame) + 2 * expected_periods
        ):
            raise ValueError("Timeline row counts or period coverage are inconsistent.")
        result = results[results.game_id == game.game_id].iloc[0]
        expected_home = manifest.team_a if result.team_a_home else manifest.team_b
        expected_away = manifest.team_b if result.team_a_home else manifest.team_a
        expected_home_pts = int(
            result.team_a_points if result.team_a_home else result.team_b_points
        )
        expected_away_pts = int(
            result.team_b_points if result.team_a_home else result.team_a_points
        )
        if (
            item.get("home_team") != expected_home
            or item.get("away_team") != expected_away
            or item.get("final_home_score") != expected_home_pts
            or item.get("final_away_score") != expected_away_pts
            or item.get("substitutions")
            != int(frame.event_type.eq("Substitution").sum())
            or item.get("fouls") != int(frame.event_type.eq("Foul").sum())
        ):
            raise ValueError(
                "Timeline source summary does not reconcile with verified results."
            )
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)
    if report.get("rows") != len(combined):
        raise ValueError("Timeline series row count differs from its report.")
    return combined


def event_display(frame):
    display = frame.copy()
    display["Game"] = display.game_number.map(lambda g: f"Game {g}")
    display["Period"] = display.period.map(
        lambda p: f"Q{p}" if p <= 4 else f"OT{p - 4}"
    )
    display["Clock"] = display.remaining_seconds.map(
        lambda s: f"{int(s) // 60:02d}:{s % 60:05.2f}"
    )
    display["team"] = display.team.replace({"": "Unassigned"})
    return display.rename(
        columns={
            "team": "Team",
            "event_type": "Event",
            "subtype": "Subtype",
            "recorded_player": "Recorded player",
            "description": "Source description",
            "source_order": "Source row",
        }
    )[
        [
            "Game",
            "Period",
            "Clock",
            "Team",
            "Event",
            "Subtype",
            "Recorded player",
            "Source description",
            "Source row",
        ]
    ]
