"""Bounded, resumable ingestion with explicit coverage and provenance reports."""

from __future__ import annotations
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import time

import pandas as pd
from data_sources.nba_matchups import (
    fetch_boxscore_matchups,
    normalize_boxscore_matchups,
)
from scripts.compare_api_manual import adapter_digest
from series_schema import to_processed, validate_processed


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".write-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require_verification(path, project_root):
    if path is None or not Path(path).exists():
        raise ValueError(
            "Live series ingestion requires a passing --verification-report from compare_api_manual."
        )
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    if (
        report.get("status") != "pass"
        or report.get("adapter_sha256") != adapter_digest()
    ):
        raise ValueError(
            "API/manual parity has not passed for the current adapter. Resolve discrepancies before live series ingestion."
        )
    benchmark = Path(project_root) / "data/OKC Spurs Matchup Data.csv"
    if (
        report.get("game_id") != "0042500311"
        or report.get("game_number") != 1
        or report.get("manual_sha256") != sha256(benchmark)
    ):
        raise ValueError(
            "Verification report does not match the repository Game 1 benchmark."
        )
    if (
        report.get("matched_rows", 0) < 1
        or report.get("failures")
        or report.get("manual_only")
        or report.get("api_only")
    ):
        raise ValueError("Verification report lacks a complete passing comparison.")


