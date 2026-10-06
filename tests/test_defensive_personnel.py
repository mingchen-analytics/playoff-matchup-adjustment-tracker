"""Personnel context must reconcile to the verified NBA roster and allocation."""

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from analytics.metrics import calculate_transition_share_changes
from defensive_personnel import compare_defensive_personnel, personnel_display
from player_context import load_player_context
from series_catalog import list_series, load_series
from series_manifest import load_manifest
from visualizations.personnel import make_personnel_change_chart

ROOT = Path(__file__).resolve().parents[1]
SERIES = [m.series_id for _, m in list_series(ROOT)[0] if not m.source_csv]


@pytest.fixture(scope="module")
def cases():
    result = {}
    for series_id in SERIES:
        manifest = load_manifest(ROOT / "series" / f"{series_id}.yml")
        matchups, _, _ = load_series(manifest, ROOT)
        result[series_id] = (manifest, matchups, load_player_context(manifest, ROOT))
    return result


def wembanyama(cases):
    return cases["2026_okc_sas_api_20261005"]


def comparison(cases, *, offense_team="SAS", offense_player="Victor Wembanyama"):
    m, matchups, players = wembanyama(cases)
    return compare_defensive_personnel(
        matchups, players, m, offense_team, offense_player, 1, 2
    )


@pytest.mark.parametrize("series_id", SERIES)
@pytest.mark.parametrize("side", ["team_a", "team_b"])
def test_all_series_personnel_reconciles_every_star_transition(cases, series_id, side):
    m, matchups, players = cases[series_id]
    team = getattr(m, side)
    star = (
        matchups[matchups.off_team.eq(team)]
        .groupby("offense_player")
        .matchup_seconds.sum()
        .idxmax()
    )
    offense = matchups[matchups.off_team.eq(team) & matchups.offense_player.eq(star)]
    for previous, current in zip(m.games, m.games[1:]):
        result = compare_defensive_personnel(
            matchups, players, m, team, star, previous.game_number, current.game_number
        )
        defending_team = m.team_b if team == m.team_a else m.team_a
        roster = players[
            players.team.eq(defending_team)
            & players.game_id.isin([previous.game_id, current.game_id])
        ]
        assert set(result.player_id) == set(roster.player_id)
        assert result.player_id.is_unique and result.team.eq(defending_team).all()
        for prefix, game in (("from", previous), ("to", current)):
            actual = offense[offense.game == game.game_number].matchup_seconds.sum()
            assert result[f"{prefix}_matchup_minutes"].sum() * 60 == pytest.approx(
                actual
            )
            if actual > 0:
                assert result[f"{prefix}_share"].sum() == pytest.approx(100)
            else:
                assert result[f"{prefix}_share"].isna().all()
            assert result[f"{prefix}_starter"].eq(True).sum() == 5
            unknown = result[f"{prefix}_status"].ne("Played")
            assert (
                result.loc[unknown, [f"{prefix}_minutes", f"{prefix}_fouls"]]
                .isna()
                .all()
                .all()
            )
        if not result.share_change.isna().any():
            assert result.share_change.sum() == pytest.approx(0, abs=1e-10)
            assert (0.5 * result.share_change.abs().sum() / 100) <= 1 + 1e-10


def test_wembanyama_api_changes_agree_with_existing_allocation_engine(cases):
    m, matchups, players = wembanyama(cases)
    output = comparison(cases).set_index("player")
    offense = matchups[
        matchups.off_team.eq("SAS") & matchups.offense_player.eq("Victor Wembanyama")
    ]
    expected = calculate_transition_share_changes(offense, 1, 2).set_index("Defender")
    for name, row in expected.iterrows():
        assert output.loc[name, "share_change"] == pytest.approx(
            row["Share Change (pp)"]
        )
    hartenstein = output.loc["Isaiah Hartenstein"]
    assert hartenstein.from_minutes == pytest.approx(730 / 60)
    assert hartenstein.to_minutes == pytest.approx(1640 / 60)
    assert hartenstein.minutes_change == pytest.approx(910 / 60)
    assert hartenstein.from_starter and hartenstein.to_starter
    assert hartenstein.from_fouls == 2 and hartenstein.to_fouls == 4
    assert output.loc["Alex Caruso", "share_change"] < 0
    assert output.loc["Jalen Williams", "minutes_change"] < 0
    # These are separate API observations; the original manual 0.620 is untouched.
    pd.testing.assert_frame_equal(matchups, load_series(m, ROOT)[0])
    pd.testing.assert_frame_equal(players, load_player_context(m, ROOT))


