"""Chronological event observations; no reconstructed player stints or lineups."""

import plotly.graph_objects as go


def make_event_timeline(frame, game_seconds, selected_person_id=None):
    fig = go.Figure()
    for kind, color, symbol in [
        ("Substitution", "#2878b5", "diamond"),
        ("Foul", "#d55e00", "circle"),
    ]:
        events = frame[frame.event_type == kind]
        if events.empty:
            continue
        lanes = events.team.replace({"": "Unassigned"}) + " · " + kind
        sizes = [
            14 if person == selected_person_id else 8 for person in events.person_id
        ]
        fig.add_trace(
            go.Scatter(
                x=events.elapsed_seconds / 60,
                y=lanes,
                mode="markers",
                name=kind,
                marker={
                    "color": color,
                    "symbol": symbol,
                    "size": sizes,
                    "opacity": 0.75,
                },
                customdata=events[
                    [
                        "period",
                        "clock",
                        "recorded_player",
                        "subtype",
                        "description",
                        "source_order",
                    ]
                ].values,
                hovertemplate="Period %{customdata[0]} · %{customdata[1]}<br>Recorded player: %{customdata[2]}<br>%{customdata[3]}<br>%{customdata[4]}<br>Source row: %{customdata[5]}<extra></extra>",
            )
        )
    boundaries = [12, 24, 36, 48] + list(range(53, int(game_seconds / 60) + 1, 5))
    for boundary in boundaries:
        if boundary < game_seconds / 60:
            fig.add_vline(x=boundary, line_dash="dot", line_color="#999999")
    fig.update_layout(
        title="Substitutions and Fouls",
        height=340,
        xaxis={"title": "Elapsed game minutes", "range": [0, game_seconds / 60]},
        yaxis={"title": ""},
        margin={"l": 150, "r": 25, "t": 55, "b": 55},
        legend={"orientation": "h"},
    )
    return fig
