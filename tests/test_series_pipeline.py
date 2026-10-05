"""Offline verification of series coverage, schema, failures, and source gates."""

import json
from pathlib import Path

import pandas as pd
import pytest

from data_sources.game_discovery import discover_from_game_log
from series_manifest import manifest_from_dict, load_manifest, save_manifest
from series_schema import to_processed, to_analytics, validate_processed
from series_ingestion import ingest_series, atomic_write, require_verification
from series_catalog import list_series, load_series
from scripts.compare_api_manual import compare_frames
from test_nba_matchups import make_api_frame
from data_sources.nba_matchups import normalize_boxscore_matchups

ROOT = Path(__file__).resolve().parents[1]


def make_manifest(n=2):
    return manifest_from_dict(
        {
            "series_id": "test_series",
            "season": "2025-26",
            "season_type": "Playoffs",
            "playoff_round": "Conference Finals",
            "team_a": "OKC",
            "team_b": "SAS",
            "series_complete": False,
            "games": [
                {
                    "game_number": i,
                    "game_id": f"004250031{i}",
                    "game_date": f"2026-05-{16 + 2 * i:02d}",
                }
                for i in range(1, n + 1)
            ],
        }
    )


def seed_cache(root, n=2):
    for i in range(1, n + 1):
        raw = make_api_frame()
        raw["gameId"] = f"004250031{i}"
        raw["teamId"] = [1610612760, 1610612759]
        atomic_write(root / "data/raw" / f"004250031{i}.csv", raw.to_csv(index=False))


def make_log(n=7):
    return pd.DataFrame(
        {
            "SEASON_ID": [42025] * n,
            "TEAM_ABBREVIATION": ["OKC"] * n,
            "GAME_ID": [f"004250031{i}" for i in range(1, n + 1)],
            "GAME_DATE": [f"2026-05-{16 + 2 * i:02d}" for i in range(1, n + 1)],
            "MATCHUP": ["OKC vs. SAS"] * n,
            "WL": ["L", "W", "W", "L", "W", "L", "L"][:n],
        }
    )


@pytest.mark.parametrize(
    "change",
    [
        {"series_id": "../bad"},
        {"season": "2025-25"},
        {"season_type": "Regular Season"},
        {"team_b": "OKC"},
        {"series_complete": "true"},
        {"source_csv": "../secret.csv"},
        {"games": [{"game_number": 1, "game_id": 42500311}]},
        {"games": [{"game_number": 1, "game_id": "0042400311"}]},
        {"games": [{"game_number": 2, "game_id": "0042500312"}]},
        {"games": [{"game_number": True, "game_id": "0042500311"}]},
        {
            "games": [
                {"game_number": 1, "game_id": "0042500311", "game_date": "2026-02-30"}
            ]
        },
    ],
)
def test_manifest_rejects_ambiguous_or_invalid_metadata(change):
    data = make_manifest().to_dict()
    data.update(change)
    with pytest.raises(ValueError):
        manifest_from_dict(data)


def test_manifest_roundtrip_preserves_leading_zero_ids(tmp_path):
    path = tmp_path / "manifest.yml"
    save_manifest(make_manifest(), path)
    assert load_manifest(path) == make_manifest()
    assert load_manifest(path).games[0].game_id == "0042500311"


def test_discovery_filters_non_playoffs_opponents_and_sorts_deduplicates():
    log = make_log()
    wrong = log.iloc[[0]].copy()
    wrong["SEASON_ID"] = 22025
    wrong["GAME_ID"] = "0022500011"
    other = log.iloc[[0]].copy()
    other["MATCHUP"] = "OKC vs. LAL"
    combined = pd.concat([log.iloc[::-1], log.iloc[[0]], wrong, other])
    result = discover_from_game_log(combined, "2025-26", "OKC", "SAS")
    assert len(result.games) == 7 and result.series_complete
    assert result.games[0].game_id == "0042500311"
    assert result.games[-1].game_date == "2026-05-30"
    assert result.playoff_round == "Conference Finals"


@pytest.mark.parametrize(
    "log",
    [
        make_log().drop(index=1),
        make_log().assign(WL="W"),
        make_log().assign(GAME_DATE="bad"),
    ],
)
def test_discovery_rejects_gaps_invalid_results_and_dates(log):
    with pytest.raises(ValueError):
        discover_from_game_log(log, "2025-26", "OKC", "SAS")


def test_discovery_marks_ongoing_series():
    assert not discover_from_game_log(
        make_log(3), "2025-26", "OKC", "SAS"
    ).series_complete


