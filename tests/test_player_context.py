"""Real traditional box scores and offline failure/identity semantics."""

import json
import shutil
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest
from requests import Timeout
from streamlit.testing.v1 import AppTest

from data_sources.player_boxscores import fetch_player_boxscore
from game_context import load_game_context
from player_context import (
    load_player_context,
    normalize_player_boxscore,
    player_context_display,
    validate_player_context,
)
from player_ingestion import ingest_player_context
from series_catalog import load_series
from series_manifest import load_manifest

ROOT = Path(__file__).resolve().parents[1]
SERIES = ["2026_okc_sas_api_20261005", "2025_okc_ind_api_20261005"]
FIXTURE = ROOT / "tests/fixtures/0042500311_traditional.json"


def case(series_id=SERIES[0]):
    manifest = load_manifest(ROOT / "series" / f"{series_id}.yml")
    return manifest, load_series(manifest, ROOT)[0], load_game_context(manifest, ROOT)


def payload():
    return json.loads(FIXTURE.read_text())


@pytest.mark.parametrize("series_id,rows", [(SERIES[0], 193), (SERIES[1], 203)])
def test_real_frozen_player_context(series_id, rows):
    manifest, matchups, _ = case(series_id)
    frame = load_player_context(manifest, ROOT)
    assert len(frame) == rows
    assert frame.game_id.nunique() == 7
    assert (
        not frame[~frame.played][["starter", "minutes_seconds", "points", "plus_minus"]]
        .notna()
        .any()
        .any()
    )
    report = json.loads(
        (ROOT / "data/player_context" / f"{series_id}.report.json").read_text()
    )
    assert len(report["games"]) == 7
    assert all(
        g["acquisition"]["fetched_at"] and g["acquisition"]["raw_sha256"]
        for g in report["games"]
    )
    name = "Victor Wembanyama" if series_id == SERIES[0] else "Tyrese Haliburton"
    team = "SAS" if series_id == SERIES[0] else "IND"
    display = player_context_display(frame, matchups, manifest, team, name)
    assert len(display) == 7
    assert display.iloc[0].PTS == (41 if team == "SAS" else 14)
    assert display.iloc[0].Minutes == ("48:42" if team == "SAS" else "38:55")


def test_raw_v3_normalization_and_dnp_not_zero_performance():
    manifest, _, _ = case()
    frame = normalize_player_boxscore(payload(), manifest.games[0], manifest)
    wemby = frame[frame.player_id == 1641705].iloc[0]
    assert wemby.points == 41 and wemby.minutes_seconds == 2922
    assert wemby.starter and wemby.game_seconds == 58 * 60
    dnp = frame[~frame.played]
    assert not dnp.empty
    assert dnp.comment.str.startswith("DNP").all()
    assert dnp.points.isna().all() and dnp.starter.isna().all()


@pytest.mark.parametrize(
    "change",
    ["game", "team", "columns", "minutes", "missing_minutes", "starter", "dnp_points"],
)
def test_invalid_raw_boxscores_rejected(change):
    manifest, _, _ = case()
    raw = payload()
    player = raw["boxScoreTraditional"]["homeTeam"]["players"][0]
    if change == "game":
        raw["boxScoreTraditional"]["gameId"] = "0042500312"
    elif change == "team":
        raw["boxScoreTraditional"]["homeTeam"]["teamTricode"] = "BOS"
    elif change == "columns":
        del player["statistics"]["points"]
    elif change == "minutes":
        player["statistics"]["minutes"] = "20:75"
    elif change == "missing_minutes":
        player["statistics"]["minutes"] = ""
    elif change == "starter":
        player["position"] = "PG"
    else:
        player["position"] = ""
        player["comment"] = "DNP - Coach's Decision"
        player["statistics"]["minutes"] = ""
    with pytest.raises(ValueError):
        normalize_player_boxscore(raw, manifest.games[0], manifest)


@pytest.mark.parametrize(
    "column,value",
    [
        ("points", 999),
        ("fga", -1),
        ("personal_fouls", 1.5),
        ("plus_minus", float("inf")),
        ("plus_minus", 100),
        ("minutes_seconds", 99999),
        ("minutes_seconds", 1),
        ("starter", False),
        ("game_date", "2026-05-17"),
        ("player_id", 999999999),
        ("played", "False"),
    ],
)
def test_processed_context_validation_rejects_changes(column, value):
    manifest, matchups, game_context = case()
    frame = load_player_context(manifest, ROOT).copy()
    frame[column] = frame[column].astype(object)
    frame.loc[0, column] = value
    with pytest.raises(ValueError):
        validate_player_context(frame, manifest, game_context, matchups)


