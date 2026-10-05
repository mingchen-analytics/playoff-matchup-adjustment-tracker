import pandas as pd
import pytest

from analytics.metrics import (
    calculate_adjustment_scores,
    calculate_matchup_concentration,
)


def test_adjustment_score_identical_distribution_is_zero():
    data = pd.DataFrame({
        "game": [1, 1, 2, 2],
        "defense_player": ["A", "B", "A", "B"],
        "matchup_seconds": [60, 40, 120, 80],
    })

    result = calculate_adjustment_scores(data)

    assert len(result) == 1
    assert result.loc[0, "Adjustment Score"] == pytest.approx(0.0)


def test_adjustment_score_complete_redistribution_is_one():
    data = pd.DataFrame({
        "game": [1, 2],
        "defense_player": ["A", "B"],
        "matchup_seconds": [100, 100],
    })

    result = calculate_adjustment_scores(data)

    assert result.loc[0, "Adjustment Score"] == pytest.approx(1.0)


def test_concentration_equal_two_defenders():
    data = pd.DataFrame({
        "game": [1, 1],
        "defense_player": ["A", "B"],
        "matchup_seconds": [50, 50],
    })

    result = calculate_matchup_concentration(data)

    assert result.loc[0, "Primary Share %"] == pytest.approx(50.0)
    assert result.loc[0, "Top-2 Share %"] == pytest.approx(100.0)
    assert result.loc[0, "HHI"] == pytest.approx(0.5)
    assert result.loc[0, "Effective Defenders"] == pytest.approx(2.0)
