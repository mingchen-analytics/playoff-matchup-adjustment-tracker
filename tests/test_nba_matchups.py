import pandas as pd
import pytest

from data_sources.nba_matchups import normalize_boxscore_matchups


def make_api_frame():
    return pd.DataFrame(
        {
            "gameId": ["0042500311", "0042500311"],
            "teamTricode": ["OKC", "SAS"],
            "personIdOff": [1, 2],
            "firstNameOff": ["Shai", "Victor"],
            "familyNameOff": ["Gilgeous-Alexander", "Wembanyama"],
            "personIdDef": [3, 4],
            "firstNameDef": ["Stephon", "Chet"],
            "familyNameDef": ["Castle", "Holmgren"],
            "matchupMinutes": ["1:05", "0:17"],
            "partialPossessions": [6.2, 1.5],
            "percentageDefenderTotalTime": [0.141, 0.086],
            "percentageOffensiveTotalTime": [0.021, 0.112],
            "percentageTotalTimeBothOn": [0.141, 0.125],
            "switchesOn": [2, 1],
            "playerPoints": [4, 2],
            "teamPoints": [8, 6],
            "matchupAssists": [1, 0],
            "matchupPotentialAssists": [2, 1],
            "matchupTurnovers": [0, 1],
            "matchupBlocks": [0, 0],
            "matchupFieldGoalsMade": [2, 1],
            "matchupFieldGoalsAttempted": [4, 2],
            "matchupFieldGoalsPercentage": [0.5, 0.5],
            "matchupThreePointersMade": [1, 0],
            "matchupThreePointersAttempted": [2, 1],
            "matchupThreePointersPercentage": [0.5, 0.0],
            "helpBlocks": [0, 1],
            "helpFieldGoalsMade": [0, 0],
            "helpFieldGoalsAttempted": [1, 0],
            "matchupFreeThrowsMade": [0, 0],
            "matchupFreeThrowsAttempted": [0, 0],
            "shootingFouls": [1, 0],
        }
    )


def test_normalize_boxscore_matchups_maps_teams_and_names():
    result = normalize_boxscore_matchups(make_api_frame(), game_number=1)

    first = result.iloc[0]
    second = result.iloc[1]

    assert first["Offense Player"] == "Shai Gilgeous-Alexander"
    assert first["OFF Team"] == "OKC"
    assert first["Defense Player"] == "Stephon Castle"
    assert first["DEF Team"] == "SAS"

    assert second["Offense Player"] == "Victor Wembanyama"
    assert second["OFF Team"] == "SAS"
    assert second["DEF Team"] == "OKC"


def test_normalize_boxscore_matchups_matches_display_scales():
    result = normalize_boxscore_matchups(make_api_frame(), game_number=1)
    first = result.iloc[0]

    assert first["MIN"] == "01:05"
    assert first["DEF Time Percent"] == pytest.approx(14.1)
    assert first["FG%"] == pytest.approx(50.0)
    assert first["3P%"] == pytest.approx(50.0)


def test_normalize_boxscore_matchups_retains_extra_api_context():
    result = normalize_boxscore_matchups(make_api_frame(), game_number=1)
    first = result.iloc[0]

    assert first["Game ID"] == "0042500311"
    assert first["OFF Player ID"] == 1
    assert first["DEF Player ID"] == 3
    assert first["Switches On"] == 2
    assert first["Potential AST"] == 2


def test_normalize_boxscore_matchups_requires_two_teams():
    data = make_api_frame()
    data["teamTricode"] = "SAS"

    with pytest.raises(ValueError, match="exactly two teams"):
        normalize_boxscore_matchups(data, game_number=1)


def test_fetch_retries_are_bounded_and_empty_responses_fail(monkeypatch):
    import sys
    from types import ModuleType, SimpleNamespace
    from data_sources.nba_matchups import fetch_boxscore_matchups
    import data_sources.nba_matchups as adapter

    endpoints = ModuleType("nba_api.stats.endpoints")
    calls = []

    def fake_endpoint(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise TimeoutError("fixture timeout")
        return SimpleNamespace(
            player_stats=SimpleNamespace(get_data_frame=make_api_frame)
        )

    endpoints.boxscorematchupsv3 = SimpleNamespace(BoxScoreMatchupsV3=fake_endpoint)
    monkeypatch.setitem(sys.modules, "nba_api", ModuleType("nba_api"))
    monkeypatch.setitem(sys.modules, "nba_api.stats", ModuleType("nba_api.stats"))
    monkeypatch.setitem(sys.modules, "nba_api.stats.endpoints", endpoints)
    monkeypatch.setattr(adapter.time, "sleep", lambda delay: None)
    frame = fetch_boxscore_matchups("0042500311", timeout=1, retries=2)
    assert len(frame) == 2 and len(calls) == 2

    def empty(**kwargs):
        return SimpleNamespace(
            player_stats=SimpleNamespace(get_data_frame=lambda: pd.DataFrame())
        )

    endpoints.boxscorematchupsv3 = SimpleNamespace(BoxScoreMatchupsV3=empty)
    with pytest.raises(RuntimeError, match="after 2 attempts"):
        fetch_boxscore_matchups("0042500311", timeout=1, retries=2)
