"""Cross-round real-series coverage and dashboard navigation, entirely offline."""

import json
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from event_context import load_event_context
from game_context import load_game_context
from player_context import load_player_context
from series_catalog import list_series, load_series
from series_manifest import load_manifest

ROOT = Path(__file__).resolve().parents[1]
NEW_SERIES = [
    ("2026_nyk_sas_api_20261005", 5),
    ("2026_cle_nyk_api_20261005", 4),
    ("2026_min_sas_api_20261005", 6),
    ("2026_lal_okc_api_20261005", 4),
    ("2026_den_min_api_20261005", 6),
]


@pytest.mark.parametrize("series_id,game_count", NEW_SERIES)
@pytest.mark.parametrize("windows_endings", [False, True])
def test_expanded_series_complete_context_chain(
    tmp_path, series_id, game_count, windows_endings
):
    manifest = load_manifest(ROOT / "series" / f"{series_id}.yml")
    root = ROOT
    if windows_endings:
        root = tmp_path
        relatives = [
            Path("data/snapshots") / f"{series_id}{suffix}"
            for suffix in (".csv", ".report.json")
        ] + [
            Path("data/context") / f"{series_id}.csv",
            Path("data/player_context") / f"{series_id}.csv",
            Path("data/player_context") / f"{series_id}.report.json",
        ]
        relatives += [
            path.relative_to(ROOT)
            for path in (ROOT / "data/event_context" / series_id).iterdir()
        ]
        for relative in relatives:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
            target.write_bytes(target.read_bytes().replace(b"\n", b"\r\n"))
    matchups, quality, provenance = load_series(manifest, root)
    results = load_game_context(manifest, root)
    players = load_player_context(manifest, root)
    events = load_event_context(manifest, root)
    expected_ids = {game.game_id for game in manifest.games}
    assert len(expected_ids) == game_count and manifest.series_complete
    assert set(matchups.game) == set(range(1, game_count + 1))
    assert not quality["errors"] and provenance["coverage_complete"]
    assert provenance["source_verification"] == "approved_separate_snapshot"
    assert provenance["manual_parity"] == "fail"
    assert len(results) == game_count
    assert set(players.game_id) == expected_ids
    assert set(events.game_id) == expected_ids
    assert set(players.team) == {manifest.team_a, manifest.team_b}
    assert set(events.event_type) == {"Substitution", "Foul"}
    for _, group in events.groupby("game_id"):
        assert group.elapsed_seconds.is_monotonic_increasing
        assert group.source_order.is_unique
    reports = [
        provenance,
        json.loads(
            (root / "data/player_context" / f"{series_id}.report.json").read_text()
        ),
        json.loads(
            (root / "data/event_context" / series_id / "report.json").read_text()
        ),
    ]
    from series_ingestion import sha256

    assert reports[1]["normalizer_sha256"] == sha256(ROOT / "player_context.py")
    for report in reports:
        assert report["status"] == "complete"
        assert len(report["games"]) == game_count
        assert all(
            game["acquisition"]["fetched_at"] and game["acquisition"]["raw_sha256"]
            for game in report["games"]
        )


def test_dashboard_switches_all_new_rounds_and_shared_round_series():
    catalog, errors = list_series(ROOT)
    assert not errors
    by_id = {manifest.series_id: manifest for _, manifest in catalog}
    app = AppTest.from_file(str(ROOT / "app_v1.py")).run(timeout=30)
    assert not app.exception and not app.error
    assert app.sidebar.selectbox[2].value == "2026_okc_sas_sample"
    for series_id, game_count in NEW_SERIES:
        manifest = by_id[series_id]
        app.sidebar.selectbox[1].set_value(manifest.playoff_round).run(timeout=30)
        app.sidebar.selectbox[2].set_value(series_id).run(timeout=30)
        assert not app.exception and not app.error
        assert app.selectbox(key=f"player_{series_id}").value
        assert any(metric.label == "Largest Adjustment" for metric in app.metric)
        result_tables = [
            frame.value
            for frame in app.dataframe
            if "Series before" in frame.value.columns
        ]
        assert len(result_tables[0]) == game_count
        assert any("Source row" in frame.value.columns for frame in app.dataframe)
    app.sidebar.selectbox[0].set_value("2024-25").run(timeout=30)
    assert app.sidebar.selectbox[2].value == "2025_okc_ind_api_20261005"
    app.sidebar.selectbox[0].set_value("2025-26").run(timeout=30)
    assert app.sidebar.selectbox[2].value == "2026_okc_sas_sample"
    assert not app.exception and not app.error


@pytest.mark.parametrize("value,expected", [("2:60", 180), ("2:59.5", 179.5)])
def test_nba_minutes_seconds_carry(value, expected):
    from player_context import minutes_seconds

    assert minutes_seconds(value) == expected


@pytest.mark.parametrize("value", ["2:61", "2:60.1", "2:99", "-2:60", "2:6", None])
def test_nba_minutes_still_reject_invalid_seconds(value):
    from player_context import minutes_seconds

    with pytest.raises(ValueError, match="Invalid box-score minutes"):
        minutes_seconds(value)


def test_finals_source_minute_carry_preserves_real_player_participation():
    from player_context import load_player_context

    manifest = load_manifest(ROOT / "series/2026_nyk_sas_api_20261005.yml")
    players = load_player_context(manifest, ROOT)
    row = players[
        players.game_id.eq("0042500404") & players.player_id.eq(1631110)
    ].iloc[0]
    assert row.player == "Jeremy Sochan" and row.played
    assert row.minutes_seconds == 180
