"""ID-joined opponent roster context for an observed matchup redistribution."""

import math

import pandas as pd

from player_context import integer


def compare_defensive_personnel(
    matchups, players, manifest, offense_team, offense_player, from_game, to_game
):
    """Use verified snapshot frames; retain missing box statistics and source status.

    Matchup share uses recorded matchup seconds, not full-game playing minutes.
    This is a roster comparison, not simultaneous five-player lineup evidence.
    """
    if manifest.source_csv or players is None:
        raise ValueError("Personnel comparison requires verified API player context.")
    if offense_team not in (manifest.team_a, manifest.team_b):
        raise ValueError("Offensive team is not in this series.")
    from_game = integer(from_game, "from game")
    to_game = integer(to_game, "to game")
    games = {game.game_number: game for game in manifest.games}
    if from_game not in games or to_game not in games or from_game >= to_game:
        raise ValueError("Choose two chronological games from the manifest.")
    required_matchups = {
        "game",
        "game_id",
        "off_team",
        "offense_player",
        "off_player_id",
        "def_team",
        "defense_player",
        "def_player_id",
        "matchup_seconds",
    }
    required_players = {
        "game_id",
        "game_number",
        "team",
        "player_id",
        "player",
        "played",
        "starter",
        "comment",
        "minutes_seconds",
        "personal_fouls",
        "game_seconds",
    }
    if required_matchups - set(matchups.columns) or required_players - set(
        players.columns
    ):
        raise ValueError("Personnel comparison inputs are missing required columns.")
    identity = (
        matchups[
            matchups.off_team.eq(offense_team)
            & matchups.offense_player.eq(offense_player)
        ]
        .off_player_id.dropna()
        .unique()
    )
    if len(identity) != 1 or integer(identity[0], "offensive player ID") <= 0:
        raise ValueError("Selected offensive player has no unique NBA identity.")
    opponent = manifest.team_b if offense_team == manifest.team_a else manifest.team_a
    selected = matchups[
        matchups.off_team.eq(offense_team)
        & matchups.off_player_id.eq(identity[0])
        & matchups.game.isin([from_game, to_game])
    ].copy()
    if not selected.def_team.eq(opponent).all():
        raise ValueError("Selected matchup has an unexpected defending team.")
    game_ids = [games[number].game_id for number in (from_game, to_game)]
    roster = players[players.team.eq(opponent) & players.game_id.isin(game_ids)].copy()
    if set(roster.game_id) != set(game_ids):
        raise ValueError("Defending roster is missing a transition game.")
    if roster.duplicated(["game_id", "player_id"]).any():
        raise ValueError("Defending roster contains duplicate NBA identities.")
    for player_id in roster.player_id:
        if integer(player_id, "defensive player ID") <= 0:
            raise ValueError("Defensive player ID must be positive.")
    totals, assignments = {}, {}
    for number, game_id in zip((from_game, to_game), game_ids):
        rows = selected[selected.game == number]
        box = roster[roster.game_id == game_id].set_index("player_id")
        if not box.game_number.eq(number).all() or not rows.game_id.eq(game_id).all():
            raise ValueError("Personnel comparison game identities disagree.")
        for row in rows.itertuples():
            person = integer(row.def_player_id, "matchup defender ID")
            if person not in box.index:
                raise ValueError(
                    "Matchup defender does not match that game's NBA roster."
                )
            seconds = float(row.matchup_seconds)
            if not math.isfinite(seconds) or seconds < 0:
                raise ValueError(
                    "Recorded matchup seconds must be finite and nonnegative."
                )
            if seconds > 0 and not box.loc[person, "played"]:
                raise ValueError("Recorded matchup time contradicts non-participation.")
        assignments[number] = (
            rows.groupby("def_player_id").matchup_seconds.sum().to_dict()
        )
        totals[number] = sum(assignments[number].values())
    records = []
    for player_id in sorted(roster.player_id.unique()):
        person = roster[roster.player_id == player_id].sort_values("game_number")
        record = {
            "team": opponent,
            "player_id": int(player_id),
            "player": person.iloc[-1].player,
        }
        for prefix, number, game_id in zip(
            ("from", "to"), (from_game, to_game), game_ids
        ):
            rows = person[person.game_id == game_id]
            row = rows.iloc[0] if len(rows) else None
            played = row is not None and bool(row.played)
            if (
                row is not None
                and not played
                and (pd.isna(row.comment) or not str(row.comment).strip())
            ):
                raise ValueError("Non-participation is missing its source status.")
            seconds = float(assignments[number].get(player_id, 0))
            record.update(
                {
                    f"{prefix}_status": "Played"
                    if played
                    else str(row.comment)
                    if row is not None
                    else "Not listed in box score",
                    f"{prefix}_starter": bool(row.starter) if played else None,
                    f"{prefix}_minutes": float(row.minutes_seconds) / 60
                    if played
                    else None,
                    f"{prefix}_fouls": int(row.personal_fouls) if played else None,
                    f"{prefix}_matchup_minutes": seconds / 60,
                    f"{prefix}_share": seconds / totals[number] * 100
                    if totals[number] > 0
                    else None,
                }
            )
        record["minutes_change"] = (
            record["to_minutes"] - record["from_minutes"]
            if record["to_minutes"] is not None and record["from_minutes"] is not None
            else None
        )
        record["share_change"] = (
            record["to_share"] - record["from_share"]
            if record["to_share"] is not None and record["from_share"] is not None
            else None
        )
        records.append(record)
    result = pd.DataFrame(records)
    for column in [
        f"{prefix}_{field}"
        for prefix in ("from", "to")
        for field in ("minutes", "fouls", "matchup_minutes", "share")
    ] + ["minutes_change", "share_change"]:
        result[column] = result[column].astype(float)
    result["_order"] = result.share_change.abs()
    return (
        result.sort_values(
            ["_order", "player_id"], ascending=[False, True], na_position="last"
        )
        .drop(columns="_order")
        .reset_index(drop=True)
    )


def personnel_display(frame, from_game, to_game):
    """Friendly transition columns; no zero-filled non-participant box statistics."""
    result = pd.DataFrame({"Defender": frame.player})
    for prefix, game in (("from", from_game), ("to", to_game)):
        label = f"Game {game}"
        result[f"{label} status"] = frame[f"{prefix}_status"]
        result[f"{label} starter"] = frame[f"{prefix}_starter"].map(
            lambda value: "Yes" if value is True else "No" if value is False else None
        )
        result[f"{label} full-game min"] = frame[f"{prefix}_minutes"].round(2)
        result[f"{label} personal fouls"] = frame[f"{prefix}_fouls"].astype("Int64")
        result[f"{label} matchup min"] = frame[f"{prefix}_matchup_minutes"].round(2)
        result[f"{label} matchup share %"] = frame[f"{prefix}_share"].round(1)
    result["Full-game min change"] = frame.minutes_change.round(2)
    result["Matchup share change (pp)"] = frame.share_change.round(1)
    return result