def test_dnp_and_absent_roster_entries_do_not_become_zero_box_performances(cases):
    m, matchups, original = wembanyama(cases)
    players = original.copy()
    joe = 1630198  # Remove one zero-matchup roster entry from the first game.
    players = players[~(players.game_number.eq(1) & players.player_id.eq(joe))]
    result = compare_defensive_personnel(
        matchups, players, m, "SAS", "Victor Wembanyama", 1, 2
    )
    row = result[result.player_id.eq(joe)].iloc[0]
    assert row.from_status == "Not listed in box score"
    assert pd.isna(row.from_minutes) and pd.isna(row.minutes_change)
    assert row.to_status == "Played" and row.from_matchup_minutes == 0
    dnp = result[result.player.eq("Nikola Topić")].iloc[0]
    assert dnp.from_status == "DNP - Coach's Decision"
    assert pd.isna(dnp.from_minutes) and pd.isna(dnp.from_fouls)
    table = personnel_display(result, 1, 2)
    assert pd.isna(
        table[table.Defender.eq("Nikola Topić")].iloc[0]["Game 1 personal fouls"]
    )


def test_missing_recorded_exposure_keeps_share_unavailable(cases):
    m, matchups, players = wembanyama(cases)
    selected = matchups.copy()
    selected = selected[
        ~(
            selected.game.eq(1)
            & selected.off_team.eq("SAS")
            & selected.offense_player.eq("Victor Wembanyama")
        )
    ]
    output = compare_defensive_personnel(
        selected, players, m, "SAS", "Victor Wembanyama", 1, 2
    )
    assert output.from_matchup_minutes.eq(0).all()
    assert output.from_share.isna().all() and output.share_change.isna().all()
    assert make_personnel_change_chart(output, 1, 2) is None


