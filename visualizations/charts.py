"""Plotly visualizations for the matchup adjustment dashboard."""

import plotly.graph_objects as go

from analytics.metrics import seconds_to_label


def make_segment_label(row):
    last_name = row["defense_player"].split()[-1]

    # Only show label for meaningful segments
    if row["matchup_seconds"] >= 90 or row["is_primary_defender"]:
        return last_name
    return ""


def make_matchup_timeline(
    data,
    selected_player,
    selected_off_team=None,
    highlight_defender="All Defenders"
):
    if selected_off_team is None:
        player_df = data[data["offense_player"] == selected_player].copy()
    else:
        player_df = data[
            (data["offense_player"] == selected_player) &
            (data["off_team"] == selected_off_team)
        ].copy()

    if player_df.empty:
        return None

    player_df["game_label"] = "Game " + player_df["game"].astype(str)

    player_df["total_time_by_game"] = (
        player_df.groupby("game")["matchup_seconds"].transform("sum")
    )

    player_df["matchup_share_time"] = (
        player_df["matchup_seconds"] / player_df["total_time_by_game"] * 100
    )

    player_df["rank_in_game"] = (
        player_df.groupby("game")["matchup_seconds"]
        .rank(method="first", ascending=False)
    )

    player_df["is_primary_defender"] = player_df["rank_in_game"] == 1

    player_df = player_df.sort_values(
        ["game", "matchup_seconds"],
        ascending=[True, False]
    ).copy()

    player_df["bar_start"] = (
        player_df.groupby("game")["matchup_seconds"].cumsum()
        - player_df["matchup_seconds"]
    )

    player_df["matchup_time_label"] = (
        player_df["matchup_seconds"].apply(seconds_to_label)
    )

    player_df["segment_label"] = player_df.apply(make_segment_label, axis=1)

    # Optional efficiency metrics
    player_df["pts_per_75"] = 0.0

    poss_mask = player_df["partial_poss"] > 0
    player_df.loc[poss_mask, "pts_per_75"] = (
    player_df.loc[poss_mask, "players_pts"] /
    player_df.loc[poss_mask, "partial_poss"] * 75
    )

    player_df["efg_pct_calc"] = 0.0

    fga_mask = player_df["fga"] > 0
    player_df.loc[fga_mask, "efg_pct_calc"] = (
        (player_df.loc[fga_mask, "fgm"] + 0.5 * player_df.loc[fga_mask, "3pm"]) /
        player_df.loc[fga_mask, "fga"] * 100
    )

    player_df["hover_text"] = (
        "<b>" + player_df["defense_player"] + "</b><br>" +
        player_df["game_label"] + "<br>" +
        "Matchup time: " + player_df["matchup_time_label"] + "<br>" +
        "Time share: " + player_df["matchup_share_time"].round(1).astype(str) + "%<br>" +
        "Partial possessions: " + player_df["partial_poss"].round(1).astype(str) + "<br>" +
        selected_player + " points: " + player_df["players_pts"].astype(str) + "<br>" +
        "FG: " + player_df["fgm"].astype(int).astype(str) + "/" + player_df["fga"].astype(int).astype(str) + "<br>" +
        "3P: " + player_df["3pm"].astype(int).astype(str) + "/" + player_df["3pa"].astype(int).astype(str) + "<br>" +
        "FTA: " + player_df["fta"].astype(int).astype(str) + "<br>" +
        "AST: " + player_df["ast"].astype(int).astype(str) + "<br>" +
        "TOV: " + player_df["tov"].astype(int).astype(str) + "<br>" +
        "eFG%: " + player_df["efg_pct_calc"].round(1).astype(str) + "%<br>" +
        "PTS/75: " + player_df["pts_per_75"].round(1).astype(str)
    )

    fig = go.Figure()

    defenders = list(player_df["defense_player"].unique())

    for defender in defenders:
        d = player_df[player_df["defense_player"] == defender]

        if highlight_defender == "All Defenders":
            trace_opacity = 1
        elif defender == highlight_defender:
            trace_opacity = 1
        else:
            trace_opacity = 0.2

        fig.add_trace(
            go.Bar(
                name=defender,
                y=d["game_label"],
                x=d["matchup_seconds"],
                base=d["bar_start"],
                orientation="h",
                text=d["segment_label"],
                textfont=dict(size=16),
                textposition="inside",
                customdata=d["hover_text"],
                hovertemplate="%{customdata}<extra></extra>",
                opacity=trace_opacity
            )
        )

    max_total_seconds = player_df.groupby("game_label")["matchup_seconds"].sum().max()
    tick_seconds = list(range(0, int(max_total_seconds) + 301, 300))
    tick_labels = [f"{s // 60}:00" for s in tick_seconds]

    game_order = [
        f"Game {g}"
        for g in sorted(player_df["game"].dropna().unique(), reverse=True)
    ]

    title_team = f" ({selected_off_team})" if selected_off_team else ""

    fig.update_layout(
        title=(
            "Game-by-Game Defensive Matchup Timeline"
            f"<br><sup>{selected_player}{title_team} on offense</sup>"
        ),
        font=dict(size=17),
        title_font=dict(size=24),
        xaxis=dict(
            title="Matchup Time",
            tickmode="array",
            tickvals=tick_seconds,
            ticktext=tick_labels,
            title_font=dict(size=18),
            tickfont=dict(size=16)
        ),
        yaxis=dict(
            title="",
            categoryorder="array",
            categoryarray=game_order,
            tickfont=dict(size=17)
        ),
        barmode="overlay",
        height=760,
        legend=dict(
            title="Defender",
            font=dict(size=14),
            title_font=dict(size=15)
        ),
        hoverlabel=dict(
            font_size=14
        ),
        margin=dict(l=100, r=300, t=110, b=90)
    )

    return fig, player_df


