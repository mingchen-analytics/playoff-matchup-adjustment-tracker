"""NBA Playoff Matchup Adjustment Research — interactive companion to research/.

    streamlit run app.py

Reads the precomputed transition table (research/results/league/) and
recomputes only the per-defender split for the selected transition. The V1
tracker dashboard is preserved as app_v1.py.
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analytics.decomposition import decompose_transition
from analytics.measures import matchup_measures

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "research" / "results" / "league"
OVERLAP, ASSIGNMENT, INK = "#2a78d6", "#eb6834", "#0b0b0b"
REPO = "https://github.com/mingchen-analytics/playoff-matchup-adjustment-tracker/blob/main"

st.set_page_config(page_title="Playoff Matchup Adjustment Research", layout="wide")


@st.cache_data
def load_transitions():
    for source in ("league", "dev"):
        path = RESULTS / f"transitions_{source}.csv"
        if path.exists():
            return source, pd.read_csv(path)
    return None, None


@st.cache_data
def load_matchups(source, series_id):
    if source == "league":
        frame = pd.read_csv(ROOT / "data/league/matchups.csv.gz", dtype={"game_id": str})
        return frame[frame.series_id.eq(series_id)]
    return pd.read_csv(ROOT / "data/snapshots" / f"{series_id}.csv", dtype={"game_id": str})


def series_label(series_id, table):
    rows = table[table.series_id.eq(series_id)]
    teams = " vs ".join(sorted(set(rows.off_team.dropna())))
    season = series_id.split("_")[0]
    return f"{teams} ({season})"


def defender_chart(detail):
    detail = detail.head(8).iloc[::-1]
    names = [f"{n}  {b:.0%} → {a:.0%}" for n, b, a in
             zip(detail.def_player, detail.share_before, detail.share_after)]
    fig = go.Figure()
    fig.add_bar(y=names, x=detail.overlap * 100, name="Overlap / rotation",
                orientation="h", marker_color=OVERLAP,
                hovertemplate="%{y}<br>Overlap %{x:+.1f} pp<extra></extra>")
    fig.add_bar(y=names, x=detail.assignment * 100, name="Assignment",
                orientation="h", marker_color=ASSIGNMENT,
                hovertemplate="%{y}<br>Assignment %{x:+.1f} pp<extra></extra>")
    fig.add_scatter(y=names, x=detail.share_change * 100, mode="markers", name="Net change",
                    marker=dict(symbol="line-ns", size=22, line=dict(width=3, color=INK)),
                    hovertemplate="%{y}<br>Net %{x:+.1f} pp<extra></extra>")
    fig.update_layout(barmode="relative", height=80 + 46 * len(detail),
                      margin=dict(l=10, r=10, t=10, b=40),
                      xaxis_title="Change in share of matchup time (percentage points)",
                      legend=dict(orientation="h", y=-0.25), bargap=0.35)
    fig.add_vline(x=0, line_width=1, line_color="#52514e")
    return fig


source, table = load_transitions()
st.title("NBA Playoff Matchup Adjustment Research")
st.markdown(
    "When a playoff team changes who guards a star, how much of the change is **who shared the "
    "floor** (overlap / rotation), how much is **who guarded him when both were on** "
    "(assignment), and is it bigger than sampling noise? "
    f"[Method]({REPO}/research/FINDINGS.md) · [Face-validity check]({REPO}/research/FACE_VALIDITY.md) · "
    f"[League findings]({REPO}/research/LEAGUE_FINDINGS.md)"
)
if table is None:
    st.error("No transition table found. Run `python -m research.run_league` first.")
    st.stop()
if source == "dev":
    st.caption("Showing the seven-series development sample. Significance is model-based; "
               "the model measures assignment allocation, not coaching intent.")

series_ids = sorted(table.series_id.unique(), key=lambda s: (s.split("_")[0], s), reverse=True)
default_series = next((i for i, s in enumerate(series_ids) if "okc_sas" in s), 0)
series_id = st.sidebar.selectbox("Series", series_ids, index=default_series,
                                 format_func=lambda s: series_label(s, table))
rows = table[table.series_id.eq(series_id) & table.game_gap.eq(1)]

players = (rows.groupby(["off_player_id", "off_player", "off_team"])
           .agg(primary=("primary", "max"), best=("excess_tvd", "max"))
           .reset_index().sort_values(["primary", "best"], ascending=False))
only_primary = st.sidebar.checkbox("Primary offensive players only", value=True)
if only_primary and players.primary.any():
    players = players[players.primary]
labels = {r.off_player_id: f"{r.off_player} ({r.off_team})" for r in players.itertuples()}
default_player = next((i for i, (pid, name) in enumerate(zip(players.off_player_id, players.off_player))
                       if name == "Victor Wembanyama"), 0)
player_id = st.sidebar.selectbox("Offensive player", list(labels), index=default_player,
                                 format_func=labels.get)
player_rows = rows[rows.off_player_id.eq(player_id)].sort_values("from_game")

st.subheader(f"{labels[player_id]}: game-to-game changes")
view = player_rows.assign(
    Transition=[f"G{a} → G{b}" for a, b in zip(player_rows.from_game, player_rows.to_game)],
    Robust=player_rows.robust.map({True: "yes", False: ""}),
    Notes=[", ".join(x for x, flag in (("blowout", b), ("low coverage", c), ("after def. loss", l)) if flag)
           for b, c, l in zip(player_rows.blowout, player_rows.low_coverage, player_rows.def_lost_before)],
)
st.dataframe(
    view[["Transition", "tvd", "null_median", "excess_tvd", "overlap", "assignment",
          "entry_exit", "coverage", "q_time", "q_poss", "Robust", "Notes"]]
    .rename(columns={"tvd": "TVD", "null_median": "Noise median", "excess_tvd": "Excess",
                     "overlap": "Overlap", "assignment": "Assignment", "entry_exit": "Entry/exit",
                     "coverage": "Coverage", "q_time": "q (time)", "q_poss": "q (poss.)"})
    .style.format({c: "{:.3f}" for c in ["TVD", "Noise median", "Excess", "Overlap",
                                          "Assignment", "Entry/exit", "Coverage", "q (time)",
                                          "q (poss.)"]}),
    hide_index=True, use_container_width=True,
)

options = [f"G{a} → G{b}" for a, b in zip(player_rows.from_game, player_rows.to_game)]
default_transition = int(player_rows.excess_tvd.reset_index(drop=True).idxmax()) if len(options) else 0
choice = st.selectbox("Transition", options, index=default_transition, key=f"transition_{series_id}")
row = player_rows.iloc[options.index(choice)]

cols = st.columns(4)
cols[0].metric("Total change (TVD)", f"{row.tvd:.3f}", f"noise median {row.null_median:.3f}",
               delta_color="off")
cols[1].metric("Overlap / rotation", f"{row.overlap:.3f}")
cols[2].metric("Assignment", f"{row.assignment:.3f}")
cols[3].metric("Entry / exit", f"{row.entry_exit:.3f}")
if row.low_coverage:
    st.warning(f"Low decomposition coverage ({row.coverage:.0%}): don't read the split precisely.")
if row.blowout:
    st.info("One of these games was decided by 20+ points; garbage-time units can shift matchups.")
if not row.robust:
    st.caption("Not robust: below q < 0.10 on at least one noise basis.")

measures = matchup_measures(load_matchups(source, series_id))
detail, _ = decompose_transition(measures[measures.off_player_id.eq(player_id)],
                                 int(row.from_game), int(row.to_game))
st.plotly_chart(defender_chart(detail), use_container_width=True)
st.caption("Each bar splits a defender's change in share of this player's matchup time. "
           "The black line is the net change.")
