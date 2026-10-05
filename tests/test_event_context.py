"""Clock, provenance and event observation tests; no live NBA dependency."""

import json
import shutil
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest
from requests import Timeout
from streamlit.testing.v1 import AppTest

from data_sources.play_by_play import fetch_play_by_play
from event_context import (
    clock_seconds,
    event_display,
    load_event_context,
    normalize_events,
    validate_event_frame,
)
from event_ingestion import ingest_event_context
from game_context import load_game_context
from player_context import load_player_context
from series_manifest import load_manifest
from visualizations.event_timeline import make_event_timeline

ROOT = Path(__file__).resolve().parents[1]
SERIES = ["2026_okc_sas_api_20261005", "2025_okc_ind_api_20261005"]
FIXTURE = ROOT / "tests/fixtures/0042500311_event_excerpt.json"


def case():
    m = load_manifest(ROOT / "series" / f"{SERIES[0]}.yml")
    return m, load_game_context(m, ROOT), load_player_context(m, ROOT)


def payload():
    return json.loads(FIXTURE.read_text())


@pytest.mark.parametrize("series_id,rows", [(SERIES[0], 842), (SERIES[1], 826)])
def test_real_frozen_event_coverage(series_id, rows):
    m = load_manifest(ROOT / "series" / f"{series_id}.yml")
    frame = load_event_context(m, ROOT)
    assert len(frame) == rows and frame.game_id.nunique() == 7
    assert set(frame.event_type) == {"Substitution", "Foul"}
    for _, events in frame.groupby("game_id"):
        assert events.elapsed_seconds.is_monotonic_increasing
        assert events.source_order.is_unique and events.action_id.is_unique
    unidentified = frame[frame.team == ""]
    assert len(unidentified) == (2 if series_id == SERIES[0] else 1)
    assert unidentified.subtype.eq("Technical").all()


@pytest.mark.parametrize(
    "clock,period,remaining,elapsed",
    [
        ("PT12M00.00S", 1, 720, 0),
        ("PT00M00.00S", 4, 0, 2880),
        ("PT05M00.00S", 5, 300, 2880),
        ("PT05M00.00S", 6, 300, 3180),
        ("PT00M00.00S", 6, 0, 3480),
        ("PT00M21.50S", 3, 21.5, 2138.5),
    ],
)
def test_regulation_overtime_fractional_clock(clock, period, remaining, elapsed):
    assert clock_seconds(clock, period) == (remaining, elapsed)


@pytest.mark.parametrize(
    "clock,period",
    [
        ("12:00", 1),
        ("PT00M61S", 1),
        ("PT13M00S", 1),
        ("PT06M00S", 5),
        ("PT-1M00S", 1),
        ("PT12M00S", 0),
    ],
)
def test_invalid_clock_rejected(clock, period):
    with pytest.raises(ValueError):
        clock_seconds(clock, period)


def test_excerpt_preserves_description_identity_and_source_order():
    m, results, players = case()
    frame, summary = normalize_events(payload(), m.games[0], m, results, players)
    assert len(frame) == 128 and summary["periods"] == 6
    sub = frame[frame.event_type == "Substitution"].iloc[0]
    assert sub.person_id == 1628392 and sub.recorded_player == "Isaiah Hartenstein"
    assert sub.description == "SUB: Caruso FOR Hartenstein"
    assert not any("incoming" in c for c in frame.columns)
    same_clock = frame[(frame.period == 1) & (frame.clock == "PT04M18.00S")]
    assert same_clock.source_order.is_monotonic_increasing
    display = event_display(frame)
    assert display.Period.str.startswith("OT").any()
    assert "Source description" in display and "Source row" in display


def test_duplicate_action_numbers_do_not_merge_distinct_source_rows():
    m, results, players = case()
    raw = payload()
    events = [a for a in raw["game"]["actions"] if a["actionType"] == "Substitution"]
    events[1]["actionNumber"] = events[0]["actionNumber"]
    frame, summary = normalize_events(raw, m.games[0], m, results, players)
    assert len(frame) == 128 and summary["duplicate_action_numbers"] > 0
    assert frame.source_order.is_unique


