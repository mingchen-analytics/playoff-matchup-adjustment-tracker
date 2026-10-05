"""Publish an existing verified discovery cache for offline game context."""

import argparse
from pathlib import Path

from game_context import load_game_context
from series_ingestion import atomic_write
from series_manifest import load_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--game-log-csv", type=Path, required=True)
    parser.add_argument(
        "--project-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args()
    try:
        manifest = load_manifest(args.manifest)
        context = load_game_context(
            manifest, args.project_root, source_path=args.game_log_csv
        )
        target = args.project_root / "data/context" / f"{manifest.series_id}.csv"
        text = args.game_log_csv.read_text(encoding="utf-8")
        if target.exists() and target.read_text(encoding="utf-8") != text:
            raise ValueError("Published context already exists with different content.")
        atomic_write(target, text)
        print(f"Published {len(context)} validated game results: {target}")
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Game context publication failed: {exc}\n")


if __name__ == "__main__":
    main()
