"""Measurement research: S/A/O, adjustment decomposition and the noise model.

Simulation properties from the upgrade plan:
(a) unchanged allocation -> excess TVD near 0 and calibrated p-values
(b) only overlap opportunity changes -> assignment contribution 0
(c) only assignment rates change -> overlap (rotation) contribution 0
(d) a deliberate primary-defender swap is detected
"""

import numpy as np
import pandas as pd
import pytest

from analytics.decomposition import COMPONENTS, decompose_series, decompose_transition
from analytics.measures import audit_measures, matchup_measures
from analytics.null_model import (
    benjamini_hochberg,
    player_max_noise,
    series_noise,
    transition_noise,
)
from research.data import load_matchups


def snapshot(rows, possessions=60.0, off_player_id=1):
    """rows: (game, defender_id, overlap_seconds, assignment_rate)."""
    frame = pd.DataFrame(rows, columns=["game_number", "def_player_id", "O", "A"])
    frame["matchup_seconds"] = frame.O * frame.A
    total = frame.groupby("game_number").matchup_seconds.transform("sum")
    count = frame.groupby("game_number").matchup_seconds.transform("size")
    return pd.DataFrame({
        "game_number": frame.game_number,
        "off_player_id": off_player_id,
        "off_player": f"Player {off_player_id}",
        "off_team": "OFF",
        "def_player_id": frame.def_player_id,
        "def_player": "D" + frame.def_player_id.astype(str),
        "matchup_seconds": frame.matchup_seconds,
        "partial_possessions": possessions / count,
        "both_on_percent": frame.A * 100,
        "off_time_percent": frame.matchup_seconds / total * 100,
        "def_time_percent": 100.0,
    })


BASE = [(1, 10, 600, 0.6), (1, 11, 500, 0.3), (1, 12, 400, 0.1)]


def test_measures_reconstruct_matchup_seconds_and_shares():
    m = matchup_measures(snapshot(BASE))
    assert m.groupby("game_number").S.sum().tolist() == pytest.approx([1.0])
    assert (m.O * m.A).to_numpy() == pytest.approx(m.M.to_numpy())
    assert m.O.tolist() == pytest.approx([600, 500, 400])
    assert m.measurable.all()


def test_assignment_rounded_to_zero_is_unmeasurable_not_infinite():
    data = snapshot(BASE)
    data.loc[2, "both_on_percent"] = 0.0
    m = matchup_measures(data)
    assert not m.measurable.iloc[2]
    assert np.isnan(m.O.iloc[2]) and m.S.iloc[2] > 0


@pytest.mark.parametrize("problem", ["duplicate", "two_series", "missing"])
def test_measures_reject_invalid_input(problem):
    data = snapshot(BASE)
    if problem == "duplicate":
        data = pd.concat([data, data.iloc[[0]]])
    elif problem == "two_series":
        data["series_id"] = ["a", "a", "b"]
    else:
        data = data.drop(columns="both_on_percent")
    with pytest.raises(ValueError):
        matchup_measures(data)


def test_audit_identities_hold_for_consistent_data():
    result = audit_measures(snapshot(BASE), min_total_seconds=0)
    assert result["off_time_percent_sum_median"] == pytest.approx(100)
    assert result["s_vs_off_time_percent_max_abs_pp"] == pytest.approx(0, abs=1e-9)
    assert result["sum_o_over_recorded_time_median"] == pytest.approx(1500 / 550)


def transition(rows):
    m = matchup_measures(snapshot(rows))
    return decompose_transition(m, 1, 2)


def assert_additive(detail, summary):
    parts = detail[list(COMPONENTS)].sum(axis=1)
    assert parts.to_numpy() == pytest.approx(detail.share_change.to_numpy())
    assert sum(summary[k] for k in COMPONENTS) == pytest.approx(summary["tvd"])


def test_identical_games_decompose_to_zero():
    detail, summary = transition(BASE + [(2, d, o, a) for _, d, o, a in BASE])
    assert summary["tvd"] == pytest.approx(0)
    assert all(summary[k] == pytest.approx(0) for k in COMPONENTS)


