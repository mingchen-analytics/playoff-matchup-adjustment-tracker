"""Phase 4: acquire every playoff game for a range of seasons (run locally).

NBA Stats blocks most cloud/CI networks, so run this on your own computer:

    pip install -r requirements.txt -r requirements-data.txt

    # 1. Which seasons have matchup data? (one request pair per season)
    python -m scripts.fetch_playoffs --probe --seasons 2013-14:2025-26

    # 2. Acquire the seasons that returned rows (resumable; rerun after errors)
    python -m scripts.fetch_playoffs --seasons 2017-18:2025-26

    # 3. Rebuild the outputs from caches only, no network
    python -m scripts.fetch_playoffs --seasons 2017-18:2025-26 --offline

Raw responses are cached under data/league/raw/ (git-ignored). Outputs and
fetch_report.json go to data/league/. Then run the league analysis:

    python -m research.run_league
"""

import argparse
import json
import sys
from pathlib import Path

from data_sources.league_fetch import LeagueFetcher, check_season, live_fetchers, probe

ROOT = Path(__file__).resolve().parents[1]


def season_range(text):
    seasons = []
    for part in text.split(","):
        part = part.strip()
        if ":" in part:
            first, last = (check_season(p) for p in part.split(":"))
            for start in range(int(first[:4]), int(last[:4]) + 1):
                seasons.append(f"{start}-{(start + 1) % 100:02d}")
        else:
            seasons.append(check_season(part))
    if not seasons:
        raise argparse.ArgumentTypeError("No seasons given.")
    return seasons


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seasons", type=season_range, required=True,
                        help="e.g. 2017-18:2025-26 or 2023-24,2024-25")
    parser.add_argument("--probe", action="store_true",
                        help="Only check which seasons return matchup rows.")
    parser.add_argument("--offline", action="store_true",
                        help="Use cached raw responses only.")
    parser.add_argument("--interval", type=float, default=2.0,
                        help="Seconds between NBA requests (default 2).")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--max-games", type=int, default=None,
                        help="Stop after this many games (for a trial run).")
    args = parser.parse_args(argv)

    game_log, matchups, boxscore = live_fetchers(args.timeout, args.retries)
    if args.probe:
        result = probe(args.seasons, game_log, matchups)
        print(json.dumps(result, indent=2))
        return 0
    report = LeagueFetcher(
        ROOT, game_log, matchups, boxscore,
        request_interval=args.interval, offline=args.offline,
    ).run(args.seasons, max_games=args.max_games)
    failed = len(report["failed_games"])
    print(json.dumps({k: report[k] for k in ("seasons", "rows")}, indent=2))
    if failed:
        print(f"{failed} games failed; see data/league/fetch_report.json. "
              "Rerun the same command to retry only those games.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
