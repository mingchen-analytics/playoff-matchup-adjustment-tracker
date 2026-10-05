"""Phase 3: noise baselines, max-adjusted leaderboard and league-level FDR.

    python -m research.run_noise_model [--simulations 4000] [--seed 20261005]

Assumptions are documented in analytics/null_model.py and research/FINDINGS.md.
"""

import argparse
import json

import numpy as np
import pandas as pd

from analytics.measures import matchup_measures
from analytics.null_model import benjamini_hochberg, series_noise
from research.data import RESULTS, api_series_ids, load_matchups

# Filter used by the first, informal audit, kept to check it reproduces.
AUDIT_MIN_POSSESSIONS = 20


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulations", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=20261005)
    args = parser.parse_args()

    transitions, leaderboards = [], []
    for offset, series_id in enumerate(api_series_ids()):
        measures = matchup_measures(load_matchups(series_id))
        table, board = series_noise(measures, args.simulations, args.seed + offset)
        table.insert(0, "series_id", series_id)
        board.insert(0, "series_id", series_id)
        transitions.append(table)
        leaderboards.append(board)
    transitions = pd.concat(transitions, ignore_index=True)
    leaderboards = pd.concat(leaderboards, ignore_index=True)
    transitions["q_value_league"] = benjamini_hochberg(transitions.p_value)
    leaderboards["q_value_league"] = benjamini_hochberg(leaderboards.p_value)
    leaderboards = leaderboards.sort_values("excess_largest_tvd", ascending=False)

    RESULTS.mkdir(parents=True, exist_ok=True)
    transitions.to_csv(RESULTS / "transition_noise.csv", index=False)
    leaderboards.to_csv(RESULTS / "player_max_leaderboard.csv", index=False)

    audit = transitions[
        (transitions.possessions_before >= AUDIT_MIN_POSSESSIONS)
        & (transitions.possessions_after >= AUDIT_MIN_POSSESSIONS)
    ]
    smaller = np.minimum(audit.possessions_before, audit.possessions_after)
    summary = {
        "simulations": args.simulations,
        "seed": args.seed,
        "transitions": int(len(transitions)),
        "transitions_uncertain": int(transitions.uncertain.sum()),
        "transitions_spanning_missed_games": int((transitions.game_gap > 1).sum()),
        "players_largest_spans_missed_games": int(leaderboards.largest_spans_missed_games.sum()),
        "transitions_q_below_0_10_league": int((transitions.q_value_league < 0.10).sum()),
        "players": int(len(leaderboards)),
        "players_q_below_0_10_league": int((leaderboards.q_value_league < 0.10).sum()),
        "audit_reproduction": {
            "filter": f"both games >= {AUDIT_MIN_POSSESSIONS} possessions",
            "transitions": int(len(audit)),
            "median_observed_tvd": float(audit.tvd.median()),
            "median_null_tvd": float(audit.null_median.median()),
            "share_above_null_p95": float((audit.tvd > audit.null_p95).mean()),
            "corr_tvd_min_possessions": float(np.corrcoef(audit.tvd, smaller)[0, 1]),
        },
    }
    (RESULTS / "noise_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(leaderboards.head(10)[
        ["series_id", "off_player", "largest_transition", "largest_tvd",
         "null_max_median", "excess_largest_tvd", "q_value_league"]
    ].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
