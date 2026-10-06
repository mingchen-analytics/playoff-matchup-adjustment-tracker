"""Phase 4 league acquisition: discovery, resumable caching, normalization (offline)."""

import json
from pathlib import Path

import pandas as pd
import pytest

from data_sources.league_fetch import (
    LeagueFetcher,
    discover_playoff_games,
    normalize_matchups,
    percentage_scale,
)
from data_sources.nba_matchups import API_REQUIRED_COLUMNS
from scripts.fetch_playoffs import season_range

FIXTURE = Path(__file__).parent / "fixtures" / "0042500311_traditional.json"


def game_log():
    rows = []
    for game_id, date, home, away, home_pts, away_pts in [
        ("0042500311", "2026-05-18", "OKC", "SAS", 115, 122),
        ("0042500312", "2026-05-20", "OKC", "SAS", 120, 101),
        ("0042500121", "2026-04-19", "DEN", "MIN", 110, 100),
        ("0052500101", "2026-04-15", "MIA", "CHI", 99, 98),  # play-in: excluded
    ]:
        for team, other, pts, opp, sep in [(home, away, home_pts, away_pts, "vs."),
                                           (away, home, away_pts, home_pts, "@")]:
            rows.append({
                "SEASON_ID": "42025", "TEAM_ABBREVIATION": team, "GAME_ID": game_id,
                "GAME_DATE": date, "MATCHUP": f"{team} {sep} {other}",
                "WL": "W" if pts > opp else "L", "PTS": pts, "PLUS_MINUS": pts - opp,
            })
    log = pd.DataFrame(rows)
    return pd.concat([log, log.iloc[[0]]])  # endpoint duplicates are tolerated


def teams_for(game_id):
    return ("MIN", "DEN") if game_id.startswith("00425001") else ("SAS", "OKC")


def raw_matchups(game_id, off_ids=(1641705, 1630170), def_ids=(1631114, 1628392)):
    offense, defense = teams_for(game_id)
    rows = []
    for off in off_ids:
        for i, d in enumerate(def_ids):
            row = {c: 0 for c in API_REQUIRED_COLUMNS}
            row.update({
                "gameId": game_id, "teamTricode": offense, "personIdOff": off,
                "firstNameOff": "Off", "familyNameOff": str(off), "personIdDef": d,
                "firstNameDef": "Def", "familyNameDef": str(d),
                "matchupMinutes": "3:05" if i == 0 else "1:00",
                "partialPossessions": 6.5 if i == 0 else 2.0,
                "percentageDefenderTotalTime": 0.5,
                "percentageOffensiveTotalTime": 0.755 if i == 0 else 0.245,
                "percentageTotalTimeBothOn": 0.6,
            })
            rows.append(row)
    for row in (rows[0], rows[2]):  # the other team gets an offensive player too
        rows.append({**row, "teamTricode": defense, "personIdOff": 1631114,
                     "personIdDef": row["personIdOff"]})
    return pd.DataFrame(rows)


def boxscore(game_id):
    payload = json.loads(FIXTURE.read_text())
    box = payload["boxScoreTraditional"]
    box["gameId"] = game_id
    away, home = teams_for(game_id)
    box["awayTeam"]["teamTricode"], box["homeTeam"]["teamTricode"] = away, home
    return payload


class Calls:
    def __init__(self, fail=()):
        self.n = 0
        self.fail = set(fail)

    def matchups(self, game_id):
        self.n += 1
        if game_id in self.fail:
            raise RuntimeError("timeout")
        return raw_matchups(game_id)

    def box(self, game_id):
        self.n += 1
        return boxscore(game_id)

    def log(self, season):
        self.n += 1
        return game_log()


