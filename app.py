import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pathlib import Path


# -----------------------------
# Page setup
# -----------------------------
st.set_page_config(
    page_title="Playoff Matchup Adjustment Tracker",
    layout="wide"
)

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
    unsafe_allow_html=True
)



# -----------------------------
# Load data
# -----------------------------
DATA_PATH = Path("data/OKC Spurs Matchup Data.csv")


@st.cache_data
def load_matchup_data(path):
    return pd.read_csv(path)


if not DATA_PATH.exists():
    st.error("CSV file not found. Please make sure the CSV is inside the data folder.")
    st.stop()

df = load_matchup_data(DATA_PATH)


# -----------------------------
# Clean data
# -----------------------------
df.columns = (
    df.columns
    .str.strip()
    .str.lower()
    .str.replace(" ", "_")
    .str.replace("%", "percent")
)

for col in ["offense_player", "defense_player", "off_team", "def_team"]:
    if col in df.columns:
        df[col] = (
            df[col]
            .astype(str)
            .str.replace("\xa0", " ", regex=False)
            .str.strip()
        )


def time_to_seconds(time_value):
    """
    Converts matchup time to seconds.
    Handles common formats:
    - '8:18'
    - Excel time fraction, if accidentally exported that way
    - numeric seconds fallback
    """
    if pd.isna(time_value):
        return 0

    text = str(time_value).strip()

    if ":" in text:
        parts = text.split(":")
        if len(parts) == 2:
            minutes, seconds = parts
            return int(minutes) * 60 + int(seconds)
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return int(hours) * 3600 + int(minutes) * 60 + int(seconds)

    try:
        value = float(text)

        # If Excel exported time as a fraction of a day
        if 0 < value < 1:
            return value * 24 * 60 * 60

        # Otherwise treat as seconds
        return value

    except ValueError:
        return 0


df["matchup_seconds"] = df["min"].apply(time_to_seconds)

numeric_cols = [
    "partial_poss",
    "players_pts",
    "team_pts",
    "ast",
    "tov",
    "blk",
    "fgm",
    "fga",
    "3pm",
    "3pa",
    "ftm",
    "fta",
    "sfl"
]

for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)


# -----------------------------
# Helper functions
# -----------------------------
def seconds_to_label(seconds):
    minutes = int(seconds) // 60
    sec = int(seconds) % 60
    return f"{minutes}:{sec:02d}"


def calculate_outcome_context(player_df):
    """
    Aggregates the selected offensive player's recorded matchup outcomes by game.

    These metrics are descriptive context only. They do not isolate the causal
    effect of a defender or a matchup adjustment.
    """
    if player_df.empty:
        return pd.DataFrame()

    outcome_df = (
        player_df.groupby("game", as_index=False)
        .agg({
            "partial_poss": "sum",
            "players_pts": "sum",
            "fgm": "sum",
            "fga": "sum",
            "3pm": "sum",
            "fta": "sum",
            "ast": "sum",
            "tov": "sum"
        })
        .sort_values("game")
        .copy()
    )

    outcome_df["PTS/75"] = 0.0
    poss_mask = outcome_df["partial_poss"] > 0
    outcome_df.loc[poss_mask, "PTS/75"] = (
        outcome_df.loc[poss_mask, "players_pts"]
        / outcome_df.loc[poss_mask, "partial_poss"]
        * 75
    )

    outcome_df["eFG%"] = 0.0
    fga_mask = outcome_df["fga"] > 0
    outcome_df.loc[fga_mask, "eFG%"] = (
        (
            outcome_df.loc[fga_mask, "fgm"]
            + 0.5 * outcome_df.loc[fga_mask, "3pm"]
        )
        / outcome_df.loc[fga_mask, "fga"]
        * 100
    )

    outcome_df["TOV/75"] = 0.0
    outcome_df.loc[poss_mask, "TOV/75"] = (
        outcome_df.loc[poss_mask, "tov"]
        / outcome_df.loc[poss_mask, "partial_poss"]
        * 75
    )

    outcome_df["Game"] = "Game " + outcome_df["game"].astype(int).astype(str)

    return outcome_df[[
        "game",
        "Game",
        "players_pts",
        "partial_poss",
        "PTS/75",
        "eFG%",
        "TOV/75",
        "ast",
        "tov",
        "fgm",
        "fga",
        "fta"
    ]]


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