def ingest_series(
    manifest,
    project_root,
    *,
    cache_dir=None,
    output_dir=None,
    offline=False,
    verification_report=None,
    source_policy="strict_parity",
    timeout=20,
    retries=2,
    request_interval=2,
    fetcher=None,
):
    root = Path(project_root)
    cache = Path(cache_dir) if cache_dir else root / "data"
    output = Path(output_dir) if output_dir else root / "data/processed"
    report = {
        "schema_version": 1,
        "series_id": manifest.series_id,
        "status": "failed",
        "coverage_complete": False,
        "series_complete": manifest.series_complete,
        "expected_games": len(manifest.games),
        "games": [],
        "errors": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "adapter_sha256": adapter_digest(),
        "manifest_sha256": hashlib.sha256(
            json.dumps(manifest.to_dict(), sort_keys=True).encode()
        ).hexdigest(),
    }
    report_path = output / f"{manifest.series_id}.report.json"
    processed_path = output / f"{manifest.series_id}.csv"
    discovery_path = cache / "discovery" / f"{manifest.series_id}.csv"
    if discovery_path.exists():
        report["discovery_sha256"] = sha256(discovery_path)
    if output.name == "snapshots" and processed_path.exists():
        raise ValueError(
            "Published snapshots are immutable. Choose a new timestamped series_id to acquire another version."
        )
    frames = []
    fetcher = fetcher or fetch_boxscore_matchups
    if request_interval < 0 or retries < 1 or timeout <= 0:
        raise ValueError("Invalid ingestion timeout/retry/request interval.")
    try:
        if manifest.source_csv:
            source = root / manifest.source_csv
            raw = pd.read_csv(source)
            frame, quality = to_processed(raw, manifest, "manual_nba_com")
            validate_processed(frame, manifest)
            frames = [frame]
            report["source_sha256"] = sha256(source)
            for game in manifest.games:
                report["games"].append(
                    {
                        "game_number": game.game_number,
                        "game_id": game.game_id,
                        "status": "manual",
                        "rows": int(frame.game_number.eq(game.game_number).sum()),
                    }
                )
        else:
            # Cached snapshots can be explored offline; never imply API/manual parity.
            if source_policy == "separate_snapshot":
                policy_path = root / "docs/source_policy.json"
                policy = json.loads(policy_path.read_text(encoding="utf-8"))
                comparison_path = root / "docs/api_manual_game1_comparison.json"
                comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
                if (
                    policy.get("approved") is not True
                    or policy.get("policy") != source_policy
                    or policy.get("comparison_sha256") != sha256(comparison_path)
                    or comparison.get("adapter_sha256") != adapter_digest()
                    or comparison.get("manual_sha256")
                    != sha256(root / "data/OKC Spurs Matchup Data.csv")
                    or comparison.get("matched_rows") != 176
                    or comparison.get("game_id") != "0042500311"
                    or comparison.get("game_number") != 1
                    or comparison.get("status") != "fail"
                    or policy.get("manual_parity") != "fail"
                    or comparison.get("manual_only")
                    or comparison.get("api_only")
                ):
                    raise ValueError(
                        "Separate-snapshot approval does not match the current adapter and benchmark."
                    )
                report["source_verification"] = "approved_separate_snapshot"
                report["manual_parity"] = comparison["status"]
                report["source_policy_sha256"] = sha256(policy_path)
            elif source_policy != "strict_parity":
                raise ValueError("Unknown source policy.")
            elif not offline:
                require_verification(verification_report, root)
            if source_policy == "strict_parity":
                report["source_verification"] = (
                    "offline_unverified" if offline else "pass"
                )
            fetched = False
            for game in manifest.games:
                item = {
                    "game_number": game.game_number,
                    "game_id": game.game_id,
                    "status": "failed",
                }
                try:
                    raw_path = cache / "raw" / f"{game.game_id}.csv"
                    if raw_path.exists():
                        raw = pd.read_csv(raw_path, dtype={"gameId": str})
                        item["status"] = "cached"
                    else:
                        if offline:
                            raise ValueError(
                                f"Missing raw cache for {game.game_id}; offline mode makes no network requests."
                            )
                        if fetched:
                            time.sleep(request_interval)
                        fetched = True
                        raw = fetcher(game.game_id, timeout=timeout, retries=retries)
                        atomic_write(raw_path, raw.to_csv(index=False))
                        atomic_write(
                            raw_path.with_suffix(".meta.json"),
                            json.dumps(
                                {
                                    "game_id": game.game_id,
                                    "endpoint": "NBA BoxScoreMatchupsV3",
                                    "fetched_at": datetime.now(
                                        timezone.utc
                                    ).isoformat(),
                                    "raw_sha256": sha256(raw_path),
                                },
                                indent=2,
                            ),
                        )
                        item["status"] = "fetched"
                    if (
                        raw.empty
                        or "gameId" not in raw
                        or not raw.gameId.astype(str).eq(game.game_id).all()
                    ):
                        raise ValueError(
                            f"Raw snapshot does not match game {game.game_id}."
                        )
                    normalized = normalize_boxscore_matchups(raw, game.game_number)
                    frame, quality = to_processed(
                        normalized, manifest, "nba_boxscorematchupsv3"
                    )
                    item.update(
                        rows=len(frame),
                        raw_sha256=sha256(raw_path),
                        warnings=quality["warnings"],
                    )
                    meta_path = raw_path.with_suffix(".meta.json")
                    if meta_path.exists():
                        item["acquisition"] = json.loads(
                            meta_path.read_text(encoding="utf-8")
                        )
                        if item["acquisition"].get("raw_sha256") != sha256(raw_path):
                            raise ValueError(
                                "Raw cache differs from acquisition metadata."
                            )
                    else:
                        item["acquisition"] = {
                            "endpoint": "NBA BoxScoreMatchupsV3",
                            "fetched_at": None,
                            "note": "Imported cache; original acquisition timestamp unavailable.",
                        }
                    # Retain IDs for both teams without guessing historical player identities.
                    if "teamId" in raw:
                        ids = raw.groupby("teamTricode").teamId.unique()
                        if any(len(values) != 1 for values in ids):
                            raise ValueError("Inconsistent team IDs.")
                        lookup = {team: int(values[0]) for team, values in ids.items()}
                        frame["off_team_id"] = frame.off_team.map(lookup)
                        frame["def_team_id"] = frame.def_team.map(lookup)
                    atomic_write(
                        cache / "normalized" / f"{game.game_id}.csv",
                        frame.to_csv(index=False),
                    )
                    frames.append(frame)
                except (ValueError, RuntimeError, OSError, KeyError) as exc:
                    item.update(status="failed", error=str(exc))
                    report["errors"].append(
                        f"Game {game.game_number} ({game.game_id}): {exc}"
                    )
                report["games"].append(item)
        if report["errors"]:
            raise ValueError("Some games failed; no complete dataset was published.")
        combined = pd.concat(frames, ignore_index=True)
        quality = validate_processed(combined, manifest)
        if manifest.source_csv is None and offline and source_policy == "strict_parity":
            quality["warnings"].append(
                "Offline API snapshot: API/manual parity has not been approved."
            )
        if not manifest.series_complete:
            quality["warnings"].append(
                "Manifest represents a sample or ongoing series; coverage is complete only for configured games."
            )
        atomic_write(processed_path, combined.to_csv(index=False))
        report.update(
            status="complete",
            coverage_complete=True,
            rows=len(combined),
            quality=quality,
            dataset_sha256=sha256(processed_path),
            dataset_path=processed_path.name,
        )
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        report["errors"].append(str(exc))
        report["status"] = "partial" if frames else "failed"
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    atomic_write(report_path, json.dumps(report, indent=2, allow_nan=False))
    return report
