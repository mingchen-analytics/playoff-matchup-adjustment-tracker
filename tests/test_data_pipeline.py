import pandas as pd

from data_pipeline import (
    parse_matchup_time,
    prepare_matchup_data,
)


def make_valid_data():
    return pd.DataFrame({
        "Game": [1, 1],
        "Offense Player": ["Player A", "Player A"],
        "OFF Team": ["AAA", "AAA"],
        "Defense Player": ["Defender A", "Defender B"],
        "DEF Team": ["BBB", "BBB"],
        "MIN": ["01:00", "00:40"],
        "Partial Poss": [5.0, 4.0],
        "Players PTS": [4, 2],
        "Team PTS": [8, 6],
        "AST": [1, 0],
        "TOV": [0, 1],
        "BLK": [0, 0],
        "FGM": [2, 1],
        "FGA": [3, 2],
        "3PM": [0, 0],
        "3PA": [1, 1],
        "FTM": [0, 0],
        "FTA": [0, 0],
        "SFL": [0, 0],
    })


def test_parse_matchup_time_mm_ss():
    assert parse_matchup_time("08:18") == 498


def test_valid_data_passes_validation():
    cleaned, report = prepare_matchup_data(make_valid_data())

    assert report["status"] == "pass"
    assert report["errors"] == []
    assert cleaned["matchup_seconds"].tolist() == [60, 40]


def test_missing_required_column_fails_validation():
    data = make_valid_data().drop(columns=["FGA"])

    _, report = prepare_matchup_data(data)

    assert report["status"] == "fail"
    assert any("Missing required columns" in error for error in report["errors"])


def test_invalid_matchup_time_fails_validation():
    data = make_valid_data()
    data.loc[0, "MIN"] = "1:75"

    _, report = prepare_matchup_data(data)

    assert report["status"] == "fail"
    assert any("Invalid matchup time" in error for error in report["errors"])


def test_negative_numeric_value_fails_validation():
    data = make_valid_data()
    data.loc[0, "FGA"] = -1

    _, report = prepare_matchup_data(data)

    assert report["status"] == "fail"
    assert any("Negative fga" in error for error in report["errors"])


def test_exact_duplicate_row_fails_validation():
    row = make_valid_data().iloc[[0]]
    data = pd.concat([row, row], ignore_index=True)

    _, report = prepare_matchup_data(data)

    assert report["status"] == "fail"
    assert any("Exact duplicate rows" in error for error in report["errors"])
