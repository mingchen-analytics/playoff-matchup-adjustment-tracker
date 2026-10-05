"""Fetch one NBA game's matchup data and save it in project format."""

from __future__ import annotations

import argparse
from pathlib import Path

from data_pipeline import prepare_matchup_data
from data_sources.nba_matchups import (
    fetch_boxscore_matchups,
    normalize_boxscore_matchups,
)
from series_ingestion import atomic_write


def main():
    parser = argparse.ArgumentParser(
        description="Fetch NBA BoxScoreMatchupsV3 data for one game."
    )
    parser.add_argument("--game-id", required=True, help="10-digit NBA game ID")
    parser.add_argument(
        "--game-number",
        required=True,
        type=int,
        help="Game number within the series",
    )
    parser.add_argument(
        "--output",
        default=None,
        help=("Output CSV path. Defaults to data/api/<game_id>_matchups.csv"),
    )
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--retries", type=int, default=2)
    args = parser.parse_args()

    output = (
        Path(args.output)
        if args.output
        else Path("data/api") / f"{args.game_id}_matchups.csv"
    )

    raw = fetch_boxscore_matchups(
        args.game_id, timeout=args.timeout, retries=args.retries
    )
    raw_path = Path("data/raw") / f"{args.game_id}.csv"
    atomic_write(raw_path, raw.to_csv(index=False))
    normalized = normalize_boxscore_matchups(raw, args.game_number)

    cleaned, report = prepare_matchup_data(normalized)

    if report["errors"]:
        print("Validation failed:")
        for error in report["errors"]:
            print(f"  - {error}")
        raise SystemExit(1)

    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(output, normalized.to_csv(index=False))

    print(f"Fetched {len(normalized):,} matchup rows.")
    print(
        f"Teams: {', '.join(report['teams'])} | "
        f"Offensive players: {report['offensive_players']}"
    )
    print(f"Validation: {report['status'].upper()}")
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
