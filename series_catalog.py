"""Discover configured series and load validated snapshots without network access."""

import json
import hashlib
from pathlib import Path
import pandas as pd
from series_manifest import load_manifest
from series_schema import to_processed, to_analytics, validate_processed


def _matches_dataset_hash(path, expected):
    """Accept Git's Windows line endings without ignoring content changes.

    Published snapshots use LF, but older Windows checkouts may contain CRLF.
    Retain the original byte hash check for reports made from other files.
    """
    data = path.read_bytes()
    return expected in {
        hashlib.sha256(data).hexdigest(),
        hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest(),
    }


def list_series(project_root):
    series = []
    errors = []
    for path in sorted((Path(project_root) / "series").glob("*.y*ml")):
        try:
            manifest = load_manifest(path)
            if any(m.series_id == manifest.series_id for _, m in series):
                raise ValueError("Duplicate series_id.")
            series.append((path, manifest))
        except (ValueError, OSError) as exc:
            errors.append(f"{path.name}: {exc}")
    series.sort(
        key=lambda pair: (
            not bool(pair[1].source_csv),
            not (
                Path(project_root) / "data/processed" / f"{pair[1].series_id}.csv"
            ).exists()
            and not (
                Path(project_root) / "data/snapshots" / f"{pair[1].series_id}.csv"
            ).exists(),
            pair[1].series_id,
        )
    )
    return series, errors


def load_series(manifest, project_root):
    root = Path(project_root)
    if manifest.source_csv:
        frame, quality = to_processed(
            pd.read_csv(root / manifest.source_csv), manifest, "manual_nba_com"
        )
        validate_processed(frame, manifest)
        provenance = {
            "source": "Manual NBA.com reference",
            "coverage_complete": True,
            "series_complete": manifest.series_complete,
            "notes": manifest.notes,
        }
    else:
        path = root / "data/processed" / f"{manifest.series_id}.csv"
        published = root / "data/snapshots" / f"{manifest.series_id}.csv"
        if published.exists():
            path = published
        report_path = path.with_suffix(".report.json")
        if not path.exists() or not report_path.exists():
            raise ValueError(
                "Series data is unavailable. Run scripts.fetch_series in a controlled ingestion environment first."
            )
        provenance = json.loads(report_path.read_text(encoding="utf-8"))
        if provenance.get("series_id") != manifest.series_id:
            raise ValueError("Report belongs to another series.")
        if (
            provenance.get("manifest_sha256")
            and provenance["manifest_sha256"]
            != hashlib.sha256(
                json.dumps(manifest.to_dict(), sort_keys=True).encode()
            ).hexdigest()
        ):
            raise ValueError("Manifest differs from its snapshot report.")
        if provenance.get("status") != "complete" or not provenance.get(
            "coverage_complete"
        ):
            raise ValueError(
                "Latest ingestion was incomplete. Review its report before using this series."
            )
        if not _matches_dataset_hash(path, provenance.get("dataset_sha256")):
            raise ValueError("Dataset hash differs from its ingestion report.")
        frame = pd.read_csv(path, dtype={"game_id": "string", "game_date": "string"})
        quality = validate_processed(frame, manifest)
        provenance["source"] = "Cached NBA BoxScoreMatchupsV3 snapshot"
    analytics, quality = to_analytics(frame)
    if not manifest.series_complete:
        quality["warnings"].append(
            "Sample/ongoing series: only configured games are available."
        )
    if provenance.get("source_verification") == "offline_unverified":
        quality["warnings"].append(
            "Offline snapshot; API/manual parity remains unresolved."
        )
    if provenance.get("source_verification") == "approved_separate_snapshot":
        quality["warnings"].append(
            "Independent API snapshot; numerical parity with the manual reference failed. Do not mix these sources."
        )
    if quality["warnings"]:
        quality["status"] = "warning"
    return analytics, quality, provenance