def calculate_matchup_concentration(player_df):
    """
    Summarizes how concentrated the matchup allocation is within each game.

    HHI is the sum of squared defender matchup shares.
    Higher HHI means the assignment is more concentrated.

    Effective defenders = 1 / HHI.
    This is a concentration-equivalent count, not a literal defender count.
    """
    if player_df.empty:
        return pd.DataFrame()

    game_defender_time = (
        player_df.groupby(["game", "defense_player"], as_index=False)["matchup_seconds"]
        .sum()
    )

    game_defender_time["game_total_seconds"] = (
        game_defender_time.groupby("game")["matchup_seconds"].transform("sum")
    )

    game_defender_time["matchup_share"] = (
        game_defender_time["matchup_seconds"]
        / game_defender_time["game_total_seconds"]
    )

    records = []

    for game, game_df in game_defender_time.groupby("game"):
        game_df = game_df.sort_values("matchup_share", ascending=False).copy()
        shares = game_df["matchup_share"].tolist()

        primary_share = shares[0] if shares else 0
        top_two_share = sum(shares[:2])
        hhi = sum(share ** 2 for share in shares)
        effective_defenders = (1 / hhi) if hhi > 0 else 0

        records.append({
            "Game": f"Game {int(game)}",
            "Primary Defender": game_df.iloc[0]["defense_player"] if len(game_df) else "",
            "Primary Share %": primary_share * 100,
            "Top-2 Share %": top_two_share * 100,
            "HHI": hhi,
            "Effective Defenders": effective_defenders
        })

    return pd.DataFrame(records)


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


def calculate_adjustment_scores(player_df):
    """
    Quantifies how much the defensive matchup-time distribution changes
    from one game to the next using total variation distance.

    Score range:
    - 0.0 = identical matchup allocation
    - 1.0 = completely different matchup allocation
    """
    if player_df.empty:
        return pd.DataFrame()

    game_defender_time = (
        player_df.groupby(["game", "defense_player"], as_index=False)["matchup_seconds"]
        .sum()
    )

    game_defender_time["game_total_seconds"] = (
        game_defender_time.groupby("game")["matchup_seconds"].transform("sum")
    )

    game_defender_time["matchup_share"] = (
        game_defender_time["matchup_seconds"]
        / game_defender_time["game_total_seconds"]
    )

    share_matrix = (
        game_defender_time
        .pivot(index="game", columns="defense_player", values="matchup_share")
        .fillna(0)
        .sort_index()
    )

    games = share_matrix.index.tolist()
    records = []

    for previous_game, current_game in zip(games[:-1], games[1:]):
        previous = share_matrix.loc[previous_game]
        current = share_matrix.loc[current_game]

        score = 0.5 * (current - previous).abs().sum()
        deltas = ((current - previous) * 100).sort_values(
            key=lambda values: values.abs(),
            ascending=False
        )

        biggest_defender = deltas.index[0]
        biggest_delta = deltas.iloc[0]

        records.append({
            "From": f"Game {int(previous_game)}",
            "To": f"Game {int(current_game)}",
            "Adjustment Score": score,
            "Largest Share Change": biggest_defender,
            "Share Change (pp)": biggest_delta
        })

    return pd.DataFrame(records)


def make_segment_label(row):
    last_name = row["defense_player"].split()[-1]

    # Only show label for meaningful segments
    if row["matchup_seconds"] >= 90 or row["is_primary_defender"]:
        return last_name
    return ""


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


