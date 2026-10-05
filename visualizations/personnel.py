"""Parallel descriptive changes in matchup allocation and full-game playing time."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots


def make_personnel_change_chart(frame, from_game, to_game):
    if frame.empty or frame.share_change.dropna().empty:
        return None
    shown = frame[frame.share_change.notna()].copy()
    shown["_order"] = shown.share_change.abs()
    shown = shown.sort_values(["_order", "player_id"], ascending=[False, True]).head(10)
    names = [
        f"{row.player} ({row.player_id})"
        if shown.player.duplicated(keep=False).loc[i]
        else row.player
        for i, row in shown.iterrows()
    ]
    figure = make_subplots(
        rows=1,
        cols=2,
        shared_yaxes=True,
        horizontal_spacing=0.13,
        subplot_titles=(
            "Recorded matchup share change",
            "Full-game playing time change",
        ),
    )
    for col, field, unit in ((1, "share_change", "pp"), (2, "minutes_change", "min")):
        figure.add_trace(
            go.Bar(
                x=shown[field].tolist(),
                y=names,
                orientation="h",
                marker_color=[
                    "#14b8a6" if value >= 0 else "#f59e0b" for value in shown[field]
                ],
                hovertemplate="%{y}<br>Change: %{x:+.2f} " + unit + "<extra></extra>",
                showlegend=False,
            ),
            row=1,
            col=col,
        )
        figure.update_xaxes(
            title_text=unit, zeroline=True, zerolinecolor="#64748b", row=1, col=col
        )
    figure.update_yaxes(categoryorder="array", categoryarray=list(reversed(names)))
    figure.update_layout(
        title=f"Game {from_game} → Game {to_game}: defensive personnel context",
        template="plotly_dark",
        height=max(320, 36 * len(shown) + 130),
        margin={"l": 20, "r": 20, "t": 100, "b": 45},
    )
    return figure
