"""Real frozen NBA snapshots are tested without any network dependency."""

import json
from pathlib import Path
import shutil

import pytest
from streamlit.testing.v1 import AppTest

from series_catalog import load_series
from series_ingestion import ingest_series
from series_manifest import load_manifest
from test_series_pipeline import make_manifest, seed_cache

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = [("2026_okc_sas_api_20261005", 1513), ("2025_okc_ind_api_20261005", 1388)]


@pytest.mark.parametrize("series_id,rows", SNAPSHOTS)
def test_real_snapshot_coverage_and_provenance(series_id, rows):
    manifest = load_manifest(ROOT / "series" / f"{series_id}.yml")
    frame, quality, provenance = load_series(manifest, ROOT)
    assert len(frame) == rows
    assert sorted(frame.game.unique()) == list(range(1, 8))
    assert manifest.series_complete and provenance["coverage_complete"]
    assert provenance["source_verification"] == "approved_separate_snapshot"
    assert provenance["manual_parity"] == "fail"
    assert provenance["started_at"] and provenance["finished_at"]
    assert len(provenance["games"]) == 7
    assert all(
        g["raw_sha256"] and g["acquisition"]["endpoint"] for g in provenance["games"]
    )
    assert not quality["errors"]
    assert any("Do not mix" in warning for warning in quality["warnings"])


def test_real_multi_series_dashboard_switching():
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    assert not app.exception and not app.error
    for season, series_id in [
        ("2025-26", SNAPSHOTS[0][0]),
        ("2024-25", SNAPSHOTS[1][0]),
    ]:
        app.sidebar.selectbox[0].set_value(season).run(timeout=30)
        app.sidebar.selectbox[2].set_value(series_id).run(timeout=30)
        assert not app.exception and not app.error
        assert app.selectbox(key=f"player_{series_id}").value
        assert any(
            "Independent API snapshot" in warning.value for warning in app.warning
        )
        assert any(m.label == "Largest Adjustment" for m in app.metric)


def seed_approval(root):
    for relative in [
        "docs/source_policy.json",
        "docs/api_manual_game1_comparison.json",
        "data/OKC Spurs Matchup Data.csv",
    ]:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / relative, target)
    seed_cache(root, 1)


def test_approved_snapshot_does_not_claim_parity(tmp_path):
    seed_approval(tmp_path)
    report = ingest_series(
        make_manifest(1), tmp_path, offline=True, source_policy="separate_snapshot"
    )
    assert report["status"] == "complete"
    assert report["source_verification"] == "approved_separate_snapshot"
    assert report["manual_parity"] == "fail"
    assert report["games"][0]["acquisition"]["fetched_at"] is None


@pytest.mark.parametrize("changed", ["approval", "comparison", "benchmark", "adapter"])
def test_snapshot_policy_rejects_changed_evidence(tmp_path, changed, monkeypatch):
    seed_approval(tmp_path)
    if changed == "approval":
        path = tmp_path / "docs/source_policy.json"
        policy = json.loads(path.read_text())
        policy["approved"] = False
        path.write_text(json.dumps(policy))
    elif changed == "comparison":
        path = tmp_path / "docs/api_manual_game1_comparison.json"
        path.write_text(path.read_text() + "\n")
    elif changed == "benchmark":
        path = tmp_path / "data/OKC Spurs Matchup Data.csv"
        path.write_text(path.read_text() + "\n")
    else:
        monkeypatch.setattr("series_ingestion.adapter_digest", lambda: "changed")
    report = ingest_series(
        make_manifest(1), tmp_path, offline=True, source_policy="separate_snapshot"
    )
    assert report["status"] == "failed"
    assert not (tmp_path / "data/processed/test_series.csv").exists()


def test_published_snapshot_cannot_be_overwritten(tmp_path):
    output = tmp_path / "data/snapshots"
    output.mkdir(parents=True)
    path = output / "test_series.csv"
    path.write_text("existing snapshot")
    with pytest.raises(ValueError, match="immutable"):
        ingest_series(make_manifest(1), tmp_path, output_dir=output)
    assert path.read_text() == "existing snapshot"


def test_fresh_acquisition_records_timestamp_and_hash(tmp_path):
    from test_nba_matchups import make_api_frame

    seed_approval(tmp_path)
    report = ingest_series(
        make_manifest(1),
        tmp_path,
        cache_dir=tmp_path / "fresh",
        source_policy="separate_snapshot",
        fetcher=lambda *args, **kwargs: make_api_frame(),
    )
    assert report["status"] == "complete"
    game = report["games"][0]
    assert game["status"] == "fetched"
    assert game["acquisition"]["fetched_at"]
    assert game["acquisition"]["raw_sha256"] == game["raw_sha256"]


def test_rejects_cache_with_stale_acquisition_hash(tmp_path):
    seed_approval(tmp_path)
    path = tmp_path / "data/raw/0042500311.meta.json"
    path.write_text(json.dumps({"raw_sha256": "incorrect"}))
    report = ingest_series(
        make_manifest(1), tmp_path, offline=True, source_policy="separate_snapshot"
    )
    assert report["status"] == "failed"
    assert "acquisition metadata" in report["errors"][0]


@pytest.mark.parametrize("changed", ["dataset", "manifest"])
def test_frozen_snapshot_rejects_modified_content(tmp_path, changed):
    from dataclasses import replace

    series_id = SNAPSHOTS[0][0]
    manifest = load_manifest(ROOT / "series" / f"{series_id}.yml")
    output = tmp_path / "data/snapshots"
    output.mkdir(parents=True)
    for extension in ["csv", "report.json"]:
        shutil.copy(ROOT / "data/snapshots" / f"{series_id}.{extension}", output)
    if changed == "dataset":
        path = output / f"{series_id}.csv"
        path.write_text(path.read_text() + "\n")
    else:
        manifest = replace(manifest, notes="Changed metadata")
    with pytest.raises(ValueError, match="hash|Manifest differs"):
        load_series(manifest, tmp_path)
