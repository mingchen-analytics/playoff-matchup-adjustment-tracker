"""Phase 2: rotation / assignment / entry-exit decomposition for every transition.

    python -m research.run_decomposition
"""

import json

import pandas as pd

from analytics.decomposition import decompose_series, decompose_transition
from analytics.measures import matchup_measures
from research.data import RESULTS, api_series_ids, load_matchups

CASE = ("2026_okc_sas_api_20261005", "Victor Wembanyama", 1, 2)


def main():
    frames = []
    for series_id in api_series_ids():
        table = decompose_series(matchup_measures(load_matchups(series_id)))
        table.insert(0, "series_id", series_id)
        frames.append(table)
    transitions = pd.concat(frames, ignore_index=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    transitions.to_csv(RESULTS / "decomposition_transitions.csv", index=False)

    series_id, player, before, after = CASE
    measures = matchup_measures(load_matchups(series_id))
    detail, summary = decompose_transition(
        measures[measures.off_player.eq(player)], before, after
    )
    detail.to_csv(RESULTS / "case_wembanyama_g1_g2.csv", index=False)
    (RESULTS / "case_wembanyama_g1_g2.json").write_text(
        json.dumps({"series_id": series_id, "player": player, **summary}, indent=2) + "\n"
    )
    print(f"{len(transitions)} transitions decomposed")
    print({k: round(v, 3) for k, v in summary.items() if isinstance(v, float)})


if __name__ == "__main__":
    main()