def test_property_b_overlap_only_change_has_no_assignment_effect():
    after = [(2, 10, 200, 0.6), (2, 11, 900, 0.3), (2, 12, 400, 0.1)]
    detail, summary = transition(BASE + after)
    assert summary["tvd"] > 0.1
    assert summary["assignment"] == pytest.approx(0, abs=1e-12)
    assert summary["entry_exit"] == pytest.approx(0, abs=1e-12)
    assert summary["overlap"] == pytest.approx(summary["tvd"])
    assert_additive(detail, summary)


def test_property_c_assignment_only_change_has_no_overlap_effect():
    after = [(2, 10, 600, 0.1), (2, 11, 500, 0.7), (2, 12, 400, 0.2)]
    detail, summary = transition(BASE + after)
    assert summary["tvd"] > 0.1
    assert summary["overlap"] == pytest.approx(0, abs=1e-12)
    assert summary["assignment"] == pytest.approx(summary["tvd"])
    assert_additive(detail, summary)


def test_longer_game_alone_is_not_an_overlap_effect():
    after = [(2, d, o * 58 / 48, a) for _, d, o, a in BASE]
    _, summary = transition(BASE + after)
    assert summary["tvd"] == pytest.approx(0, abs=1e-12)


def test_new_defender_is_entry_exit_and_effects_stay_additive():
    after = [(2, 10, 300, 0.4), (2, 11, 500, 0.3), (2, 12, 400, 0.1), (2, 13, 500, 0.5)]
    detail, summary = transition(BASE + after)
    newcomer = detail.set_index("def_player_id").loc[13]
    assert not newcomer.comparable
    assert newcomer.entry_exit == pytest.approx(newcomer.share_change)
    assert summary["entry_exit"] > 0
    assert_additive(detail, summary)


def test_wembanyama_api_case_is_reproduced():
    m = matchup_measures(load_matchups("2026_okc_sas_api_20261005"))
    player = m[m.off_player.eq("Victor Wembanyama")]
    detail, summary = decompose_transition(player, 1, 2)
    assert summary["tvd"] == pytest.approx(0.6476, abs=1e-4)
    assert summary["overlap"] == pytest.approx(0.3097, abs=1e-4)
    assert summary["coverage"] == pytest.approx(0.979, abs=1e-3)
    assert not summary["low_coverage"]
    assert summary["assignment"] == pytest.approx(0.3330, abs=1e-4)
    hartenstein = detail.set_index("def_player").loc["Isaiah Hartenstein"]
    assert hartenstein.share_change == pytest.approx(0.567, abs=1e-3)
    assert_additive(detail, summary)
    assert len(decompose_series(m)) == 140


def draws(shares, possessions, rng, game, player=1):
    counts = rng.multinomial(possessions, shares)
    rows = [(game, d, float(c) + 1e-9, 0.5) for d, c in enumerate(counts) if c > 0]
    return rows


def test_property_a_null_data_gives_small_excess_and_calibrated_p():
    rng = np.random.default_rng(7)
    shares = np.array([0.45, 0.30, 0.15, 0.10])
    excess, p = [], []
    for _ in range(300):
        rows = draws(shares, 60, rng, 1) + draws(shares, 60, rng, 2)
        result = transition_noise(matchup_measures(snapshot(rows)), 500, rng)
        excess.append(result.excess_tvd[0])
        p.append(result.p_value[0])
    assert abs(np.mean(excess)) < 0.02
    assert 0.01 <= np.mean(np.array(p) < 0.05) <= 0.10


def test_property_d_primary_swap_is_detected():
    rng = np.random.default_rng(3)
    rows = draws(np.array([0.7, 0.2, 0.1]), 60, rng, 1) + draws(
        np.array([0.1, 0.2, 0.7]), 60, rng, 2
    )
    result = transition_noise(matchup_measures(snapshot(rows)), 2000, rng)
    assert result.p_value[0] < 0.01
    assert result.excess_tvd[0] > 0.3
    assert not result.high_noise[0]


