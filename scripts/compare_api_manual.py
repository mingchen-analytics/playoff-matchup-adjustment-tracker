"""Compare NBA API matchup data with the manually collected project CSV."""

from __future__ import annotations

import argparse

import pandas as pd

from data_pipeline import parse_matchup_time
from data_sources.nba_matchups import fetch_and_normalize_game


KEY_COLUMNS = [
    "Offense Player",
    "OFF Team",
    "Defense Player",
    "DEF Team",
]

INTEGER_COLUMNS = [
    "Players PTS",
    "Team PTS",
    "AST",
    "TOV",
    "BLK",
    "FGM",
    "FGA",
    "3PM",
    "3PA",
    "FTM",
    "FTA",
    "SFL",
]

FLOAT_TOLERANCES = {
    "Partial Poss": 0.11,
    "DEF Time Percent": 0.11,
    "OFF Time Percent": 0.11,
    "Both On Percent": 0.11,
    "FG%": 0.11,
    "3P%": 0.11,
}


def _clean_names(df):
    result = df.copy()
    for column in KEY_COLUMNS:
        result[column] = (
            result[column]
            .astype(str)
            .str.replace("\xa0", " ", regex=False)
            .str.strip()
        )
    return result


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Fetch one NBA game and compare it with a game from the "
            "manually collected matchup CSV."
        )
    )
    parser.add_argument("--game-id", required=True)
    parser.add_argument("--game-number", required=True, type=int)
    parser.add_argument(
        "--manual-csv",
        default="data/OKC Spurs Matchup Data.csv",
    )
    args = parser.parse_args()

    manual = pd.read_csv(args.manual_csv)
    manual = manual[manual["Game"] == args.game_number].copy()

    api = fetch_and_normalize_game(
        game_id=args.game_id,
        game_number=args.game_number,
    )

    manual = _clean_names(manual)
    api = _clean_names(api)

    manual["_matchup_seconds"] = manual["MIN"].map(parse_matchup_time)
    api["_matchup_seconds"] = api["MIN"].map(parse_matchup_time)

    merged = manual.merge(
        api,
        on=KEY_COLUMNS,
        how="outer",
        suffixes=("_manual", "_api"),
        indicator=True,
    )

    matched = merged[merged["_merge"] == "both"].copy()
    only_manual = merged[merged["_merge"] == "left_only"]
    only_api = merged[merged["_merge"] == "right_only"]

    print("=== ROW MATCHING ===")
    print(f"Manual rows: {len(manual)}")
    print(f"API rows:    {len(api)}")
    print(f"Matched:     {len(matched)}")
    print(f"Manual only: {len(only_manual)}")
    print(f"API only:    {len(only_api)}")

    failures = []

    if len(only_manual):
        failures.append(f"{len(only_manual)} matchup rows appear only in manual data")

    if len(only_api):
        failures.append(f"{len(only_api)} matchup rows appear only in API data")

    if not matched.empty:
        time_diff = (
            matched["_matchup_seconds_manual"]
            - matched["_matchup_seconds_api"]
        ).abs()
        bad_time = int((time_diff > 1.1).sum())
        print(f"Matchup time >1.1 sec difference: {bad_time}")
        if bad_time:
            failures.append(f"{bad_time} rows differ in matchup time")

        print("\n=== VALUE CHECKS ===")

        for column in INTEGER_COLUMNS:
            manual_col = f"{column}_manual"
            api_col = f"{column}_api"

            if manual_col not in matched or api_col not in matched:
                continue

            diff = (
                pd.to_numeric(matched[manual_col], errors="coerce")
                - pd.to_numeric(matched[api_col], errors="coerce")
            ).abs()
            bad = int((diff > 0).sum())
            print(f"{column}: {bad} mismatched rows")
            if bad:
                failures.append(f"{column}: {bad} mismatched rows")

        for column, tolerance in FLOAT_TOLERANCES.items():
            manual_col = f"{column}_manual"
            api_col = f"{column}_api"

            if manual_col not in matched or api_col not in matched:
                continue

            diff = (
                pd.to_numeric(matched[manual_col], errors="coerce")
                - pd.to_numeric(matched[api_col], errors="coerce")
            ).abs()
            bad = int((diff > tolerance).sum())
            max_diff = float(diff.max()) if len(diff) else 0.0
            print(
                f"{column}: {bad} outside tolerance "
                f"(max abs diff {max_diff:.3f})"
            )
            if bad:
                failures.append(
                    f"{column}: {bad} rows outside ±{tolerance}"
                )

    if failures:
        print("\n=== RESULT: DIFFERENCES FOUND ===")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)

    print("\n=== RESULT: API MATCHES MANUAL GAME DATA ===")


if __name__ == "__main__":
    main()