@pytest.mark.parametrize(
    "change",
    [
        "game",
        "period",
        "clock",
        "final_score",
        "boundary",
        "sub_identity",
        "foul_identity",
        "description",
    ],
)
def test_invalid_source_event_or_coverage_rejected(change):
    m, results, players = case()
    raw = payload()
    actions = raw["game"]["actions"]
    sub = next(a for a in actions if a["actionType"] == "Substitution")
    foul = next(a for a in actions if a["actionType"] == "Foul")
    if change == "game":
        raw["game"]["gameId"] = "0042500312"
    elif change == "period":
        sub["period"] = 7
    elif change == "clock":
        sub["clock"] = "PT13M00S"
    elif change == "final_score":
        actions[-1]["scoreAway"] = "121"
    elif change == "boundary":
        raw["game"]["actions"] = actions[:-1]
    elif change == "sub_identity":
        sub["personId"] = 999999999
    elif change == "foul_identity":
        foul["personId"] = 999999999
    else:
        sub["description"] = ""
    with pytest.raises(ValueError):
        normalize_events(raw, m.games[0], m, results, players)


def test_frame_validation_and_chart_use_elapsed_clock():
    m, results, players = case()
    frame, _ = normalize_events(payload(), m.games[0], m, results, players)
    changed = frame.copy()
    changed.loc[0, "elapsed_seconds"] += 1
    with pytest.raises(ValueError, match="source clock"):
        validate_event_frame(changed, m.games[0], m, players)
    chart = make_event_timeline(frame, 3480, 1628392)
    assert chart.layout.xaxis.range == (0, 58)
    assert sum(len(trace.x) for trace in chart.data) == 128
    assert any(14 in trace.marker.size for trace in chart.data)
    assert make_event_timeline(frame.iloc[0:0], 3480).data == ()


def copy_root(tmp_path):
    for folder in ["snapshots", "context", "player_context", "event_context"]:
        shutil.copytree(ROOT / "data" / folder, tmp_path / "data" / folder)


def test_missing_crlf_and_modified_timeline(tmp_path):
    m, _, _ = case()
    assert load_event_context(m, tmp_path) is None
    copy_root(tmp_path)
    path = tmp_path / "data/event_context" / m.series_id / "0042500311.csv"
    original = path.read_bytes()
    path.write_bytes(original.replace(b"\n", b"\r\n"))
    assert len(load_event_context(m, tmp_path)) == 842
    path.write_bytes(original + b"\n")
    with pytest.raises(ValueError, match="hash differs"):
        load_event_context(m, tmp_path)


@pytest.mark.parametrize(
    "change", ["coverage", "score", "rows", "acquisition", "dependency"]
)
def test_loader_rejects_changed_provenance(tmp_path, change):
    m, _, _ = case()
    copy_root(tmp_path)
    path = tmp_path / "data/event_context" / m.series_id / "report.json"
    report = json.loads(path.read_text())
    if change == "coverage":
        report["games"] = report["games"][:-1]
    elif change == "score":
        report["games"][0]["final_away_score"] = 121
    elif change == "rows":
        report["rows"] = 1
    elif change == "acquisition":
        report["games"][0]["acquisition"]["fetched_at"] = None
    else:
        report["player_dataset_sha256"] = "wrong"
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError):
        load_event_context(m, tmp_path)


def ingestion_case(tmp_path, monkeypatch):
    m, results, players = case()
    one = replace(
        m, series_id="fixture_events", games=m.games[:1], series_complete=False
    )
    for folder in ["context", "player_context"]:
        target = tmp_path / "data" / folder / f"{one.series_id}.csv"
        target.parent.mkdir(parents=True)
        shutil.copy(ROOT / "data" / folder / f"{m.series_id}.csv", target)
    monkeypatch.setattr("event_ingestion.load_player_context", lambda *_: players)
    monkeypatch.setattr("event_ingestion.load_game_context", lambda *_: results)
    return one