def make_matchup_heatmap(player_df, selected_player, top_n=8):
    """
    Shows how matchup share shifts across games.

    Rows are defenders, columns are games, and cell values are each defender's
    share of the offensive player's recorded matchup time in that game.
    """
    if player_df.empty:
        return None

    heatmap_df = (
        player_df.groupby(["game", "defense_player"], as_index=False)["matchup_seconds"]
        .sum()
    )

    heatmap_df["game_total_seconds"] = (
        heatmap_df.groupby("game")["matchup_seconds"].transform("sum")
    )

    heatmap_df["matchup_share_pct"] = (
        heatmap_df["matchup_seconds"]
        / heatmap_df["game_total_seconds"]
        * 100
    )

    defender_order = (
        heatmap_df.groupby("defense_player")["matchup_seconds"]
        .sum()
        .sort_values(ascending=False)
        .head(top_n)
        .index
        .tolist()
    )

    heatmap_df = heatmap_df[
        heatmap_df["defense_player"].isin(defender_order)
    ].copy()

    share_matrix = (
        heatmap_df
        .pivot(index="defense_player", columns="game", values="matchup_share_pct")
        .reindex(defender_order)
        .fillna(0)
    )

    time_matrix = (
        heatmap_df
        .pivot(index="defense_player", columns="game", values="matchup_seconds")
        .reindex(index=defender_order, columns=share_matrix.columns)
        .fillna(0)
    )

    game_labels = [f"Game {int(game)}" for game in share_matrix.columns]
    text_labels = share_matrix.map(
        lambda value: f"{value:.0f}%" if value >= 5 else ""
    )

    hover_labels = time_matrix.map(seconds_to_label)

    fig = go.Figure(
        data=go.Heatmap(
            z=share_matrix.values,
            x=game_labels,
            y=share_matrix.index.tolist(),
            text=text_labels.values,
            texttemplate="%{text}",
            customdata=hover_labels.values,
            colorscale="Blues",
            zmin=0,
            zmax=max(50, float(share_matrix.to_numpy().max())),
            colorbar=dict(title="Matchup<br>Share %"),
            hovertemplate=(
                "<b>%{y}</b><br>"
                "%{x}<br>"
                "Matchup share: %{z:.1f}%<br>"
                "Matchup time: %{customdata}"
                "<extra></extra>"
            )
        )
    )

    fig.update_layout(
        title=(
            "Matchup Share Heatmap"
            f"<br><sup>{selected_player} on offense · top {len(defender_order)} defenders by series matchup time</sup>"
        ),
        title_font=dict(size=22),
        xaxis=dict(title="", side="top"),
        yaxis=dict(
            title="",
            autorange="reversed"
        ),
        height=max(430, 52 * len(defender_order) + 160),
        margin=dict(l=170, r=80, t=120, b=60)
    )

    return fig


