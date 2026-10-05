"""Discover, cache, validate and process a playoff series from a manifest or team pair."""

from __future__ import annotations
import argparse
from dataclasses import replace
from pathlib import Path
import sys
import pandas as pd
from data_sources.game_discovery import fetch_game_log, discover_from_game_log
from series_manifest import load_manifest, save_manifest
from series_ingestion import ingest_series, atomic_write


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path)
    p.add_argument("--season")
    p.add_argument("--season-type", default="Playoffs", choices=["Playoffs"])
    p.add_argument("--team-a")
    p.add_argument("--team-b")
    p.add_argument("--round", dest="playoff_round")
    p.add_argument("--series-id")
    p.add_argument(
        "--game-log-csv", type=Path, help="Offline LeagueGameFinder CSV for discovery"
    )
    p.add_argument("--discover-only", action="store_true")
    p.add_argument(
        "--offline", action="store_true", help="Use raw caches only; no NBA requests"
    )
    p.add_argument(
        "--project-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    p.add_argument("--cache-dir", type=Path)
    p.add_argument("--output-dir", type=Path)
    p.add_argument("--verification-report", type=Path)
    p.add_argument(
        "--source-policy",
        choices=["strict_parity", "separate_snapshot"],
        default="strict_parity",
    )
    p.add_argument("--timeout", type=float, default=20)
    p.add_argument("--retries", type=int, default=2)
    p.add_argument("--request-interval", type=float, default=2)
    args = p.parse_args()
    if args.manifest and any(
        [
            args.season,
            args.team_a,
            args.team_b,
            args.game_log_csv,
            args.series_id,
            args.playoff_round,
        ]
    ):
        p.error("Use --manifest OR team/season discovery arguments.")
    if not args.manifest and not all([args.season, args.team_a, args.team_b]):
        p.error("Provide --manifest or --season --team-a --team-b.")
    if args.offline and not args.manifest and not args.game_log_csv:
        p.error("Offline discovery requires --game-log-csv.")
    try:
        if args.manifest:
            manifest = load_manifest(args.manifest)
        else:
            log = (
                pd.read_csv(args.game_log_csv, dtype={"GAME_ID": str, "SEASON_ID": str})
                if args.game_log_csv
                else fetch_game_log(
                    args.season,
                    args.team_a,
                    args.team_b,
                    timeout=args.timeout,
                    retries=args.retries,
                )
            )
            manifest = discover_from_game_log(
                log, args.season, args.team_a, args.team_b
            )
            if args.playoff_round:
                manifest = replace(manifest, playoff_round=args.playoff_round)
            if args.series_id:
                from series_manifest import manifest_from_dict

                data = manifest.to_dict()
                data["series_id"] = args.series_id
                manifest = manifest_from_dict(data)
            cache = args.cache_dir or args.project_root / "data"
            atomic_write(
                cache / "discovery" / f"{manifest.series_id}.csv",
                log.to_csv(index=False),
            )
            target = args.project_root / "series" / f"{manifest.series_id}.yml"
            # Never overwrite a curated manifest or its manual source configuration.
            if target.exists() and load_manifest(target) != manifest:
                raise ValueError(
                    f"Manifest already exists with different configuration: {target}. Choose a new --series-id."
                )
            save_manifest(manifest, target)
            print(
                f"Discovered {len(manifest.games)} played games; series complete: {manifest.series_complete}"
            )
            print(f"Manifest: {target}")
        if args.discover_only:
            return
        report = ingest_series(
            manifest,
            args.project_root,
            cache_dir=args.cache_dir,
            output_dir=args.output_dir,
            offline=args.offline,
            verification_report=args.verification_report,
            source_policy=args.source_policy,
            timeout=args.timeout,
            retries=args.retries,
            request_interval=args.request_interval,
        )
        print(
            f"Ingestion: {report['status'].upper()}; configured coverage complete: {report['coverage_complete']}; series complete: {report['series_complete']}"
        )
        for issue in report["errors"]:
            print(f"- {issue}")
        if report["status"] != "complete":
            sys.exit(1)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
