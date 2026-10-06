"""Game-result validation, team perspective, provenance and dashboard interactions."""

import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from game_context import build_game_context, context_for_team, load_game_context
from series_manifest import load_manifest, save_manifest

ROOT = Path(__file__).resolve().parents[1]
SERIES = ["2026_okc_sas_api_20261005", "2025_okc_ind_api_20261005"]


def source(series_id=SERIES[0]):
    manifest = load_manifest(ROOT / "series" / f"{series_id}.yml")
    frame = pd.read_csv(
        ROOT / "data/context" / f"{series_id}.csv",
        dtype={"GAME_ID": str, "SEASON_ID": str},
    )
    return manifest, frame


@pytest.mark.parametrize(
    "series_id,final_record", [(SERIES[0], "3–4"), (SERIES[1], "4–3")]
)
def test_published_context_and_team_perspective(series_id, final_record):
    manifest, _ = source(series_id)
    context = load_game_context(manifest, ROOT)
    assert len(context) == 7
    a = context_for_team(context, manifest, manifest.team_a)
    b = context_for_team(context, manifest, manifest.team_b)
    assert a.iloc[0]["Series before"] == "0–0"
    assert a.iloc[-1]["Series after"] == final_record
    assert a["Margin"].equals(-b["Margin"])
    assert (a.Venue != b.Venue).all()
    assert (a.Result != b.Result).all()
    assert a["Series before"].iloc[1:].tolist() == a["Series after"].iloc[:-1].tolist()
    with pytest.raises(ValueError, match="belong"):
        context_for_team(context, manifest, "BOS")


def test_real_game_one_score_is_not_summed_matchup_points():
    manifest, frame = source()
    context = build_game_context(frame, manifest)
    assert context.iloc[0].team_a_points == 115
    assert context.iloc[0].team_b_points == 122
    assert context.iloc[0].team_a_home
    sas = context_for_team(context, manifest, "SAS")
    assert sas.iloc[0].Score == "SAS 122 – OKC 115"
    assert sas.iloc[0]["Series after"] == "1–0"


@pytest.mark.parametrize(
    "column,value",
    [
        ("PTS", -1),
        ("PTS", 100.5),
        ("PTS", float("nan")),
        ("PLUS_MINUS", float("inf")),
        ("PLUS_MINUS", 0),
        ("PLUS_MINUS", 1000),
        ("WL", "W"),
    ],
)
def test_invalid_scores_or_results_rejected(column, value):
    manifest, frame = source()
    frame[column] = frame[column].astype(object)
    frame.loc[0, column] = value
    with pytest.raises(ValueError):
        build_game_context(frame, manifest)


def test_conflicting_rows_and_manifest_coverage_rejected():
    manifest, frame = source()
    duplicate = frame.iloc[[0]].copy()
    duplicate.PTS += 1
    with pytest.raises(ValueError, match="Conflicting"):
        build_game_context(pd.concat([frame, duplicate]), manifest)
    with pytest.raises(ValueError):
        build_game_context(frame.iloc[1:], manifest)
    changed = replace(
        manifest,
        games=(replace(manifest.games[0], game_date="2026-05-17"),)
        + manifest.games[1:],
    )
    with pytest.raises(ValueError, match="dates differ"):
        build_game_context(frame, changed)
    with pytest.raises(ValueError, match="requires PTS"):
        build_game_context(frame.drop(columns="PTS"), manifest)


def test_missing_tampered_and_crlf_context(tmp_path):
    manifest, _ = source()
    assert load_game_context(manifest, tmp_path) is None
    target = tmp_path / "data/context" / f"{manifest.series_id}.csv"
    target.parent.mkdir(parents=True)
    original = ROOT / "data/context" / target.name
    target.write_bytes(original.read_bytes().replace(b"\n", b"\r\n"))
    with pytest.raises(ValueError, match="missing its source"):
        load_game_context(manifest, tmp_path)
    report = tmp_path / "data/snapshots" / f"{manifest.series_id}.report.json"
    report.parent.mkdir(parents=True)
    shutil.copy(ROOT / "data/snapshots" / report.name, report)
    assert len(load_game_context(manifest, tmp_path)) == 7
    target.write_bytes(target.read_bytes().replace(b",103,", b",104,", 1))
    with pytest.raises(ValueError, match="hash differs"):
        load_game_context(manifest, tmp_path)


def test_publication_cli_checks_evidence_before_writing(tmp_path):
    manifest, _ = source()
    manifest_path = tmp_path / "series.yml"
    save_manifest(manifest, manifest_path)
    report = tmp_path / "data/snapshots" / f"{manifest.series_id}.report.json"
    report.parent.mkdir(parents=True)
    shutil.copy(ROOT / "data/snapshots" / report.name, report)
    log = tmp_path / "log.csv"
    shutil.copy(ROOT / "data/context" / f"{manifest.series_id}.csv", log)
    cmd = [
        sys.executable,
        "-m",
        "scripts.publish_game_context",
        "--manifest",
        str(manifest_path),
        "--game-log-csv",
        str(log),
        "--project-root",
        str(tmp_path),
    ]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    target = tmp_path / "data/context" / f"{manifest.series_id}.csv"
    before = target.read_bytes()
    evidence = json.loads(report.read_text())
    evidence["discovery_sha256"] = "invalid"
    report.write_text(json.dumps(evidence))
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 1 and "hash differs" in result.stderr
    assert target.read_bytes() == before


def test_dashboard_context_follows_player_team_and_transition():
    app = AppTest.from_file(str(ROOT / "app_v1.py")).run(timeout=30)
    assert not app.exception and not app.error
    assert any("context is not available" in item.value for item in app.info)
    app.sidebar.selectbox[2].set_value(SERIES[0]).run(timeout=30)
    assert not app.exception and not app.error
    tables = [d.value for d in app.dataframe if "Series before" in d.value.columns]
    assert len(tables) == 2 and len(tables[0]) == 7 and len(tables[1]) == 2
    assert tables[0].iloc[0].Score == "SAS 122 – OKC 115"
    player = app.selectbox(key=f"player_{SERIES[0]}")
    player.set_value("OKC|Shai Gilgeous-Alexander").run(timeout=30)
    tables = [d.value for d in app.dataframe if "Series before" in d.value.columns]
    assert tables[0].iloc[0].Score == "OKC 115 – SAS 122"
    transition = app.selectbox(
        key=f"transition_{SERIES[0]}_OKC|Shai Gilgeous-Alexander"
    )
    transition.set_value("Game 2 → Game 3").run(timeout=30)
    tables = [d.value for d in app.dataframe if "Series before" in d.value.columns]
    assert tables[1].Game.tolist() == ["Game 2", "Game 3"]
    assert not app.exception and not app.error