def make_concentration_chart(concentration_df):
    if concentration_df.empty:
        return None

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=concentration_df["Game"],
            y=concentration_df["Primary Share %"],
            mode="lines+markers",
            name="Primary Defender Share",
            hovertemplate="%{x}<br>Primary share: %{y:.1f}%<extra></extra>"
        )
    )

    fig.add_trace(
        go.Scatter(
            x=concentration_df["Game"],
            y=concentration_df["Top-2 Share %"],
            mode="lines+markers",
            name="Top-2 Defender Share",
            hovertemplate="%{x}<br>Top-2 share: %{y:.1f}%<extra></extra>"
        )
    )

    fig.update_layout(
        title="Matchup Concentration by Game",
        yaxis=dict(
            title="Share of Recorded Matchup Time (%)",
            range=[0, 100]
        ),
        xaxis=dict(title=""),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0
        ),
        height=430,
        margin=dict(l=70, r=40, t=90, b=60)
    )

    return fig


def make_outcome_chart(outcome_df, selected_player):
    if outcome_df.empty:
        return None

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=outcome_df["Game"],
            y=outcome_df["PTS/75"],
            mode="lines+markers",
            name="PTS/75",
            hovertemplate="%{x}<br>PTS/75: %{y:.1f}<extra></extra>"
        )
    )

    fig.add_trace(
        go.Scatter(
            x=outcome_df["Game"],
            y=outcome_df["eFG%"],
            mode="lines+markers",
            name="eFG%",
            yaxis="y2",
            hovertemplate="%{x}<br>eFG%: %{y:.1f}%<extra></extra>"
        )
    )

    fig.update_layout(
        title=(
            "Outcome Context by Game"
            f"<br><sup>{selected_player} · descriptive context, not causal attribution</sup>"
        ),
        yaxis=dict(
            title="PTS/75"
        ),
        yaxis2=dict(
            title="eFG%",
            overlaying="y",
            side="right",
            rangemode="tozero"
        ),
        xaxis=dict(title=""),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0
        ),
        height=430,
        margin=dict(l=70, r=70, t=100, b=60)
    )

    return fig


def make_transition_change_chart(comparison_df, from_label, to_label, top_n=8):
    if comparison_df.empty:
        return None

    chart_df = comparison_df.head(top_n).sort_values(
        "Share Change (pp)",
        ascending=True
    )

    fig = go.Figure(
        go.Bar(
            x=chart_df["Share Change (pp)"],
            y=chart_df["Defender"],
            orientation="h",
            text=chart_df["Share Change (pp)"].map(
                lambda value: f"{value:+.1f}"
            ),
            textposition="outside",
            customdata=chart_df[[
                "From Share %",
                "To Share %",
                "From Time",
                "To Time"
            ]].values,
            hovertemplate=(
                "<b>%{y}</b><br>"
                f"{from_label}: " + "%{customdata[0]:.1f}% (%{customdata[2]})<br>"
                f"{to_label}: " + "%{customdata[1]:.1f}% (%{customdata[3]})<br>"
                "Change: %{x:+.1f} pp"
                "<extra></extra>"
            )
        )
    )

    max_abs = max(
        10,
        float(chart_df["Share Change (pp)"].abs().max()) * 1.25
    )

    fig.update_layout(
        title=(
            "Defender Matchup Share Changes"
            f"<br><sup>{from_label} → {to_label}</sup>"
        ),
        xaxis=dict(
            title="Change in Matchup Share (percentage points)",
            range=[-max_abs, max_abs],
            zeroline=True
        ),
        yaxis=dict(title=""),
        height=max(430, 45 * len(chart_df) + 170),
        margin=dict(l=180, r=80, t=100, b=70)
    )

    return fig


def make_series_leaderboard_chart(leaderboard_df, top_n=10):
    if leaderboard_df.empty:
        return None

    chart_df = leaderboard_df.head(top_n).sort_values(
        "Largest Adjustment",
        ascending=True
    ).copy()

    chart_df["Label"] = (
        chart_df["Team"] + " — " + chart_df["Player"]
    )

    fig = go.Figure(
        go.Bar(
            x=chart_df["Largest Adjustment"],
            y=chart_df["Label"],
            orientation="h",
            text=chart_df["Largest Adjustment"].round(3),
            textposition="outside",
            customdata=chart_df[[
                "Largest Transition",
                "Average Adjustment",
                "Matchup Min"
            ]].values,
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Largest adjustment: %{x:.3f}<br>"
                "Transition: %{customdata[0]}<br>"
                "Average adjustment: %{customdata[1]:.3f}<br>"
                "Series matchup time: %{customdata[2]:.1f} min"
                "<extra></extra>"
            )
        )
    )

    fig.update_layout(
        title="Largest Game-to-Game Matchup Adjustment",
        xaxis=dict(
            title="Adjustment Score",
            range=[0, 1]
        ),
        yaxis=dict(title=""),
        height=max(430, 42 * len(chart_df) + 170),
        margin=dict(l=180, r=70, t=90, b=60)
    )

    return fig
