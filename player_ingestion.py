"""Raw-cache-first player context publication, isolated from dashboard execution."""

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from data_sources.player_boxscores import fetch_player_boxscore
from game_context import load_game_context
from player_context import (
    manifest_digest,
    normalize_player_boxscore,
    validate_player_context,
)
from series_catalog import load_series
from series_ingestion import atomic_write, sha256


def ingest_player_context(
    manifest,
    project_root,
    *,
    offline=False,
    timeout=20,
    retries=2,
    request_interval=2,
    fetcher=fetch_player_boxscore,
):
    if manifest.source_csv:
        raise ValueError(
            "Player box scores are only attached to independent API snapshots."
        )
    if timeout <= 0 or retries < 1 or request_interval < 0:
        raise ValueError("Invalid ingestion timeout, retries or request interval.")
    root = Path(project_root)
    output = root / "data/player_context" / f"{manifest.series_id}.csv"
    report_path = output.with_suffix(".report.json")
    if output.exists() or report_path.exists():
        raise ValueError(
            "Published player context cannot be overwritten. Use a new versioned series ID."
        )
    matchups, _, _ = load_series(manifest, root)
    team_context = load_game_context(manifest, root)
    if team_context is None:
        raise ValueError("Publish verified team game context before player box scores.")
    report = {
        "schema_version": 1,
        "series_id": manifest.series_id,
        "status": "running",
        "endpoint": "NBA BoxScoreTraditionalV3",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": manifest_digest(manifest),
        "team_game_log_sha256": sha256(
            root / "data/context" / f"{manifest.series_id}.csv"
        ),
        "matchup_dataset_sha256": sha256(
            root / "data/snapshots" / f"{manifest.series_id}.csv"
        ),
        "normalizer_sha256": sha256(Path(__file__).with_name("player_context.py")),
        "games": [],
    }
    frames = []
    fetched = False
    try:
        for game in manifest.games:
            raw = root / "data/raw/player_boxes" / f"{game.game_id}.json"
            meta_path = raw.with_suffix(".meta.json")
            item = {
                "game_id": game.game_id,
                "game_number": game.game_number,
                "status": "pending",
            }
            report["games"].append(item)
            if not raw.exists():
                if offline:
                    raise ValueError(
                        f"Missing player box-score cache for {game.game_id}."
                    )
                if fetched:
                    time.sleep(request_interval)
                fetched = True
                payload = fetcher(game.game_id, timeout=timeout, retries=retries)
                atomic_write(raw, json.dumps(payload, indent=2))
                atomic_write(
                    meta_path,
                    json.dumps(
                        {
                            "game_id": game.game_id,
                            "endpoint": report["endpoint"],
                            "fetched_at": datetime.now(timezone.utc).isoformat(),
                            "raw_sha256": sha256(raw),
                        },
                        indent=2,
                    ),
                )
                item["status"] = "fetched"
            else:
                item["status"] = "cached"
            if not meta_path.exists():
                raise ValueError(
                    f"Player cache {game.game_id} lacks acquisition evidence."
                )
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            timestamp = datetime.fromisoformat(meta.get("fetched_at", ""))
            if (
                meta.get("game_id") != game.game_id
                or meta.get("endpoint") != report["endpoint"]
                or meta.get("raw_sha256") != sha256(raw)
                or timestamp.tzinfo is None
            ):
                raise ValueError(
                    "Player cache acquisition evidence does not match its raw data."
                )
            payload = json.loads(raw.read_text(encoding="utf-8"))
            frame = normalize_player_boxscore(payload, game, manifest)
            frames.append(frame)
            item.update(rows=len(frame), acquisition=meta)
        combined = pd.concat(frames, ignore_index=True)
        validate_player_context(combined, manifest, team_context, matchups)
        text = combined.to_csv(index=False)
        report.update(
            status="complete",
            rows=len(combined),
            dataset_sha256=hashlib.sha256(text.encode()).hexdigest(),
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        atomic_write(output, text)
        atomic_write(report_path, json.dumps(report, indent=2))
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
        report.update(
            status="failed",
            error=str(exc),
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        atomic_write(
            root / "data/processed" / f"{manifest.series_id}.player_failure.json",
            json.dumps(report, indent=2),
        )
        raise ValueError(f"Player context ingestion failed: {exc}") from exc
    return report