def test_dnp_missing_identity_and_coverage_semantics():
    manifest, matchups, game_context = case()
    frame = load_player_context(manifest, ROOT)
    dnp_id = int(frame[~frame.played].iloc[0].player_id)
    name = "Fixture player"
    selection = matchups.iloc[[0]].copy()
    selection["off_player_id"] = dnp_id
    selection["off_team"] = frame[~frame.played].iloc[0].team
    selection["offense_player"] = name
    display = player_context_display(
        frame, selection, manifest, selection.iloc[0].off_team, name
    )
    assert "DNP" in display.iloc[0].Status and pd.isna(display.iloc[0].PTS)
    assert pd.isna(display.iloc[0].Starter)
    absent = frame[frame.player_id != dnp_id]
    display = player_context_display(
        absent, selection, manifest, selection.iloc[0].off_team, name
    )
    assert display.iloc[0].Status == "Not listed in box score"
    assert pd.isna(display.iloc[0].PTS)
    with pytest.raises(ValueError, match="coverage"):
        validate_player_context(
            frame[frame.game_number != 7], manifest, game_context, matchups
        )
    with pytest.raises(ValueError, match="Duplicate"):
        validate_player_context(
            pd.concat([frame, frame.iloc[[0]]]), manifest, game_context, matchups
        )


def test_player_selection_joins_by_id_not_boxscore_name():
    manifest, matchups, _ = case()
    frame = load_player_context(manifest, ROOT).copy()
    frame.loc[frame.player_id == 1641705, "player"] = "Different display spelling"
    assert (
        player_context_display(frame, matchups, manifest, "SAS", "Victor Wembanyama")
        .iloc[0]
        .PTS
        == 41
    )


def copied_root(tmp_path):
    for folder in ["snapshots", "context", "player_context"]:
        shutil.copytree(ROOT / "data" / folder, tmp_path / "data" / folder)
    return tmp_path


def test_loader_crlf_missing_and_modified_evidence(tmp_path):
    manifest, _, _ = case()
    assert load_player_context(manifest, tmp_path) is None
    copied_root(tmp_path)
    path = tmp_path / "data/player_context" / f"{manifest.series_id}.csv"
    original = path.read_bytes()
    path.write_bytes(original.replace(b"\n", b"\r\n"))
    assert len(load_player_context(manifest, tmp_path)) == 193
    path.write_bytes(original + b"\n")
    with pytest.raises(ValueError, match="integrity"):
        load_player_context(manifest, tmp_path)
    path.write_bytes(original)
    report = path.with_suffix(".report.json")
    evidence = json.loads(report.read_text())
    evidence["team_game_log_sha256"] = "wrong"
    report.write_text(json.dumps(evidence))
    with pytest.raises(ValueError, match="different team"):
        load_player_context(manifest, tmp_path)


@pytest.mark.parametrize("change", ["coverage", "rows", "timestamp", "endpoint"])
def test_loader_rejects_incomplete_provenance(tmp_path, change):
    manifest, _, _ = case()
    copied_root(tmp_path)
    path = tmp_path / "data/player_context" / f"{manifest.series_id}.report.json"
    report = json.loads(path.read_text())
    if change == "coverage":
        report["games"] = report["games"][:-1]
    elif change == "rows":
        report["rows"] = 1
    elif change == "timestamp":
        report["games"][0]["acquisition"]["fetched_at"] = None
    else:
        report["endpoint"] = "Unknown endpoint"
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError):
        load_player_context(manifest, tmp_path)


def ingestion_case(tmp_path, monkeypatch):
    manifest, matchups, game_context = case()
    one = replace(
        manifest,
        series_id="fixture_players",
        games=manifest.games[:1],
        series_complete=False,
    )
    for folder in ["snapshots", "context"]:
        path = tmp_path / "data" / folder / f"{one.series_id}.csv"
        path.parent.mkdir(parents=True)
        shutil.copy(ROOT / "data" / folder / f"{manifest.series_id}.csv", path)
    monkeypatch.setattr(
        "player_ingestion.load_series",
        lambda *_: (matchups[matchups.game == 1], None, None),
    )
    monkeypatch.setattr(
        "player_ingestion.load_game_context",
        lambda *_: game_context[game_context.game_number == 1],
    )
    return one


