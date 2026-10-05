"""Strict, portable series configurations. Paths are relative to the project root."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
import re

import yaml


@dataclass(frozen=True)
class Game:
    game_number: int
    game_id: str | None = None
    game_date: str | None = None


@dataclass(frozen=True)
class SeriesManifest:
    series_id: str
    season: str
    season_type: str
    playoff_round: str
    team_a: str
    team_b: str
    games: tuple[Game, ...]
    series_complete: bool = False
    source_csv: str | None = None
    default_player: str | None = None
    notes: str = ""

    @property
    def label(self):
        return f"{self.team_a} vs {self.team_b}"

    def to_dict(self):
        result = asdict(self)
        result["games"] = [asdict(game) for game in self.games]
        return result


def manifest_from_dict(data):
    if not isinstance(data, dict):
        raise ValueError("Manifest must be a YAML mapping.")
    required = {
        "series_id",
        "season",
        "season_type",
        "playoff_round",
        "team_a",
        "team_b",
        "games",
    }
    unknown = set(data) - set(SeriesManifest.__dataclass_fields__)
    if required - set(data) or unknown:
        raise ValueError(
            f"Manifest fields: missing {sorted(required - set(data))}; unknown {sorted(unknown)}"
        )
    for key in required - {"games"}:
        if not isinstance(data[key], str) or not data[key].strip():
            raise ValueError(f"{key} must be a non-empty string.")
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", data["series_id"]):
        raise ValueError(
            "series_id must contain only letters, numbers, underscores or hyphens."
        )
    season = data["season"]
    if (
        not re.fullmatch(r"\d{4}-\d{2}", season)
        or int(season[-2:]) != (int(season[:4]) + 1) % 100
    ):
        raise ValueError("season must use YYYY-YY, e.g. 2025-26.")
    if data["season_type"] != "Playoffs":
        raise ValueError("Only Playoffs series are supported in V1.")
    for team in (data["team_a"], data["team_b"]):
        if not re.fullmatch(r"[A-Z]{3}", team):
            raise ValueError("Teams must be uppercase three-letter codes.")
    if data["team_a"] == data["team_b"]:
        raise ValueError("Series teams must differ.")
    if not isinstance(data.get("series_complete", False), bool):
        raise ValueError("series_complete must be true or false.")
    for key in ("source_csv", "default_player", "notes"):
        if data.get(key) is not None and not isinstance(data[key], str):
            raise ValueError(f"{key} must be a string.")
    raw_games = data["games"]
    if not isinstance(raw_games, list) or not 1 <= len(raw_games) <= 7:
        raise ValueError("games must list one to seven games.")
    games = []
    for raw in raw_games:
        if not isinstance(raw, dict) or set(raw) - {
            "game_number",
            "game_id",
            "game_date",
        }:
            raise ValueError("Invalid game fields.")
        number = raw.get("game_number")
        if (
            isinstance(number, bool)
            or not isinstance(number, int)
            or not 1 <= number <= 7
        ):
            raise ValueError("game_number must be an integer from 1 to 7.")
        game_id = raw.get("game_id")
        if game_id is not None:
            if not isinstance(game_id, str) or not re.fullmatch(r"004\d{7}", game_id):
                raise ValueError(
                    "game_id must be a quoted 10-digit NBA playoff game ID."
                )
            if int(game_id[-1]) != number:
                raise ValueError("game_id suffix does not match game_number.")
            if game_id[3:5] != season[2:4]:
                raise ValueError("game_id season does not match manifest season.")
        day = raw.get("game_date")
        if day is not None:
            day = str(day)
            try:
                if date.fromisoformat(day).isoformat() != day:
                    raise ValueError()
            except ValueError as exc:
                raise ValueError("game_date must be YYYY-MM-DD.") from exc
        games.append(Game(number, game_id, day))
    if [g.game_number for g in games] != list(range(1, len(games) + 1)):
        raise ValueError(
            "games must be ordered and numbered consecutively starting at 1."
        )
    ids = [g.game_id for g in games if g.game_id]
    if ids and len({game_id[:-1] for game_id in ids}) != 1:
        raise ValueError("Manifest mixes different playoff series IDs.")
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate game IDs in manifest.")
    dates = [g.game_date for g in games if g.game_date]
    if dates != sorted(dates) or len(set(dates)) != len(dates):
        raise ValueError("Game dates must be unique and chronological.")
    if not data.get("source_csv") and len(ids) != len(games):
        raise ValueError("API manifests require a game_id for every game.")
    if data.get("source_csv") and (
        Path(data["source_csv"]).is_absolute() or ".." in Path(data["source_csv"]).parts
    ):
        raise ValueError("source_csv must be a project-relative path without '..'.")
    kwargs = {k: v for k, v in data.items() if k != "games"}
    return SeriesManifest(**kwargs, games=tuple(games))


def load_manifest(path):
    with Path(path).open(encoding="utf-8") as handle:
        try:
            data = yaml.safe_load(handle)
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML manifest: {exc}") from exc
        return manifest_from_dict(data)


def save_manifest(manifest, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(manifest.to_dict(), sort_keys=False), encoding="utf-8"
    )
