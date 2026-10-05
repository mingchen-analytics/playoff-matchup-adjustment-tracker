"""Evidence-backed API/manual parity check; never silently approve missing values."""

from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from data_pipeline import parse_matchup_time, prepare_matchup_data
from data_sources.nba_matchups import (
    fetch_boxscore_matchups,
    normalize_boxscore_matchups,
)

KEY_COLUMNS = ["Offense Player", "OFF Team", "Defense Player", "DEF Team"]
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
    c: 0.11
    for c in [
        "Partial Poss",
        "DEF Time Percent",
        "OFF Time Percent",
        "Both On Percent",
        "FG%",
        "3P%",
    ]
}


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def adapter_digest():
    return file_digest(
        Path(__file__).resolve().parents[1] / "data_sources/nba_matchups.py"
    )


def _clean_names(df):
    result = df.copy()
    for col in KEY_COLUMNS:
        result[col] = (
            result[col]
            .astype("string")
            .str.replace("\xa0", " ", regex=False)
            .str.strip()
        )
    return result


def compare_frames(manual, api):
    report = {
        "status": "fail",
        "manual_rows": len(manual),
        "api_rows": len(api),
        "failures": [],
        "checks": {},
        "differences": [],
    }
    for label, frame in [("manual", manual), ("api", api)]:
        required = set(KEY_COLUMNS + INTEGER_COLUMNS + list(FLOAT_TOLERANCES) + ["MIN"])
        if required - set(frame.columns):
            report["failures"].append(
                f"{label} missing columns: {sorted(required - set(frame.columns))}"
            )
        elif frame.empty:
            report["failures"].append(f"{label} contains no rows")
        else:
            _, quality = prepare_matchup_data(frame)
            report["failures"].extend(f"{label}: {e}" for e in quality["errors"])
    if report["failures"]:
        return report
    manual = _clean_names(manual)
    api = _clean_names(api)
    for label, frame in [("manual", manual), ("api", api)]:
        if frame.duplicated(KEY_COLUMNS).any():
            report["failures"].append(f"{label} contains duplicate matchup identities")
    if report["failures"]:
        return report
    merged = manual.merge(
        api,
        on=KEY_COLUMNS,
        how="outer",
        suffixes=("_manual", "_api"),
        indicator=True,
        validate="one_to_one",
    )
    counts = merged._merge.value_counts()
    report.update(
        matched_rows=int(counts.get("both", 0)),
        manual_only=int(counts.get("left_only", 0)),
        api_only=int(counts.get("right_only", 0)),
    )
    if report["manual_only"] or report["api_only"]:
        report["failures"].append("Unmatched matchup rows")
        report["unmatched"] = (
            merged.loc[merged._merge != "both", KEY_COLUMNS + ["_merge"]]
            .astype(str)
            .to_dict("records")
        )
    matched = merged[merged._merge == "both"]
    for col, tolerance in {
        "MIN": 1.1,
        **{c: 0.0 for c in INTEGER_COLUMNS},
        **FLOAT_TOLERANCES,
    }.items():
        left = matched[col + "_manual"]
        right = matched[col + "_api"]
        if col == "MIN":
            left = left.map(parse_matchup_time)
            right = right.map(parse_matchup_time)
        else:
            left = pd.to_numeric(left, errors="coerce")
            right = pd.to_numeric(right, errors="coerce")
        diff = (left - right).abs()
        bad = left.isna() | right.isna() | (diff > tolerance + 1e-9)
        report["checks"][col] = {
            "mismatches": int(bad.sum()),
            "tolerance": tolerance,
            "max_abs_difference": float(diff.max()) if diff.notna().any() else None,
        }
        if bad.any():
            report["failures"].append(f"{col}: {int(bad.sum())} mismatches")
            for idx in matched.index[bad]:
                record = {k: str(matched.loc[idx, k]) for k in KEY_COLUMNS}
                record.update(
                    column=col,
                    manual=str(matched.loc[idx, col + "_manual"]),
                    api=str(matched.loc[idx, col + "_api"]),
                )
                report["differences"].append(record)
    report["status"] = "fail" if report["failures"] else "pass"
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--game-id", required=True)
    p.add_argument("--game-number", required=True, type=int)
    p.add_argument("--manual-csv", default="data/OKC Spurs Matchup Data.csv")
    p.add_argument(
        "--raw-api-csv", help="Read a raw PlayerStats snapshot without network access"
    )
    p.add_argument("--report", default="data/api/verification.json")
    p.add_argument("--timeout", type=float, default=20)
    p.add_argument("--retries", type=int, default=2)
    args = p.parse_args()
    report = {
        "status": "blocked",
        "game_id": args.game_id,
        "game_number": args.game_number,
        "failures": [],
    }
    output = Path(args.report)
    try:
        manual = pd.read_csv(args.manual_csv)
        manual = manual[manual.Game == args.game_number]
        raw = (
            pd.read_csv(args.raw_api_csv, dtype={"gameId": str})
            if args.raw_api_csv
            else fetch_boxscore_matchups(
                args.game_id, timeout=args.timeout, retries=args.retries
            )
        )
        if not raw.gameId.astype(str).eq(args.game_id).all():
            raise ValueError("Raw API snapshot does not match requested game ID.")
        api = normalize_boxscore_matchups(raw, args.game_number)
        if not args.raw_api_csv:
            raw_path = Path("data/raw") / f"{args.game_id}.csv"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw.to_csv(raw_path, index=False)
        report.update(compare_frames(manual, api))
        report["raw_api_sha256"] = hashlib.sha256(
            raw.to_csv(index=False).encode("utf-8")
        ).hexdigest()
        report.update(
            manual_sha256=file_digest(args.manual_csv), adapter_sha256=adapter_digest()
        )
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        report["failures"] = [str(exc)]
    report["checked_at"] = datetime.now(timezone.utc).isoformat()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(f"API/manual verification: {report['status'].upper()}")
    print(
        f"Matched: {report.get('matched_rows', 0)} / manual {report.get('manual_rows', 0)} / API {report.get('api_rows', 0)}"
    )
    for issue in report["failures"]:
        print(f"- {issue}")
    print(f"Report: {output}")
    if report["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