def test_live_boundary_cache_reuse_and_immutability(tmp_path, monkeypatch):
    manifest = ingestion_case(tmp_path, monkeypatch)
    calls = []

    def fetcher(game_id, **kwargs):
        calls.append((game_id, kwargs))
        return payload()

    report = ingest_player_context(
        manifest, tmp_path, fetcher=fetcher, request_interval=0
    )
    assert report["status"] == "complete" and len(calls) == 1
    assert report["games"][0]["status"] == "fetched"
    assert report["games"][0]["acquisition"]["fetched_at"]
    with pytest.raises(ValueError, match="cannot be overwritten"):
        ingest_player_context(manifest, tmp_path, fetcher=fetcher)
    second = replace(manifest, series_id="fixture_players_v2")
    for folder in ["snapshots", "context"]:
        shutil.copy(
            tmp_path / "data" / folder / f"{manifest.series_id}.csv",
            tmp_path / "data" / folder / f"{second.series_id}.csv",
        )
    assert (
        ingest_player_context(second, tmp_path, offline=True)["games"][0]["status"]
        == "cached"
    )
    assert len(calls) == 1


@pytest.mark.parametrize("failure", ["missing", "tampered", "metadata", "network"])
def test_failed_ingestion_never_publishes_partial_dataset(
    tmp_path, monkeypatch, failure
):
    manifest = ingestion_case(tmp_path, monkeypatch)
    raw = tmp_path / "data/raw/player_boxes/0042500311.json"
    if failure in ("tampered", "metadata"):
        raw.parent.mkdir(parents=True)
        raw.write_bytes(FIXTURE.read_bytes())
        if failure == "tampered":
            raw.with_suffix(".meta.json").write_text(
                json.dumps(
                    {
                        "game_id": "0042500311",
                        "endpoint": "NBA BoxScoreTraditionalV3",
                        "fetched_at": "2026-10-05T19:00:00+00:00",
                        "raw_sha256": "wrong",
                    }
                )
            )

    def failed(*args, **kwargs):
        raise RuntimeError("Fixture network outage")

    with pytest.raises(ValueError, match="ingestion failed"):
        ingest_player_context(
            manifest, tmp_path, offline=failure != "network", fetcher=failed
        )
    assert not (tmp_path / "data/player_context" / f"{manifest.series_id}.csv").exists()
    assert (
        json.loads(
            (
                tmp_path
                / "data/processed"
                / f"{manifest.series_id}.player_failure.json"
            ).read_text()
        )["status"]
        == "failed"
    )


def test_fetcher_bounded_retries_without_live_http(monkeypatch):
    module = ModuleType("nba_api.stats.endpoints.boxscoretraditionalv3")
    calls = []

    class Endpoint:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise Timeout("Fixture timeout")

        def get_dict(self):
            return payload()

    module.BoxScoreTraditionalV3 = Endpoint
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr("data_sources.player_boxscores.time.sleep", lambda *_: None)
    assert (
        fetch_player_boxscore("0042500311", timeout=3, retries=2)[
            "boxScoreTraditional"
        ]["gameId"]
        == "0042500311"
    )
    assert len(calls) == 2 and calls[0]["timeout"] == 3
    with pytest.raises(ValueError):
        fetch_player_boxscore("invalid")


def test_dashboard_player_and_transition_boxes():
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    assert not app.exception and not app.error
    assert any("player game box scores are not available" in i.value for i in app.info)
    app.sidebar.selectbox[2].set_value(SERIES[0]).run(timeout=30)
    tables = [d.value for d in app.dataframe if "Starter" in d.value.columns]
    assert len(tables) == 2 and len(tables[0]) == 7 and len(tables[1]) == 2
    assert tables[0].iloc[0].PTS == 41
    player = app.selectbox(key=f"player_{SERIES[0]}")
    player.set_value("OKC|Shai Gilgeous-Alexander").run(timeout=30)
    tables = [d.value for d in app.dataframe if "Starter" in d.value.columns]
    assert tables[0].iloc[0].PTS == 24
    app.selectbox(key=f"transition_{SERIES[0]}_OKC|Shai Gilgeous-Alexander").set_value(
        "Game 2 → Game 3"
    ).run(timeout=30)
    tables = [d.value for d in app.dataframe if "Starter" in d.value.columns]
    assert tables[1].Game.tolist() == ["Game 2", "Game 3"]
    assert not app.exception and not app.error
