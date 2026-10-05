"""Phase 1: check the identities behind S, A and O for every bundled API series.

    python -m research.run_measure_audit
"""

import json

from analytics.measures import audit_measures
from research.data import RESULTS, api_series_ids, load_matchups, load_player_minutes


def main():
    report = {}
    for series_id in api_series_ids():
        report[series_id] = audit_measures(
            load_matchups(series_id), load_player_minutes(series_id)
        )
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "measure_audit.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    for series_id, row in report.items():
        print(
            f"{series_id}: off% sum median {row['off_time_percent_sum_median']:.1f}, "
            f"sumO/recorded median {row['sum_o_over_recorded_time_median']:.2f}, "
            f"O>court rows (>=30s) {row['o_exceeds_court_minutes_rows']}, small rows {row['o_exceeds_court_minutes_small_rows']}"
        )
    print(f"wrote {out.relative_to(RESULTS.parents[1])}")


if __name__ == "__main__":
    main()