def test_live_boundary_cache_reuse_and_atomic_immutability(tmp_path, monkeypatch):
    m = ingestion_case(tmp_path, monkeypatch)
    calls = []

    def fetcher(game_id, **kwargs):
        calls.append(game_id)
        return payload()

    report = ingest_event_context(m, tmp_path, fetcher=fetcher, request_interval=0)
    assert report["status"] == "complete" and calls == ["0042500311"]
    output = tmp_path / "data/event_context" / m.series_id
    assert (output / "report.json").exists() and (output / "0042500311.csv").exists()
    with pytest.raises(ValueError, match="cannot be overwritten"):
        ingest_event_context(m, tmp_path, fetcher=fetcher)
    second = replace(m, series_id="fixture_events_v2")
    for folder in ["context", "player_context"]:
        shutil.copy(
            tmp_path / "data" / folder / f"{m.series_id}.csv",
            tmp_path / "data" / folder / f"{second.series_id}.csv",
        )
    assert (
        ingest_event_context(second, tmp_path, offline=True)["games"][0]["status"]
        == "cached"
    )
    assert len(calls) == 1


@pytest.mark.parametrize("failure", ["missing", "evidence", "score", "network"])
def test_failure_never_publishes_partial_event_folder(tmp_path, monkeypatch, failure):
    m = ingestion_case(tmp_path, monkeypatch)
    raw = tmp_path / "data/raw/play_by_play/0042500311.json"
    if failure == "evidence":
        raw.parent.mkdir(parents=True)
        raw.write_bytes(FIXTURE.read_bytes())

    def fetcher(*args, **kwargs):
        if failure == "network":
            raise RuntimeError("Fixture NBA outage")
        raw = payload()
        raw["game"]["actions"][-1]["scoreAway"] = "121"
        return raw

    with pytest.raises(ValueError, match="ingestion failed"):
        ingest_event_context(
            m, tmp_path, offline=failure in ("missing", "evidence"), fetcher=fetcher
        )
    assert not (tmp_path / "data/event_context" / m.series_id).exists()
    assert (
        json.loads(
            (
                tmp_path / "data/processed" / f"{m.series_id}.event_failure.json"
            ).read_text()
        )["status"]
        == "failed"
    )
    assert not list((tmp_path / "data/processed").glob("event-stage-*"))


def test_fetcher_bounded_retries_without_http(monkeypatch):
    module = ModuleType("nba_api.stats.endpoints.playbyplayv3")
    calls = []

    class Endpoint:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise Timeout("Fixture timeout")

        def get_dict(self):
            return payload()

    module.PlayByPlayV3 = Endpoint
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr("data_sources.play_by_play.time.sleep", lambda *_: None)
    assert (
        fetch_play_by_play("0042500311", timeout=3, retries=2)["game"]["gameId"]
        == "0042500311"
    )
    assert len(calls) == 2
    with pytest.raises(ValueError):
        fetch_play_by_play("invalid")


def test_dashboard_timeline_game_team_types_and_transition():
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    assert not app.exception and not app.error
    assert any("event timelines are not available" in i.value for i in app.info)
    app.sidebar.selectbox[2].set_value(SERIES[0]).run(timeout=30)
    transition = app.selectbox(key=f"transition_{SERIES[0]}_SAS|Victor Wembanyama")
    transition.set_value("Game 1 → Game 2").run(timeout=30)
    prefix = f"events_{SERIES[0]}_SAS|Victor Wembanyama_1_2"
    app.selectbox(key=f"{prefix}_game").set_value(1).run(timeout=30)
    tables = [d.value for d in app.dataframe if "Source row" in d.value.columns]
    assert (
        len(tables) == 1
        and len(tables[0]) == 128
        and tables[0].Period.str.startswith("OT").any()
    )
    app.selectbox(key=f"{prefix}_team").set_value("OKC").run(timeout=30)
    app.multiselect(key=f"{prefix}_types").set_value(["Foul"]).run(timeout=30)
    table = next(d.value for d in app.dataframe if "Source row" in d.value.columns)
    assert table.Team.eq("OKC").all() and table.Event.eq("Foul").all()
    app.multiselect(key=f"{prefix}_types").set_value([]).run(timeout=30)
    assert any("No events match" in i.value for i in app.info)
    assert not app.exception and not app.error