def test_parity_check_rejects_duplicate_empty_missing_and_nan():
    api = normalize_boxscore_matchups(make_api_frame(), 1)
    assert compare_frames(api, api)["status"] == "pass"
    assert compare_frames(api.iloc[:0], api.iloc[:0])["status"] == "fail"
    assert compare_frames(pd.concat([api, api]), api)["status"] == "fail"
    assert compare_frames(api.drop(columns="FG%"), api)["status"] == "fail"
    bad = api.copy()
    bad.loc[0, "Players PTS"] = float("nan")
    assert compare_frames(bad, api)["status"] == "fail"
    bad = api.copy()
    bad.loc[0, "FG%"] = float("nan")
    assert compare_frames(bad, api)["status"] == "fail"


def test_schema_roundtrip_preserves_manual_analytics():
    manifest = load_manifest(ROOT / "series/2026_okc_sas_sample.yml")
    raw = pd.read_csv(ROOT / manifest.source_csv)
    frame, _ = to_processed(raw, manifest, "manual_nba_com")
    validate_processed(frame, manifest)
    assert frame.game_id.iloc[0] == "0042500311"
    assert frame.off_player_id.isna().all()  # Unknown IDs never fabricated.
    assert frame.three_pm.sum() == raw["3PM"].sum()
    analytics, quality = to_analytics(frame)
    assert not quality["errors"]
    assert (
        analytics.matchup_seconds.sum()
        == raw.MIN.map(__import__("data_pipeline").parse_matchup_time).sum()
    )
    assert analytics.players_pts.sum() == raw["Players PTS"].sum()


def test_offline_full_pipeline_and_catalog_without_network(tmp_path):
    manifest = make_manifest()
    seed_cache(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("No network calls allowed")

    report = ingest_series(manifest, tmp_path, offline=True, fetcher=forbidden)
    assert report["coverage_complete"] and not report["series_complete"]
    assert report["source_verification"] == "offline_unverified"
    assert [g["status"] for g in report["games"]] == ["cached", "cached"]
    save_manifest(manifest, tmp_path / "series/test.yml")
    data, quality, provenance = load_series(manifest, tmp_path)
    assert len(data) == 4 and data.game.nunique() == 2
    assert data.off_team_id.iloc[0] == 1610612760
    assert provenance["source_verification"] == "offline_unverified"
    assert quality["warnings"]
    assert len(list_series(tmp_path)[0]) == 1
    path = tmp_path / "data/processed/test_series.csv"
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="hash"):
        load_series(manifest, tmp_path)


def test_missing_game_blocks_publication_and_stale_dataset_use(tmp_path):
    manifest = make_manifest()
    seed_cache(tmp_path, n=1)
    report = ingest_series(manifest, tmp_path, offline=True)
    assert report["status"] == "partial" and not report["coverage_complete"]
    assert "0042500312" in " ".join(report["errors"])
    assert not (tmp_path / "data/processed/test_series.csv").exists()
    seed_cache(tmp_path, n=2)
    assert ingest_series(manifest, tmp_path, offline=True)["status"] == "complete"
    (tmp_path / "data/raw/0042500312.csv").unlink()
    assert ingest_series(manifest, tmp_path, offline=True)["status"] == "partial"
    with pytest.raises(ValueError, match="incomplete"):
        load_series(manifest, tmp_path)


def test_wrong_game_and_team_caches_fail(tmp_path):
    manifest = make_manifest(1)
    seed_cache(tmp_path, n=1)
    raw = make_api_frame()
    raw["gameId"] = "0042500312"
    atomic_write(tmp_path / "data/raw/0042500311.csv", raw.to_csv(index=False))
    assert ingest_series(manifest, tmp_path, offline=True)["status"] == "failed"
    raw = make_api_frame()
    raw["teamTricode"] = ["BOS", "MIA"]
    atomic_write(tmp_path / "data/raw/0042500311.csv", raw.to_csv(index=False))
    assert ingest_series(manifest, tmp_path, offline=True)["status"] == "failed"