@pytest.mark.parametrize(
    "mutation", ["id", "team", "seconds", "game", "dnp", "duplicate"]
)
def test_conflicting_personnel_evidence_is_rejected(cases, mutation):
    m, original, source_players = wembanyama(cases)
    matchups, players = original.copy(), source_players.copy()
    chosen = matchups.index[
        matchups.game.eq(1)
        & matchups.off_team.eq("SAS")
        & matchups.offense_player.eq("Victor Wembanyama")
        & matchups.defense_player.eq("Isaiah Hartenstein")
    ][0]
    if mutation == "id":
        matchups.loc[chosen, "def_player_id"] = 99999999
    elif mutation == "team":
        matchups.loc[chosen, "def_team"] = "SAS"
    elif mutation == "seconds":
        matchups.loc[chosen, "matchup_seconds"] = float("nan")
    elif mutation == "game":
        matchups.loc[chosen, "game_id"] = "0042500312"
    elif mutation == "dnp":
        players.loc[
            players.game_number.eq(1) & players.player_id.eq(1628392), "played"
        ] = False
    else:
        players = pd.concat([players, players.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError):
        compare_defensive_personnel(
            matchups, players, m, "SAS", "Victor Wembanyama", 1, 2
        )


@pytest.mark.parametrize(
    "team,name,from_game,to_game",
    [
        ("IND", "Victor Wembanyama", 1, 2),
        ("SAS", "Unknown player", 1, 2),
        ("SAS", "Victor Wembanyama", 2, 1),
        ("SAS", "Victor Wembanyama", 1, 1),
        ("SAS", "Victor Wembanyama", 1, 8),
    ],
)
def test_invalid_personnel_selection_is_rejected(cases, team, name, from_game, to_game):
    m, matchups, players = wembanyama(cases)
    with pytest.raises(ValueError):
        compare_defensive_personnel(
            matchups, players, m, team, name, from_game, to_game
        )


def test_comparison_plot_keeps_different_units_and_missing_minutes(cases):
    result = comparison(cases)
    chart = make_personnel_change_chart(result, 1, 2)
    assert chart.layout.xaxis.title.text == "pp"
    assert chart.layout.xaxis2.title.text == "min"
    assert len(chart.data[0].y) == 10
    hartenstein = result[result.player.eq("Isaiah Hartenstein")].iloc[0]
    i = list(chart.data[0].y).index("Isaiah Hartenstein")
    assert chart.data[0].x[i] == hartenstein.share_change
    assert chart.data[1].x[i] == hartenstein.minutes_change
    result.loc[result.player.eq("Isaiah Hartenstein"), "minutes_change"] = float("nan")
    chart = make_personnel_change_chart(result, 1, 2)
    assert pd.isna(chart.data[1].x[i])


def test_manual_sample_is_not_joined_to_api_personnel(cases):
    m = load_manifest(ROOT / "series/2026_okc_sas_sample.yml")
    _, matchups, players = wembanyama(cases)
    with pytest.raises(ValueError, match="API"):
        compare_defensive_personnel(
            matchups, players, m, "SAS", "Victor Wembanyama", 1, 2
        )


def test_dashboard_personnel_follows_team_and_transition():
    sid = "2026_okc_sas_api_20261005"
    app = AppTest.from_file(str(ROOT / "app_v1.py")).run(timeout=30)
    assert not app.exception and not app.error
    assert any(
        "defensive personnel context is not available" in entry.value
        for entry in app.info
    )
    app.sidebar.selectbox[2].set_value(sid).run(timeout=30)
    app.selectbox(key=f"transition_{sid}_SAS|Victor Wembanyama").set_value(
        "Game 1 → Game 2"
    ).run(timeout=30)
    table = next(
        frame.value
        for frame in app.dataframe
        if "Full-game min change" in frame.value.columns
    )
    row = table[table.Defender.eq("Isaiah Hartenstein")].iloc[0]
    assert row["Game 1 full-game min"] == 12.17 and row["Game 2 full-game min"] == 27.33
    assert any("Game 1 58 min → Game 2 48 min" in entry.value for entry in app.caption)
    app.selectbox(key=f"player_{sid}").set_value("OKC|Shai Gilgeous-Alexander").run(
        timeout=30
    )
    table = next(
        frame.value
        for frame in app.dataframe
        if "Full-game min change" in frame.value.columns
    )
    assert "Victor Wembanyama" in table.Defender.values
    assert "Isaiah Hartenstein" not in table.Defender.values
    app.selectbox(key=f"transition_{sid}_OKC|Shai Gilgeous-Alexander").set_value(
        "Game 2 → Game 3"
    ).run(timeout=30)
    table = next(
        frame.value
        for frame in app.dataframe
        if "Full-game min change" in frame.value.columns
    )
    assert "Game 3 full-game min" in table and "Game 1 full-game min" not in table
    assert not app.exception and not app.error


def test_real_diacritics_and_suffixes_join_by_nba_id(cases):
    m, matchups, players = cases["2026_den_min_api_20261005"]
    for team, player_id, canonical_name in [
        ("MIN", 202685, "Jonas Valančiūnas"),
        ("DEN", 1630545, "Terrence Shannon Jr."),
    ]:
        star = (
            matchups[matchups.off_team.eq(team)]
            .groupby("offense_player")
            .matchup_seconds.sum()
            .idxmax()
        )
        output = compare_defensive_personnel(matchups, players, m, team, star, 3, 4)
        row = output[output.player_id.eq(player_id)].iloc[0]
        assert row.player == canonical_name
