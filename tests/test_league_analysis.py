"""Phase 5 league analysis: definitions and wiring (offline, dev sample)."""

import numpy as np
import pandas as pd
import pytest

from research.league import (
    _two_sided,
    build_transitions,
    cluster_bootstrap,
    findings,
    load_dataset,
    player_outcomes,
    primary_players,
)


def boxes(rows):
    frame = pd.DataFrame(rows, columns=["player_id", "team", "game_number", "minutes",
                                        "points", "fga", "fta", "turnovers"])
    frame["series_id"] = "s"
    frame["game_id"] = "00425" + frame.game_number.astype(str)
    frame["played"] = True
    frame["minutes_seconds"] = frame.minutes * 60
    return frame


def test_primary_players_need_minutes_and_top_two_usage():
    data = boxes([
        (1, "A", 1, 36, 30, 22, 8, 3), (1, "A", 2, 38, 28, 20, 6, 4),
        (2, "A", 1, 34, 20, 15, 4, 2), (2, "A", 2, 33, 18, 14, 2, 2),
        (3, "A", 1, 25, 25, 25, 10, 5), (3, "A", 2, 26, 25, 25, 10, 5),  # high usage, too few minutes
        (4, "A", 1, 40, 4, 3, 0, 1), (4, "A", 2, 40, 4, 3, 0, 1),        # minutes, low usage
    ])
    roles = primary_players(data).set_index("player_id")
    assert roles.primary.to_dict() == {1: True, 2: False, 3: False, 4: False}
    assert roles.loc[3, "usage_rank"] == 1


def test_outcomes_compare_each_game_with_the_players_other_games():
    data = boxes([(1, "A", g, 36, p, 20, 0, 0) for g, p in [(1, 30), (2, 20), (3, 10)]])
    out = player_outcomes(data).set_index("game_number")
    assert out.loc[1, "pts36_dev"] == pytest.approx(30 - 15)
    assert out.loc[3, "ts_dev"] == pytest.approx(10 / 40 - 0.625)


def test_two_sided_adds_the_opponent_row():
    log = pd.DataFrame([{"SEASON_ID": "42025", "TEAM_ABBREVIATION": "OKC", "GAME_ID": "0042500311",
                         "GAME_DATE": "2026-05-18", "MATCHUP": "OKC vs. SAS", "WL": "L",
                         "PTS": 115, "PLUS_MINUS": -7}])
    both = _two_sided(log).set_index("TEAM_ABBREVIATION")
    assert both.loc["SAS", "WL"] == "W" and both.loc["SAS", "PTS"] == 122
    assert both.loc["SAS", "MATCHUP"] == "SAS @ OKC"


def test_cluster_bootstrap_brackets_the_estimate():
    table = pd.DataFrame({"series_id": np.repeat(list("abcdef"), 10),
                          "robust": np.tile([True, False], 30)})
    result = cluster_bootstrap(table, lambda f: float(f.robust.mean()), draws=200)
    assert result["estimate"] == pytest.approx(0.5)
    assert result["low"] <= 0.5 <= result["high"]


@pytest.fixture(scope="module")
def dev_table():
    source, bundles = load_dataset("dev")
    assert source == "dev"
    keep = [b for b in bundles if b[0] in {"2026_okc_sas_api_20261005", "2026_den_min_api_20261005"}]
    return build_transitions(keep, simulations=200)


def test_wembanyama_row_carries_context(dev_table):
    row = dev_table[(dev_table.off_player.eq("Victor Wembanyama"))
                    & dev_table.from_game.eq(1) & dev_table.to_game.eq(2)].iloc[0]
    assert row.def_team == "OKC" and row.def_lost_before  # SAS won Game 1
    assert row.primary and row.robust
    assert row.tvd == pytest.approx(0.6476, abs=1e-4)
    assert {"q_time", "q_poss", "blowout", "pts36_dev_after", "ts_dev_before"} <= set(dev_table.columns)


def test_findings_report_both_samples(dev_table):
    result = findings(dev_table, draws=50)
    assert result["series"] == 2
    assert set(result) >= {"all", "no_blowouts", "robust_rate_non_primary"}
    shares = [result["all"][f"share_{c}"]["estimate"] for c in ("overlap", "assignment", "entry_exit")]
    assert sum(shares) == pytest.approx(1.0)