def test_live_ingestion_stops_before_network_if_parity_gate_fails(tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("Gate must precede network")

    report = ingest_series(make_manifest(), tmp_path, fetcher=forbidden)
    assert report["status"] == "failed"
    assert "verification-report" in " ".join(report["errors"])
    path = tmp_path / "failed.json"
    path.write_text(json.dumps({"status": "fail"}))
    report = ingest_series(
        make_manifest(), tmp_path, verification_report=path, fetcher=forbidden
    )
    assert "parity" in " ".join(report["errors"])


def test_live_fetch_cache_reuse_and_team_ids(tmp_path, monkeypatch):
    import series_ingestion

    monkeypatch.setattr(series_ingestion, "require_verification", lambda *args: None)
    calls = []

    def fetch(game_id, **kwargs):
        calls.append(game_id)
        raw = make_api_frame()
        raw["gameId"] = game_id
        return raw

    manifest = make_manifest()
    assert (
        ingest_series(manifest, tmp_path, fetcher=fetch, request_interval=0)["status"]
        == "complete"
    )
    assert calls == ["0042500311", "0042500312"]
    calls.clear()
    assert (
        ingest_series(manifest, tmp_path, fetcher=fetch, request_interval=0)["status"]
        == "complete"
    )
    assert calls == []


@pytest.mark.parametrize(
    "column,value",
    [
        ("matchup_seconds", float("inf")),
        ("partial_possessions", -1),
        ("fg_pct", 101),
        ("game_id", "0042500999"),
        ("season", "2024-25"),
    ],
)
def test_processed_validation_rejects_corrupt_values(column, value):
    m = make_manifest(1)
    frame, _ = to_processed(
        normalize_boxscore_matchups(make_api_frame(), 1), m, "nba_boxscorematchupsv3"
    )
    if column == "matchup_seconds":
        frame[column] = frame[column].astype(float)
    frame.loc[0, column] = value
    with pytest.raises(ValueError):
        validate_processed(frame, m)


def test_processed_rejects_missing_coverage_and_duplicate_keys():
    m = make_manifest()
    frame, _ = to_processed(
        normalize_boxscore_matchups(make_api_frame(), 1), m, "nba_boxscorematchupsv3"
    )
    with pytest.raises(ValueError, match="coverage"):
        validate_processed(frame, m)
    one = make_manifest(1)
    with pytest.raises(ValueError, match="Duplicate"):
        validate_processed(pd.concat([frame, frame]), one)


def test_malformed_yaml_reports_clear_catalog_error(tmp_path):
    path = tmp_path / "series/bad.yml"
    path.parent.mkdir()
    path.write_text("games: [")
    with pytest.raises(ValueError, match="Invalid YAML"):
        load_manifest(path)
    series, errors = list_series(tmp_path)
    assert not series and errors


def test_cli_manual_ingestion_and_offline_discovery(tmp_path):
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.fetch_series",
            "--manifest",
            str(ROOT / "series/2026_okc_sas_sample.yml"),
            "--offline",
            "--output-dir",
            str(tmp_path / "processed"),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert "series complete: False" in result.stdout
    log = tmp_path / "games.csv"
    make_log().to_csv(log, index=False)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.fetch_series",
            "--season",
            "2025-26",
            "--team-a",
            "OKC",
            "--team-b",
            "SAS",
            "--game-log-csv",
            str(log),
            "--project-root",
            str(tmp_path),
            "--offline",
            "--discover-only",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert len(load_manifest(tmp_path / "series/2025_26_okc_sas.yml").games) == 7
    # Repeating the same discovery is safe and leaves the curated sample alone.
    result2 = subprocess.run(result.args, cwd=ROOT, text=True, capture_output=True)
    assert result2.returncode == 0, result2.stderr


def test_zero_total_matchup_time_cannot_be_analyzed():
    m = make_manifest(1)
    raw = normalize_boxscore_matchups(make_api_frame(), 1)
    raw["MIN"] = "00:00"
    with pytest.raises(ValueError, match="undefined"):
        to_processed(raw, m, "nba_boxscorematchupsv3")


def test_live_gate_accepts_only_current_complete_benchmark_report(tmp_path):
    from scripts.compare_api_manual import adapter_digest, file_digest

    raw = pd.read_csv(ROOT / "data/OKC Spurs Matchup Data.csv")
    (tmp_path / "data").mkdir()
    benchmark = tmp_path / "data/OKC Spurs Matchup Data.csv"
    raw.to_csv(benchmark, index=False)
    game1 = raw[raw.Game == 1]
    report = compare_frames(game1, game1)
    report.update(
        game_id="0042500311",
        game_number=1,
        adapter_sha256=adapter_digest(),
        manual_sha256=file_digest(benchmark),
    )
    path = tmp_path / "verification.json"
    path.write_text(json.dumps(report))
    require_verification(path, tmp_path)
    report["adapter_sha256"] = "outdated"
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError):
        require_verification(path, tmp_path)
    report["adapter_sha256"] = adapter_digest()
    report["manual_sha256"] = "wrong"
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError):
        require_verification(path, tmp_path)


def test_fractional_seconds_are_preserved_without_false_zero_warning():
    m = make_manifest(1)
    raw = normalize_boxscore_matchups(make_api_frame(), 1)
    frame, _ = to_processed(raw, m, "nba_boxscorematchupsv3")
    frame["matchup_seconds"] = [0.5, 60.5]
    validate_processed(frame, m)
    analytics, report = to_analytics(frame)
    assert analytics.matchup_seconds.tolist() == [0.5, 60.5]
    assert report["zero_matchup_time_rows"] == 0
    assert not report["warnings"]