def test_discovery_builds_series_and_excludes_play_in():
    games = discover_playoff_games(game_log(), "2025-26")
    assert set(games.series_id) == {"2025_26_okc_sas", "2025_26_den_min"}
    assert games.game_id.nunique() == 3 and len(games) == 6
    g1 = games[games.game_id.eq("0042500311")].set_index("team")
    assert g1.loc["SAS", "wl"] == "W" and g1.loc["SAS", "margin"] == 7
    assert bool(g1.loc["OKC", "home"]) and g1.loc["OKC", "opponent"] == "SAS"
    assert games[games.game_id.eq("0042500312")].game_number.iloc[0] == 2
    assert games[games.series_id.eq("2025_26_okc_sas")].playoff_round.iloc[0] == "Conference Finals"


def test_discovery_rejects_a_game_with_one_team_row():
    log = game_log()
    log = log[~((log.GAME_ID == "0042500121") & (log.TEAM_ABBREVIATION == "MIN"))]
    with pytest.raises(ValueError):
        discover_playoff_games(log, "2025-26")


def okc_sas_game():
    games = discover_playoff_games(game_log(), "2025-26")
    return games[games.game_id.eq("0042500311")].iloc[0]


def test_normalized_matchups_use_seconds_and_research_columns():
    game = okc_sas_game()
    out = normalize_matchups(raw_matchups(game.game_id), game)
    assert out.matchup_seconds.tolist()[:2] == [185, 60]
    assert out.off_time_percent.iloc[0] == pytest.approx(75.5)
    assert set(out.def_team) == {"OKC", "SAS"}
    assert out.series_id.eq(game.series_id).all()


def test_matchups_from_another_series_are_rejected():
    game = okc_sas_game()
    with pytest.raises(ValueError):
        normalize_matchups(raw_matchups("0042500121")
                           .assign(gameId=game.game_id), game, ("OKC", "SAS"))


def test_fetch_is_resumable_and_records_failures(tmp_path):
    calls = Calls(fail={"0042500312"})
    first = LeagueFetcher(tmp_path, calls.log, calls.matchups, calls.box,
                          request_interval=0, log=lambda *_: None).run(["2025-26"])
    assert [f["game_id"] for f in first["failed_games"]] == ["0042500312"]
    assert first["seasons"]["2025-26"]["games_acquired"] == 2
    out = tmp_path / "data" / "league"
    assert len(pd.read_csv(out / "matchups.csv.gz")) == 2 * 6
    assert pd.read_csv(out / "boxscores.csv.gz").series_id.nunique() == 2

    before = calls.n
    calls.fail.clear()
    second = LeagueFetcher(tmp_path, calls.log, calls.matchups, calls.box,
                           request_interval=0, log=lambda *_: None).run(["2025-26"])
    assert calls.n - before == 2  # only the failed game: its matchups and box score
    assert not second["failed_games"]
    assert second["rows"]["matchups"] == 3 * 6


def test_offline_mode_never_calls_the_network(tmp_path):
    calls = Calls()
    LeagueFetcher(tmp_path, calls.log, calls.matchups, calls.box,
                  request_interval=0, log=lambda *_: None).run(["2025-26"])
    def forbidden(*_):
        raise AssertionError("network call in offline mode")
    report = LeagueFetcher(tmp_path, forbidden, forbidden, forbidden,
                           offline=True, log=lambda *_: None).run(["2025-26"])
    assert report["rows"]["matchups"] == 3 * 6


def test_max_games_limits_a_trial_run(tmp_path):
    calls = Calls()
    report = LeagueFetcher(tmp_path, calls.log, calls.matchups, calls.box,
                           request_interval=0, log=lambda *_: None).run(["2025-26"], max_games=1)
    assert report["seasons"]["2025-26"]["games_acquired"] == 1


def test_percentage_scale_flags_games_off_100():
    frame = pd.DataFrame({
        "game_id": ["a", "a", "b", "b"], "off_player_id": [1, 1, 1, 1],
        "off_time_percent": [60.0, 40.0, 66.0, 44.0],
    })
    assert percentage_scale(frame) == {"b": 1}


def test_season_range_expands_and_validates():
    assert season_range("2023-24:2025-26") == ["2023-24", "2024-25", "2025-26"]
    assert season_range("2017-18,2019-20") == ["2017-18", "2019-20"]
    with pytest.raises(ValueError):
        season_range("2024-26")
