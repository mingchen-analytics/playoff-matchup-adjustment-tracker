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


def make_segment_label(row):
    last_name = row["defense_player"].split()[-1]

    # Only show label for meaningful segments
    if row["matchup_seconds"] >= 90 or row["is_primary_defender"]:
        return last_name
    return ""


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
    if selected_player == "Victor Wembanyama" and selected_off_team == "SAS":
        st.markdown(
            """
    ### Key Insight

    The clearest signal is the shift in matchup allocation.  
    For Victor Wembanyama, OKC did not use one fixed defensive matchup across the series.

    The primary defender changed from Alex Caruso in Game 1 to Isaiah Hartenstein in Game 2, with Chet Holmgren and Hartenstein sharing the main responsibility in Game 3 before Hartenstein became the main matchup again in Games 4–5.

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