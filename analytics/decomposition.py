"""Split a game-to-game matchup-share change into rotation, assignment and entry/exit.

With M = O x A (see ``analytics.measures``), a game's realized shares are

    f(O, A)_d = O_d A_d / sum_j O_j A_j

For a transition g1 -> g2 the change in realized share for every defender,
dS_d = S2_d - S1_d, is split into three parts that add up exactly:

* rotation    - change from moving overlap opportunity O while holding the
                assignment rates fixed,
* assignment  - change from moving assignment rates A while holding O fixed,
* entry/exit  - change carried by defenders that cannot be compared: a
                defender recorded in only one of the games, or whose A rounded
                to zero, plus the rescaling this forces on everyone else.

Rotation and assignment are computed on the defenders measurable in both games
("common") with a two-factor Shapley average, so the order of substitution
does not matter:

    rotation   = 1/2 [ f(O2,A1) - f(O1,A1) + f(O2,A2) - f(O1,A2) ]
    assignment = 1/2 [ f(O1,A2) - f(O1,A1) + f(O2,A2) - f(O2,A1) ]

TVD = 1/2 sum_d |dS_d| is not additive, so it is attributed with the sign of
each defender's total change: contribution_k = 1/2 sum_d sign(dS_d) k_d. The
three contributions sum to the TVD exactly; one can be negative when it
offsets the others.

Only O's relative distribution matters: f is invariant to scaling O, so a
longer (overtime) game does not by itself register as rotation.
"""

import numpy as np
import pandas as pd

COMPONENTS = ("rotation", "assignment", "entry_exit")


def _allocation(o, a):
    weight = o * a
    return weight / weight.sum()


def decompose_transition(measures, from_game, to_game):
    """Decompose one offensive player's transition.

    ``measures`` is ``analytics.measures.matchup_measures`` output filtered to
    one offensive player. Returns (per-defender frame, summary dict).
    """
    if measures.off_player_id.nunique() != 1:
        raise ValueError("Decompose one offensive player at a time.")
    games = {}
    for game in (from_game, to_game):
        rows = measures[measures.game_number.eq(game) & measures.M.gt(0)]
        if rows.empty:
            raise ValueError(f"No recorded matchups in game {game}.")
        games[game] = rows.set_index("def_player_id")

    first, second = games[from_game], games[to_game]
    defenders = first.index.union(second.index)
    s1 = (first.M / first.M.sum()).reindex(defenders, fill_value=0.0)
    s2 = (second.M / second.M.sum()).reindex(defenders, fill_value=0.0)
    change = s2 - s1

    common = first.index[first.measurable].intersection(
        second.index[second.measurable]
    )
    rotation = pd.Series(0.0, index=defenders)
    assignment = pd.Series(0.0, index=defenders)
    if len(common):
        o1, a1 = first.O[common], first.A[common]
        o2, a2 = second.O[common], second.A[common]
        base = _allocation(o1, a1)
        moved_o = _allocation(o2, a1)
        moved_a = _allocation(o1, a2)
        both = _allocation(o2, a2)
        rotation[common] = 0.5 * ((moved_o - base) + (both - moved_a))
        assignment[common] = 0.5 * ((moved_a - base) + (both - moved_o))
    entry_exit = change - rotation - assignment

    names = pd.concat([first.def_player, second.def_player])
    names = names[~names.index.duplicated(keep="last")]
    detail = pd.DataFrame(
        {
            "def_player": names.reindex(defenders),
            "share_before": s1,
            "share_after": s2,
            "share_change": change,
            "rotation": rotation,
            "assignment": assignment,
            "entry_exit": entry_exit,
            "comparable": defenders.isin(common),
        }
    )
    detail.index.name = "def_player_id"

    sign = np.sign(change)
    summary = {
        "from_game": int(from_game),
        "to_game": int(to_game),
        "game_gap": int(to_game - from_game),
        "tvd": float(0.5 * change.abs().sum()),
        **{k: float(0.5 * (sign * detail[k]).sum()) for k in COMPONENTS},
        "comparable_share_before": float(s1[common].sum()),
        "comparable_share_after": float(s2[common].sum()),
    }
    detail = detail.sort_values("share_change", key=np.abs, ascending=False)
    return detail.reset_index(), summary


def decompose_series(measures):
    """Summary rows for every adjacent transition of every offensive player.

    "Adjacent" means consecutive games in which the player has recorded
    matchups; ``game_gap`` > 1 marks a transition across games he missed.
    """
    rows = []
    for (player_id, player), player_rows in measures.groupby(
        ["off_player_id", "off_player"]
    ):
        games = sorted(player_rows.loc[player_rows.M > 0, "game_number"].unique())
        for from_game, to_game in zip(games[:-1], games[1:]):
            _, summary = decompose_transition(player_rows, from_game, to_game)
            rows.append({"off_player_id": player_id, "off_player": player, **summary})
    return pd.DataFrame(rows)
