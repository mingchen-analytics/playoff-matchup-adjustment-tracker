import streamlit as st
from pathlib import Path

from series_catalog import list_series, load_series
from game_context import load_game_context, context_for_team
from player_context import load_player_context, player_context_display
from analytics.metrics import (
    build_adjustment_event_summary,
    calculate_adjustment_scores,
    calculate_matchup_concentration,
    calculate_outcome_context,
    calculate_series_adjustment_leaderboard,
    calculate_transition_share_changes,
)
from visualizations.charts import (
    make_concentration_chart,
    make_matchup_heatmap,
    make_matchup_timeline,
    make_outcome_chart,
    make_series_leaderboard_chart,
    make_transition_change_chart,
)


# -----------------------------
# Page setup
# -----------------------------
st.set_page_config(page_title="Playoff Matchup Adjustment Tracker", layout="wide")

st.title("Playoff Matchup Adjustment Tracker")
st.caption(
    "A game-by-game matchup timeline concept inspired by Databallr’s playoff matchup pages."
)

st.markdown(
    """
    <style>
    .block-container {
        max-width: 1650px;
        padding-top: 2.5rem;
        padding-left: 4rem;
        padding-right: 4rem;
    }

    h1 {
        font-size: 3.2rem !important;
        line-height: 1.15 !important;
        margin-bottom: 0.6rem !important;
    }

    h2 {
        font-size: 2rem !important;
    }

    h3 {
        font-size: 1.65rem !important;
    }

    p, li {
        font-size: 1.12rem !important;
        line-height: 1.65 !important;
    }

    [data-testid="stMarkdownContainer"] {
        font-size: 1.12rem !important;
    }

    [data-testid="stSidebar"] {
        min-width: 310px;
    }

    [data-testid="stSidebar"] * {
        font-size: 1rem !important;
    }

    label {
        font-size: 1rem !important;
    }

    .stSelectbox label {
        font-size: 1rem !important;
        font-weight: 600 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------
# Load data
# -----------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
st.sidebar.header("Series")
catalog, catalog_errors = list_series(PROJECT_ROOT)
for issue in catalog_errors:
    st.sidebar.warning(issue)
if not catalog:
    st.error("No valid series configurations found in the series folder.")
    st.stop()
season = st.sidebar.selectbox(
    "Season", sorted({m.season for _, m in catalog}, reverse=True)
)
season_catalog = [(path, m) for path, m in catalog if m.season == season]
round_name = st.sidebar.selectbox(
    "Round", sorted({m.playoff_round for _, m in season_catalog})
)
round_catalog = [
    (path, m) for path, m in season_catalog if m.playoff_round == round_name
]
by_id = {m.series_id: m for _, m in round_catalog}
selected_series_id = st.sidebar.selectbox(
    "Series",
    list(by_id),
    format_func=lambda key: (
        f"{by_id[key].label} — {len(by_id[key].games)} games"
        + (" · manual reference" if by_id[key].source_csv else " · API snapshot")
        + (f" · {key[-8:]}" if "_api_" in key else "")
        + (" (sample / ongoing)" if not by_id[key].series_complete else "")
    ),
)
manifest = by_id[selected_series_id]
try:
    df, data_quality, provenance = load_series(manifest, PROJECT_ROOT)
except (ValueError, OSError) as exc:
    st.error(f"Cannot load this series: {exc}")
    st.stop()
st.caption(
    f"{manifest.season} · {manifest.playoff_round} · {manifest.label} · {provenance['source']}"
)
if not manifest.series_complete:
    st.info(
        f"This view contains {len(manifest.games)} configured games. It is a sample or ongoing series, not a complete-series claim."
    )
if manifest.notes:
    with st.expander("Series coverage and source"):
        st.write(manifest.notes)
if provenance.get("source_verification") == "offline_unverified":
    st.warning(
        "This cached API snapshot is exploratory. API/manual parity has not been approved."
    )
if provenance.get("source_verification") == "approved_separate_snapshot":
    st.warning(
        "Independent API snapshot: numerical values differ from the manual reference. Do not mix the two sources."
    )
    with st.expander("Snapshot provenance"):
        st.write(
            {
                "snapshot_started_at": provenance.get("started_at"),
                "snapshot_finished_at": provenance.get("finished_at"),
                "dataset_sha256": provenance.get("dataset_sha256"),
                "manual_parity": provenance.get("manual_parity"),
                "games": provenance.get("games"),
            }
        )

if data_quality["errors"]:
    st.error("Data validation failed. Analysis has been stopped.")
    for issue in data_quality["errors"]:
        st.write(f"- {issue}")

    if data_quality["warnings"]:
        st.warning("Additional data-quality warnings:")
        for issue in data_quality["warnings"]:
            st.write(f"- {issue}")

    st.stop()


# -----------------------------
# Sidebar controls
# -----------------------------
st.sidebar.header("Controls")

max_series_games = int(df["game"].nunique())

st.sidebar.subheader("Leaderboard Eligibility")
leaderboard_min_games = (
    st.sidebar.slider(
        "Minimum games",
        min_value=2,
        max_value=max_series_games,
        value=min(5, max_series_games),
        key=f"min_games_{selected_series_id}",
    )
    if max_series_games > 2
    else max_series_games
)
if max_series_games <= 2:
    st.sidebar.caption(
        f"Minimum games: {max_series_games}. Adjustment analysis requires at least two recorded games."
    )
leaderboard_min_minutes = st.sidebar.slider(
    "Minimum series matchup minutes", min_value=0, max_value=60, value=30, step=5
)

team_order = [manifest.team_a, manifest.team_b]

offense_options = []

for team in team_order:
    team_players = sorted(
        df[df["off_team"] == team]["offense_player"].dropna().unique()
    )

    for player in team_players:
        label = f"{team} — {player}"
        value = f"{team}|{player}"
        offense_options.append((label, value))


def parse_player_key(player_key):
    team, player = player_key.split("|", 1)
    return team, player


label_by_value = {value: label for label, value in offense_options}
offense_values = [value for _, value in offense_options]


# -----------------------------
# Main content
# -----------------------------
st.markdown(
    """
This dashboard adds a **game-by-game timeline layer** to matchup data.

Instead of only showing series-level totals, it helps users see **when defensive responsibilities changed**, who became the primary matchup, and how those assignments evolved across a playoff series.

Efficiency numbers are included in the hover details, but matchup time and matchup share are treated as the primary signals because single-game matchup samples are small.
"""
)

with st.expander("Data Quality"):
    quality_col1, quality_col2, quality_col3, quality_col4 = st.columns(4)
    quality_col1.metric("Rows", f"{data_quality['rows']:,}")
    quality_col2.metric("Games", data_quality["games"])
    quality_col3.metric("Offensive Players", data_quality["offensive_players"])
    quality_col4.metric("Validation", data_quality["status"].upper())

    st.caption(
        "Validation runs before any analytics are calculated. "
        "Required columns, identities, game numbers, matchup times, numeric "
        "values, negative values, duplicate rows, and team consistency are checked."
    )

    if data_quality["warnings"]:
        for warning in data_quality["warnings"]:
            st.warning(warning)
    else:
        st.success("No data-quality warnings detected.")

st.subheader("Series Adjustment Leaderboard")
st.caption(
    "Ranks eligible offensive players by their largest game-to-game matchup "
    "redistribution. Eligibility filters are shown in the sidebar because "
    "small matchup samples can produce unstable share changes."
)

leaderboard_df = calculate_series_adjustment_leaderboard(
    data=df,
    min_games=leaderboard_min_games,
    min_matchup_minutes=leaderboard_min_minutes,
)

if leaderboard_df.empty:
    st.info("No players meet the current leaderboard eligibility filters.")
    analysis_values = offense_values
else:
    leaderboard_fig = make_series_leaderboard_chart(leaderboard_df)
    if leaderboard_fig is not None:
        st.plotly_chart(leaderboard_fig, use_container_width=True)

    leaderboard_display = leaderboard_df.copy()
    leaderboard_display["Matchup Min"] = leaderboard_display["Matchup Min"].round(1)
    leaderboard_display["Largest Adjustment"] = leaderboard_display[
        "Largest Adjustment"
    ].round(3)
    leaderboard_display["Average Adjustment"] = leaderboard_display[
        "Average Adjustment"
    ].round(3)
    leaderboard_display["Average HHI"] = leaderboard_display["Average HHI"].round(3)

    st.dataframe(leaderboard_display, use_container_width=True, hide_index=True)

    analysis_values = [
        f"{row['Team']}|{row['Player']}" for _, row in leaderboard_df.iterrows()
    ]

st.subheader("Analyze a Player")
st.caption(
    "Choose an eligible player from the leaderboard to open the full "
    "game-by-game adjustment analysis below."
)

default_analysis_value = next(
    (
        value
        for value in analysis_values
        if value.split("|", 1)[1] == manifest.default_player
    ),
    analysis_values[0],
)

selected_offense_key = st.selectbox(
    "Offensive player",
    key=f"player_{selected_series_id}",
    options=analysis_values,
    index=analysis_values.index(default_analysis_value),
    format_func=lambda value: label_by_value.get(value, value),
)

selected_off_team, selected_player = parse_player_key(selected_offense_key)

game_context_display = None
st.subheader("Game Context")
try:
    game_context = load_game_context(manifest, PROJECT_ROOT)
    if game_context is None:
        st.info("Verified game context is not available for this dataset.")
    else:
        game_context_display = context_for_team(
            game_context, manifest, selected_off_team
        )
        st.caption(
            f"Scores, venue and series records from {selected_off_team}'s perspective. "
            "Series records are shown before and after each game. Opponent points "
            "are derived from team points minus the team point differential in the "
            "cached NBA LeagueGameFinder log. These results provide context, not coaching intent."
        )
        st.dataframe(game_context_display, use_container_width=True, hide_index=True)
except (ValueError, OSError) as exc:
    st.warning(f"Game context is unavailable: {exc}")

player_box_display = None
st.subheader("Player Game Box Score")
try:
    player_box = load_player_context(manifest, PROJECT_ROOT)
    if player_box is None:
        st.info("Verified player game box scores are not available for this dataset.")
    else:
        player_box_display = player_context_display(
            player_box, df, manifest, selected_off_team, selected_player
        )
        st.caption(
            f"Full-game statistics for {selected_player} from cached NBA BoxScoreTraditionalV3. "
            "These differ from the matchup-attributed outcomes below. Non-participants "
            "retain the source status and blank statistics; fouls and +/- do not explain "
            "the timing or intent of a matchup change."
        )
        st.dataframe(player_box_display, use_container_width=True, hide_index=True)
except (ValueError, OSError) as exc:
    st.warning(f"Player game box scores are unavailable: {exc}")

temp = df[
    (df["off_team"] == selected_off_team) & (df["offense_player"] == selected_player)
].copy()

defender_order = (
    temp.groupby("defense_player")["matchup_seconds"]
    .sum()
    .sort_values(ascending=False)
    .index.tolist()
)

defender_options = ["All Defenders"] + defender_order

st.sidebar.subheader("Player Analysis")
highlight_defender = st.sidebar.selectbox(
    "Highlight defender",
    key=f"defender_{selected_series_id}_{selected_offense_key}",
    options=defender_options,
)

st.markdown(f"### {selected_off_team} — {selected_player}")
st.caption(
    "Full player-level view: timeline, matchup-share shifts, concentration, "
    "outcome context, and automated adjustment summary."
)

st.divider()

result = make_matchup_timeline(
    data=df,
    selected_player=selected_player,
    selected_off_team=selected_off_team,
    highlight_defender=highlight_defender,
)

if result is None:
    st.warning("No matchup data available for this selection.")
else:
    fig, player_df = result
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Matchup Share Heatmap")
    st.caption(
        "Each cell shows a defender's share of the selected offensive player's "
        "recorded matchup time in that game. Darker cells indicate a larger share."
    )

    heatmap_fig = make_matchup_heatmap(
        player_df=player_df, selected_player=selected_player
    )

    if heatmap_fig is not None:
        st.plotly_chart(heatmap_fig, use_container_width=True)

    concentration_df = calculate_matchup_concentration(player_df)

    if not concentration_df.empty:
        st.subheader("Matchup Concentration")
        st.caption(
            "Primary and Top-2 shares show how much of the assignment was concentrated "
            "among the leading defenders. HHI summarizes the full distribution; higher HHI "
            "means a more concentrated matchup plan. Effective Defenders = 1 / HHI."
        )

        concentration_fig = make_concentration_chart(concentration_df)
        if concentration_fig is not None:
            st.plotly_chart(concentration_fig, use_container_width=True)

        concentration_display = concentration_df.copy()
        concentration_display["Primary Share %"] = concentration_display[
            "Primary Share %"
        ].round(1)
        concentration_display["Top-2 Share %"] = concentration_display[
            "Top-2 Share %"
        ].round(1)
        concentration_display["HHI"] = concentration_display["HHI"].round(3)
        concentration_display["Effective Defenders"] = concentration_display[
            "Effective Defenders"
        ].round(2)

        st.dataframe(concentration_display, use_container_width=True, hide_index=True)

    adjustment_df = calculate_adjustment_scores(player_df)
    outcome_df = calculate_outcome_context(player_df)

    if not outcome_df.empty:
        st.subheader("Outcome Context")
        st.caption(
            "These are descriptive outcomes from the recorded matchup data. "
            "They show what happened alongside the matchup changes, but they do not "
            "establish that a defender or adjustment caused the result."
        )

        outcome_fig = make_outcome_chart(outcome_df, selected_player)
        if outcome_fig is not None:
            st.plotly_chart(outcome_fig, use_container_width=True)

        if not adjustment_df.empty:
            largest_adjustment_row = adjustment_df.loc[
                adjustment_df["Adjustment Score"].idxmax()
            ]

            previous_game_label = largest_adjustment_row["From"]
            current_game_label = largest_adjustment_row["To"]

            previous_outcome = outcome_df[outcome_df["Game"] == previous_game_label]
            current_outcome = outcome_df[outcome_df["Game"] == current_game_label]

            if not previous_outcome.empty and not current_outcome.empty:
                previous_outcome = previous_outcome.iloc[0]
                current_outcome = current_outcome.iloc[0]

                st.markdown(
                    f"**Largest adjustment transition: {previous_game_label} → "
                    f"{current_game_label}**"
                )

                out_col1, out_col2, out_col3 = st.columns(3)

                out_col1.metric(
                    "PTS/75",
                    f"{current_outcome['PTS/75']:.1f}",
                    f"{current_outcome['PTS/75'] - previous_outcome['PTS/75']:+.1f}",
                    delta_color="off",
                )

                out_col2.metric(
                    "eFG%",
                    f"{current_outcome['eFG%']:.1f}%",
                    f"{current_outcome['eFG%'] - previous_outcome['eFG%']:+.1f} pp",
                    delta_color="off",
                )

                out_col3.metric(
                    "TOV/75",
                    f"{current_outcome['TOV/75']:.1f}",
                    f"{current_outcome['TOV/75'] - previous_outcome['TOV/75']:+.1f}",
                    delta_color="off",
                )

        outcome_display = outcome_df[
            ["Game", "players_pts", "partial_poss", "PTS/75", "eFG%", "TOV/75"]
        ].copy()

        outcome_display = outcome_display.rename(
            columns={"players_pts": "Player PTS", "partial_poss": "Partial Poss"}
        )

        for column in ["Partial Poss", "PTS/75", "eFG%", "TOV/75"]:
            outcome_display[column] = outcome_display[column].round(1)

        st.dataframe(outcome_display, use_container_width=True, hide_index=True)

    if not adjustment_df.empty:
        st.subheader("Game-to-Game Adjustment Score")
        st.caption(
            "Total variation distance between consecutive games' matchup-time distributions. "
            "0 means the defender allocation was unchanged; 1 means it was completely different."
        )

        largest_adjustment = adjustment_df.loc[
            adjustment_df["Adjustment Score"].idxmax()
        ]

        metric_col1, metric_col2 = st.columns(2)
        metric_col1.metric(
            "Largest Adjustment",
            f"{largest_adjustment['Adjustment Score']:.3f}",
            f"{largest_adjustment['From']} → {largest_adjustment['To']}",
        )
        metric_col2.metric(
            "Largest Defender Share Shift",
            f"{largest_adjustment['Share Change (pp)']:+.1f} pp",
            largest_adjustment["Largest Share Change"],
        )

        adjustment_display = adjustment_df.copy()
        adjustment_display["Adjustment Score"] = adjustment_display[
            "Adjustment Score"
        ].round(3)
        adjustment_display["Share Change (pp)"] = adjustment_display[
            "Share Change (pp)"
        ].round(1)

        st.dataframe(adjustment_display, use_container_width=True, hide_index=True)

        st.subheader("Game Transition Comparison")
        st.caption(
            "Select any available game-to-game transition to inspect which defender "
            "shares changed most and how concentration and offensive outcomes moved "
            "over the same interval."
        )

        transition_options = [
            f"{row['From']} → {row['To']}" for _, row in adjustment_df.iterrows()
        ]

        largest_transition_label = (
            f"{largest_adjustment['From']} → {largest_adjustment['To']}"
        )

        selected_transition = st.selectbox(
            "Transition",
            key=f"transition_{selected_series_id}_{selected_offense_key}",
            options=transition_options,
            index=transition_options.index(largest_transition_label),
        )

        transition_row = adjustment_df[
            (adjustment_df["From"] + " → " + adjustment_df["To"]) == selected_transition
        ].iloc[0]

        from_label = transition_row["From"]
        to_label = transition_row["To"]
        from_game = int(from_label.replace("Game ", ""))
        to_game = int(to_label.replace("Game ", ""))

        if game_context_display is not None:
            st.markdown("**Game results around this adjustment**")
            st.dataframe(
                game_context_display[
                    game_context_display["Game"].isin([from_label, to_label])
                ],
                use_container_width=True,
                hide_index=True,
            )

        if player_box_display is not None:
            st.markdown("**Player box scores around this adjustment**")
            st.dataframe(
                player_box_display[
                    player_box_display["Game"].isin([from_label, to_label])
                ],
                use_container_width=True,
                hide_index=True,
            )

        transition_comparison = calculate_transition_share_changes(
            player_df=player_df, from_game=from_game, to_game=to_game
        )

        if not transition_comparison.empty:
            transition_chart = make_transition_change_chart(
                transition_comparison, from_label=from_label, to_label=to_label
            )

            if transition_chart is not None:
                st.plotly_chart(transition_chart, use_container_width=True)

            from_concentration = concentration_df[
                concentration_df["Game"] == from_label
            ]
            to_concentration = concentration_df[concentration_df["Game"] == to_label]
            from_outcome = outcome_df[outcome_df["Game"] == from_label]
            to_outcome = outcome_df[outcome_df["Game"] == to_label]

            if (
                not from_concentration.empty
                and not to_concentration.empty
                and not from_outcome.empty
                and not to_outcome.empty
            ):
                from_concentration = from_concentration.iloc[0]
                to_concentration = to_concentration.iloc[0]
                from_outcome = from_outcome.iloc[0]
                to_outcome = to_outcome.iloc[0]

                st.markdown(f"**{from_label} → {to_label} context**")

                trans_col1, trans_col2, trans_col3, trans_col4, trans_col5 = st.columns(
                    5
                )

                trans_col1.metric(
                    "Adjustment Score", f"{transition_row['Adjustment Score']:.3f}"
                )
                trans_col2.metric(
                    "HHI",
                    f"{to_concentration['HHI']:.3f}",
                    f"{to_concentration['HHI'] - from_concentration['HHI']:+.3f}",
                    delta_color="off",
                )
                trans_col3.metric(
                    "PTS/75",
                    f"{to_outcome['PTS/75']:.1f}",
                    f"{to_outcome['PTS/75'] - from_outcome['PTS/75']:+.1f}",
                    delta_color="off",
                )
                trans_col4.metric(
                    "eFG%",
                    f"{to_outcome['eFG%']:.1f}%",
                    f"{to_outcome['eFG%'] - from_outcome['eFG%']:+.1f} pp",
                    delta_color="off",
                )
                trans_col5.metric(
                    "TOV/75",
                    f"{to_outcome['TOV/75']:.1f}",
                    f"{to_outcome['TOV/75'] - from_outcome['TOV/75']:+.1f}",
                    delta_color="off",
                )

                primary_from = from_concentration["Primary Defender"]
                primary_to = to_concentration["Primary Defender"]

                if primary_from != primary_to:
                    st.markdown(f"Primary matchup: **{primary_from} → {primary_to}**")
                else:
                    st.markdown(f"Primary matchup remained **{primary_to}**.")

            transition_display = transition_comparison[
                [
                    "Defender",
                    "From Share %",
                    "To Share %",
                    "Share Change (pp)",
                    "From Time",
                    "To Time",
                ]
            ].copy()

            for column in ["From Share %", "To Share %", "Share Change (pp)"]:
                transition_display[column] = transition_display[column].round(1)

            st.dataframe(transition_display, use_container_width=True, hide_index=True)

    event_summary = build_adjustment_event_summary(
        selected_player=selected_player,
        adjustment_df=adjustment_df,
        concentration_df=concentration_df,
        outcome_df=outcome_df,
    )

    if event_summary:
        st.subheader("Adjustment Event Summary")
        st.markdown(event_summary)

    st.subheader("Primary Defender Summary")

    st.caption(
        "Primary and secondary defenders are ranked by matchup time within each game."
    )

    summary = (
        player_df.sort_values(["game", "rank_in_game"]).groupby("game").head(2).copy()
    )

    summary["role"] = summary["rank_in_game"].map({1.0: "Primary", 2.0: "Secondary"})

    summary_table = summary[
        [
            "game_label",
            "role",
            "defense_player",
            "matchup_time_label",
            "matchup_share_time",
            "partial_poss",
            "players_pts",
            "pts_per_75",
        ]
    ].copy()

    summary_table = summary_table.rename(
        columns={
            "game_label": "Game",
            "role": "Role",
            "defense_player": "Defender",
            "matchup_time_label": "Time",
            "matchup_share_time": "Time Share %",
            "partial_poss": "Partial Poss",
            "players_pts": "Player PTS",
            "pts_per_75": "PTS/75",
        }
    )

    summary_table["Time Share %"] = summary_table["Time Share %"].round(1)
    summary_table["Partial Poss"] = summary_table["Partial Poss"].round(1)
    summary_table["PTS/75"] = summary_table["PTS/75"].round(1)

    st.dataframe(
        summary_table.reset_index(drop=True), use_container_width=True, hide_index=True
    )
    with st.expander("Project idea"):
        st.markdown(
            """
**Product concept:** Databallr's current matchup pages are useful for series-level totals.  
This prototype adds a **game-by-game timeline layer** so users can see when matchup responsibilities changed during a playoff series.

**Series selection:** Choose any configured series in the sidebar; the same analysis methods apply.

**Interpretation note:** Matchup time and matchup share are the primary signals. Efficiency stats are shown as supporting context, not definitive proof of individual defensive success.
"""
        )