def make_matchup_timeline(
    selected_player,
    selected_off_team=None,
    highlight_defender="All Defenders"
):
    if selected_off_team is None:
        player_df = df[df["offense_player"] == selected_player].copy()
    else:
        player_df = df[
            (df["offense_player"] == selected_player) &
            (df["off_team"] == selected_off_team)
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


# -----------------------------
# Sidebar controls
# -----------------------------
st.sidebar.header("Controls")

team_order = ["OKC", "SAS"]

offense_options = []

for team in team_order:
    team_players = sorted(
        df[df["off_team"] == team]["offense_player"]
        .dropna()
        .unique()
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

default_value = (
    "SAS|Victor Wembanyama"
    if "SAS|Victor Wembanyama" in offense_values
    else offense_values[0]
)

selected_offense_key = st.sidebar.selectbox(
    "Offense Player",
    options=offense_values,
    index=offense_values.index(default_value),
    format_func=lambda x: label_by_value[x]
)

selected_off_team, selected_player = parse_player_key(selected_offense_key)

temp = df[
    (df["off_team"] == selected_off_team) &
    (df["offense_player"] == selected_player)
].copy()

defender_order = (
    temp.groupby("defense_player")["matchup_seconds"]
    .sum()
    .sort_values(ascending=False)
    .index
    .tolist()
)

defender_options = ["All Defenders"] + defender_order

highlight_defender = st.sidebar.selectbox(
    "Defense Player",
    options=defender_options
)


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

result = make_matchup_timeline(
    selected_player=selected_player,
    selected_off_team=selected_off_team,
    highlight_defender=highlight_defender
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
        player_df=player_df,
        selected_player=selected_player
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
        concentration_display["Primary Share %"] = (
            concentration_display["Primary Share %"].round(1)
        )
        concentration_display["Top-2 Share %"] = (
            concentration_display["Top-2 Share %"].round(1)
        )
        concentration_display["HHI"] = concentration_display["HHI"].round(3)
        concentration_display["Effective Defenders"] = (
            concentration_display["Effective Defenders"].round(2)
        )

        st.dataframe(
            concentration_display,
            use_container_width=True,
            hide_index=True
        )

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

            previous_outcome = outcome_df[
                outcome_df["Game"] == previous_game_label
            ]
            current_outcome = outcome_df[
                outcome_df["Game"] == current_game_label
            ]

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
                    f'{current_outcome["PTS/75"]:.1f}',
                    f'{current_outcome["PTS/75"] - previous_outcome["PTS/75"]:+.1f}'
                )

                out_col2.metric(
                    "eFG%",
                    f'{current_outcome["eFG%"]:.1f}%',
                    f'{current_outcome["eFG%"] - previous_outcome["eFG%"]:+.1f} pp'
                )

                out_col3.metric(
                    "TOV/75",
                    f'{current_outcome["TOV/75"]:.1f}',
                    f'{current_outcome["TOV/75"] - previous_outcome["TOV/75"]:+.1f}'
                )

        outcome_display = outcome_df[[
            "Game",
            "players_pts",
            "partial_poss",
            "PTS/75",
            "eFG%",
            "TOV/75"
        ]].copy()

        outcome_display = outcome_display.rename(columns={
            "players_pts": "Player PTS",
            "partial_poss": "Partial Poss"
        })

        for column in ["Partial Poss", "PTS/75", "eFG%", "TOV/75"]:
            outcome_display[column] = outcome_display[column].round(1)

        st.dataframe(
            outcome_display,
            use_container_width=True,
            hide_index=True
        )

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
            f'{largest_adjustment["Adjustment Score"]:.3f}',
            f'{largest_adjustment["From"]} → {largest_adjustment["To"]}'
        )
        metric_col2.metric(
            "Largest Defender Share Shift",
            f'{largest_adjustment["Share Change (pp)"]:+.1f} pp',
            largest_adjustment["Largest Share Change"]
        )

        adjustment_display = adjustment_df.copy()
        adjustment_display["Adjustment Score"] = (
            adjustment_display["Adjustment Score"].round(3)
        )
        adjustment_display["Share Change (pp)"] = (
            adjustment_display["Share Change (pp)"].round(1)
        )

        st.dataframe(
            adjustment_display,
            use_container_width=True,
            hide_index=True
        )

    if selected_player == "Victor Wembanyama" and selected_off_team == "SAS":
        st.markdown(
            """
    ### Key Insight

    The clearest signal is the shift in matchup allocation.  
    For Victor Wembanyama, OKC did not use one fixed defensive matchup across the series.

    The largest game-to-game change occurred from **Game 1 to Game 2**, when the Adjustment Score reached **0.620**. Hartenstein's matchup share increased by roughly **53 percentage points**, while Caruso's fell by about **30 points**.

    That change also made the assignment more concentrated: the primary defender share rose from **36.2% to 54.6%**, while HHI increased from **0.204 to 0.340**.

    Game 3 then moved toward a near-even Holmgren–Hartenstein split. The top two defenders still accounted for **67.5%** of Wembanyama's recorded matchup time even though neither defender individually exceeded 34%.

    This is exactly the type of adjustment that can be hidden in series-level matchup totals.
    """
        )
    else:
        st.markdown(
            f"""
    ### Key Insight

    This view shows how defensive matchup responsibility changed game by game for **{selected_player}**.

    The main signal is not single-game efficiency, which can be noisy in small samples.  
    The more reliable signal is **matchup allocation**: who guarded the offensive player, how much time they spent on that assignment, and whether that responsibility changed across the series.
    """
        )

    st.subheader("Primary Defender Summary")

    st.caption(
    "Primary and secondary defenders are ranked by matchup time within each game."
    )

    summary = (
        player_df.sort_values(["game", "rank_in_game"])
        .groupby("game")
        .head(2)
        .copy()
    )

    summary["role"] = summary["rank_in_game"].map({
        1.0: "Primary",
        2.0: "Secondary"
    })

    summary_table = summary[[
        "game_label",
        "role",
        "defense_player",
        "matchup_time_label",
        "matchup_share_time",
        "partial_poss",
        "players_pts",
        "pts_per_75"
    ]].copy()

    summary_table = summary_table.rename(columns={
        "game_label": "Game",
        "role": "Role",
        "defense_player": "Defender",
        "matchup_time_label": "Time",
        "matchup_share_time": "Time Share %",
        "partial_poss": "Partial Poss",
        "players_pts": "Player PTS",
        "pts_per_75": "PTS/75"
    })

    summary_table["Time Share %"] = summary_table["Time Share %"].round(1)
    summary_table["Partial Poss"] = summary_table["Partial Poss"].round(1)
    summary_table["PTS/75"] = summary_table["PTS/75"].round(1)

    st.dataframe(
        summary_table.reset_index(drop=True),
        use_container_width=True,
        hide_index=True
    )
    with st.expander("Project idea"):
        st.markdown(
            """
**Product concept:** Databallr's current matchup pages are useful for series-level totals.  
This prototype adds a **game-by-game timeline layer** so users can see when matchup responsibilities changed during a playoff series.

**Case study:** OKC vs SAS, with Victor Wembanyama on offense as the default view.

**Interpretation note:** Matchup time and matchup share are the primary signals. Efficiency stats are shown as supporting context, not definitive proof of individual defensive success.
"""
        )