def test_small_samples_get_the_high_noise_heuristic_flag():
    rows = [(1, 10, 2, 1.0), (1, 11, 1, 1.0), (2, 10, 1, 1.0), (2, 11, 2, 1.0)]
    result = transition_noise(matchup_measures(snapshot(rows, possessions=3)), 500, 0)
    assert result.high_noise[0]


def test_max_null_is_stricter_than_single_transition_null():
    rng = np.random.default_rng(11)
    shares = np.array([0.5, 0.3, 0.2])
    rows = sum((draws(shares, 50, rng, g) for g in range(1, 8)), [])
    m = matchup_measures(snapshot(rows))
    single = transition_noise(m, 2000, 1)
    best = player_max_noise(m, 2000, 1)
    assert best["largest_tvd"] == pytest.approx(single.tvd.max())
    assert best["null_max_median"] > single.null_median.median()


def test_benjamini_hochberg_matches_hand_calculation():
    q = benjamini_hochberg([0.01, 0.04, 0.03, 0.5])
    assert q.tolist() == pytest.approx([0.04, 0.16 / 3, 0.16 / 3, 0.5])


def test_series_noise_is_reproducible_with_a_seed():
    m = matchup_measures(load_matchups("2026_okc_sas_api_20261005"))
    first = series_noise(m, simulations=300, seed=5)
    second = series_noise(m, simulations=300, seed=5)
    pd.testing.assert_frame_equal(first[0], second[0])
    pd.testing.assert_frame_equal(first[1], second[1])
    assert first[1].excess_largest_tvd.is_monotonic_decreasing


def test_low_comparable_coverage_is_flagged():
    after = [(2, 10, 300, 0.2), (2, 13, 600, 0.9), (2, 14, 500, 0.8)]
    detail, summary = transition(BASE + after)
    assert summary["coverage"] < 0.8 and summary["low_coverage"]
    assert_additive(detail, summary)


def test_constant_scale_error_in_assignment_rates_does_not_move_the_split():
    after = [(2, 10, 200, 0.5), (2, 11, 900, 0.4), (2, 12, 400, 0.1)]
    _, clean = transition(BASE + after)
    data = snapshot(BASE + after)
    data.loc[data.game_number.eq(2), "both_on_percent"] *= 0.9
    m = matchup_measures(data)
    _, scaled = decompose_transition(m, 1, 2)
    for key in COMPONENTS:
        assert scaled[key] == pytest.approx(clean[key])


def test_audit_detects_a_per_game_percentage_scale_mismatch():
    data = snapshot(BASE + [(2, d, o, a) for _, d, o, a in BASE])
    data.loc[data.game_number.eq(2), "off_time_percent"] *= 1.1
    result = audit_measures(data, min_total_seconds=0)
    assert result["off_time_percent_scale_games"] == [2]
    assert result["off_time_percent_scale_max"] == pytest.approx(1.1)
    assert result["normalized_off_time_percent_vs_s_max_pp_affected_games"] == pytest.approx(0, abs=1e-9)


def test_possession_basis_uses_partial_possession_shares():
    rows = snapshot(BASE + [(2, d, o, a) for _, d, o, a in BASE])
    rows["partial_possessions"] = [30, 20, 10, 10, 20, 30]
    m = matchup_measures(rows)
    time = transition_noise(m, 500, 0)
    poss = transition_noise(m, 500, 0, basis="possessions")
    assert time.tvd[0] == pytest.approx(0)
    assert poss.tvd[0] == pytest.approx(1 / 3)
    with pytest.raises(ValueError):
        transition_noise(m, 10, 0, basis="minutes")


def test_property_a_holds_on_the_possession_basis():
    rng = np.random.default_rng(13)
    shares = np.array([0.5, 0.3, 0.2])
    p = []
    for _ in range(200):
        rows = draws(shares, 60, rng, 1) + draws(shares, 60, rng, 2)
        data = snapshot(rows)
        data["partial_possessions"] = data.matchup_seconds * 2  # draws use A = 0.5
        result = transition_noise(matchup_measures(data), 400, rng, basis="possessions")
        p.append(result.p_value[0])
    assert 0.01 <= np.mean(np.array(p) < 0.05) <= 0.10
