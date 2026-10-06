"""Phase 3 / 3.5: noise baselines on two bases, max-adjusted leaderboard, FDR.

    python -m research.run_noise_model [--simulations 4000] [--seed 20261005]

Primary basis: time shares (the statistic the project reports).
Robustness basis: possession shares, whose sampling unit matches the
multinomial draws. Assumptions are in analytics/null_model.py and
research/FINDINGS.md.
"""

import argparse
import json

import numpy as np
import pandas as pd

from analytics.measures import matchup_measures
from analytics.null_model import BASES, benjamini_hochberg, series_noise
from research.data import RESULTS, api_series_ids, load_matchups

# Filter used by the first, informal audit, kept to check it reproduces.
AUDIT_MIN_POSSESSIONS = 20
Q_THRESHOLD = 0.10
KEYS = ["series_id", "off_player_id", "from_game", "to_game"]
CASE = ("2026_okc_sas_api_20261005", "Victor Wembanyama", 1, 2)


def run_basis(basis, simulations, seed):
    transitions, leaderboards = [], []
    for offset, series_id in enumerate(api_series_ids()):
        measures = matchup_measures(load_matchups(series_id))
        table, board = series_noise(measures, simulations, seed + offset, basis=basis)
        table.insert(0, "series_id", series_id)
        board.insert(0, "series_id", series_id)
        transitions.append(table)
        leaderboards.append(board)
    transitions = pd.concat(transitions, ignore_index=True)
    leaderboards = pd.concat(leaderboards, ignore_index=True)
    transitions["q_value_league"] = benjamini_hochberg(transitions.p_value)
    leaderboards["q_value_league"] = benjamini_hochberg(leaderboards.p_value)
    leaderboards = leaderboards.sort_values("excess_largest_tvd", ascending=False)
    return transitions, leaderboards


def basis_summary(transitions, leaderboards):
    return {
        "transitions": int(len(transitions)),
        "transitions_high_noise_heuristic": int(transitions.high_noise.sum()),
        "transitions_spanning_missed_games": int((transitions.game_gap > 1).sum()),
        f"transitions_q_below_{Q_THRESHOLD}_league": int(
            (transitions.q_value_league < Q_THRESHOLD).sum()
        ),
        "players": int(len(leaderboards)),
        f"players_q_below_{Q_THRESHOLD}_league": int(
            (leaderboards.q_value_league < Q_THRESHOLD).sum()
        ),
        "players_largest_spans_missed_games": int(
            leaderboards.largest_spans_missed_games.sum()
        ),
    }


def compare_bases(time, poss):
    merged = time.merge(poss, on=KEYS, suffixes=("_time", "_poss"))
    t = merged.q_value_league_time < Q_THRESHOLD
    p = merged.q_value_league_poss < Q_THRESHOLD
    return merged, {
        "transitions_matched": int(len(merged)),
        "both_flag": int((t & p).sum()),
        "time_only": int((t & ~p).sum()),
        "possessions_only": int((~t & p).sum()),
        "neither": int((~t & ~p).sum()),
        "corr_excess_tvd": float(np.corrcoef(merged.excess_tvd_time, merged.excess_tvd_poss)[0, 1]),
        "corr_tvd": float(np.corrcoef(merged.tvd_time, merged.tvd_poss)[0, 1]),
    }


def audit_reproduction(transitions):
    audit = transitions[
        (transitions.possessions_before >= AUDIT_MIN_POSSESSIONS)
        & (transitions.possessions_after >= AUDIT_MIN_POSSESSIONS)
    ]
    smaller = np.minimum(audit.possessions_before, audit.possessions_after)
    return {
        "filter": f"both games >= {AUDIT_MIN_POSSESSIONS} possessions",
        "transitions": int(len(audit)),
        "median_observed_tvd": float(audit.tvd.median()),
        "median_null_tvd": float(audit.null_median.median()),
        "share_above_null_p95": float((audit.tvd > audit.null_p95).mean()),
        "corr_tvd_min_possessions": float(np.corrcoef(audit.tvd, smaller)[0, 1]),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulations", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=20261005)
    args = parser.parse_args()

    results = {basis: run_basis(basis, args.simulations, args.seed) for basis in BASES}
    RESULTS.mkdir(parents=True, exist_ok=True)
    time_tr, time_lb = results["time"]
    poss_tr, poss_lb = results["possessions"]
    time_tr.to_csv(RESULTS / "transition_noise.csv", index=False)
    time_lb.to_csv(RESULTS / "player_max_leaderboard.csv", index=False)
    poss_tr.to_csv(RESULTS / "transition_noise_possessions.csv", index=False)
    poss_lb.to_csv(RESULTS / "player_max_leaderboard_possessions.csv", index=False)
    merged, comparison = compare_bases(time_tr, poss_tr)
    merged.to_csv(RESULTS / "basis_comparison.csv", index=False)

    series_id, player, before, after = CASE
    case = merged[
        merged.series_id.eq(series_id) & merged.off_player_time.eq(player)
        & merged.from_game.eq(before) & merged.to_game.eq(after)
    ].iloc[0]
    summary = {
        "simulations": args.simulations,
        "seed": args.seed,
        "time_basis": basis_summary(time_tr, time_lb),
        "possession_basis": basis_summary(poss_tr, poss_lb),
        "basis_agreement_at_q_below_0.10": comparison,
        "case_wembanyama_g1_g2": {
            f"{field}_{basis}": float(case[f"{field}_{basis}"])
            for basis in ("time", "poss")
            for field in ("tvd", "null_median", "excess_tvd", "p_value", "q_value_league")
        },
        "audit_reproduction_time_basis": audit_reproduction(time_tr),
    }
    (RESULTS / "noise_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
