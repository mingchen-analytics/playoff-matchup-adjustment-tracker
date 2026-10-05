"""Cache-first atomic series publication of substitution/foul observations."""

import hashlib
import json
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from data_sources.play_by_play import fetch_play_by_play
from event_context import normalize_events
from game_context import load_game_context
from player_context import load_player_context, manifest_digest
from series_ingestion import atomic_write, sha256


def ingest_event_context(
    manifest,
    project_root,
    *,
    offline=False,
    timeout=20,
    retries=2,
    request_interval=2,
    fetcher=fetch_play_by_play,
):
    root = Path(project_root)
    output = root / "data/event_context" / manifest.series_id
    if output.exists():
        raise ValueError(
            "Published event context cannot be overwritten. Use a new versioned series ID."
        )
    if manifest.source_csv or timeout <= 0 or retries < 1 or request_interval < 0:
        raise ValueError(
            "Event ingestion requires an API snapshot and valid request settings."
        )
    players = load_player_context(manifest, root)
    results = load_game_context(manifest, root)
    if players is None or results is None:
        raise ValueError(
            "Publish verified player and team context before event ingestion."
        )
    report = {
        "schema_version": 1,
        "series_id": manifest.series_id,
        "endpoint": "NBA PlayByPlayV3",
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": manifest_digest(manifest),
        "normalizer_sha256": sha256(Path(__file__).with_name("event_context.py")),
        "team_game_log_sha256": sha256(
            root / "data/context" / f"{manifest.series_id}.csv"
        ),
        "player_dataset_sha256": sha256(
            root / "data/player_context" / f"{manifest.series_id}.csv"
        ),
        "games": [],
    }
    processed = root / "data/processed"
    processed.mkdir(parents=True, exist_ok=True)
    fetched = False
    try:
        with tempfile.TemporaryDirectory(
            prefix="event-stage-", dir=processed
        ) as temporary:
            stage = Path(temporary)
            for game in manifest.games:
                item = {
                    "game_id": game.game_id,
                    "game_number": game.game_number,
                    "status": "pending",
                }
                report["games"].append(item)
                raw = root / "data/raw/play_by_play" / f"{game.game_id}.json"
                meta_path = raw.with_suffix(".meta.json")
                if not raw.exists():
                    if offline:
                        raise ValueError(
                            f"Missing play-by-play cache for {game.game_id}."
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
                        "Play-by-play cache is missing acquisition evidence."
                    )
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if (
                    not isinstance(meta, dict)
                    or meta.get("raw_sha256") != sha256(raw)
                    or meta.get("game_id") != game.game_id
                    or meta.get("endpoint") != report["endpoint"]
                    or datetime.fromisoformat(meta.get("fetched_at", "")).tzinfo is None
                ):
                    raise ValueError(
                        "Play-by-play cache acquisition evidence does not match its data."
                    )
                payload = json.loads(raw.read_text(encoding="utf-8"))
                frame, summary = normalize_events(
                    payload, game, manifest, results, players
                )
                text = frame.to_csv(index=False)
                item.update(
                    summary,
                    rows=len(frame),
                    acquisition=meta,
                    dataset_sha256=hashlib.sha256(text.encode()).hexdigest(),
                )
                atomic_write(stage / f"{game.game_id}.csv", text)
            report.update(
                status="complete",
                rows=sum(g["rows"] for g in report["games"]),
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
            atomic_write(stage / "report.json", json.dumps(report, indent=2))
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.exists():
                raise ValueError(
                    "A concurrent publication already created this event snapshot."
                )
            stage.rename(output)
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
        report.update(
            status="failed",
            error=str(exc),
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        atomic_write(
            processed / f"{manifest.series_id}.event_failure.json",
            json.dumps(report, indent=2),
        )
        raise ValueError(f"Event context ingestion failed: {exc}") from exc
    return report
