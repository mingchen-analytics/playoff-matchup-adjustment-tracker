"""Acquire, validate and freeze traditional player game box scores for a series."""

import argparse
from pathlib import Path

from player_ingestion import ingest_player_context
from series_manifest import load_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--project-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--request-interval", type=float, default=2)
    args = parser.parse_args()
    try:
        report = ingest_player_context(
            load_manifest(args.manifest),
            args.project_root,
            offline=args.offline,
            timeout=args.timeout,
            retries=args.retries,
            request_interval=args.request_interval,
        )
        print(
            f"Published {report['rows']} player-game roster rows for {report['series_id']}."
        )
    except (ValueError, OSError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
