"""Pre-declared case selection for the face-validity check.

    python -m research.select_face_validity_cases

The rule is fixed here, before any press coverage is read, so the cases are
not hand-picked successes. Population: transitions between consecutive games
(game_gap == 1), comparable coverage >= 0.80, offensive player averaging
>= 28 minutes in the series (box score).

    A  assignment-dominant, robust: league q < 0.10 on both noise bases,
       assignment >= 2 x overlap. Top 4 by excess TVD, at most one per series.
    B  overlap-dominant, robust: same q rule, overlap >= 2 x assignment.
       Top 3 by excess TVD, at most one per series.
    C  large but noise-like: TVD >= 0.30 and league q >= 0.10 on both bases.
       Top 2 by TVD, different series.

Wembanyama OKC-SAS G1->G2 is the motivating case and is reported separately;
it was not selected blind.
"""

import pandas as pd

from research.data import RESULTS, ROOT, api_series_ids

MIN_COVERAGE = 0.80
MIN_MINUTES = 28
Q = 0.10


def minutes_per_game():
    frames = []
    for series_id in api_series_ids():
        players = pd.read_csv(ROOT / "data/player_context" / f"{series_id}.csv")
        played = players[players.played.astype(bool) & players.minutes_seconds.notna()]
        mpg = played.groupby("player_id").minutes_seconds.mean() / 60
        frames.append(mpg.rename("mpg").reset_index().assign(series_id=series_id))
    return pd.concat(frames).rename(columns={"player_id": "off_player_id"})


def one_per_series(frame, n, order):
    picked = frame.sort_values(order, ascending=False).drop_duplicates("series_id")
    return picked.head(n)


def select():
    decomposition = pd.read_csv(RESULTS / "decomposition_transitions.csv")
    noise = pd.read_csv(RESULTS / "basis_comparison.csv")
    keys = ["series_id", "off_player_id", "from_game", "to_game"]
    frame = decomposition.merge(
        noise[keys + ["q_value_league_time", "q_value_league_poss", "excess_tvd_time"]],
        on=keys,
    ).merge(minutes_per_game(), on=["series_id", "off_player_id"])
    eligible = frame[
        frame.game_gap.eq(1) & ~frame.low_coverage & frame.mpg.ge(MIN_MINUTES)
    ]
    robust = eligible[
        eligible.q_value_league_time.lt(Q) & eligible.q_value_league_poss.lt(Q)
    ]
    noisy = eligible[
        eligible.q_value_league_time.ge(Q) & eligible.q_value_league_poss.ge(Q)
        & eligible.tvd.ge(0.30)
    ]
    groups = [
        ("A assignment-dominant", one_per_series(
            robust[robust.assignment >= 2 * robust.overlap], 4, "excess_tvd_time")),
        ("B overlap-dominant", one_per_series(
            robust[robust.overlap >= 2 * robust.assignment], 3, "excess_tvd_time")),
        ("C large but noise-like", one_per_series(noisy, 2, "tvd")),
    ]
    selected = pd.concat([g.assign(group=name) for name, g in groups], ignore_index=True)
    columns = ["group", "series_id", "off_player", "from_game", "to_game", "tvd",
               "overlap", "assignment", "entry_exit", "coverage", "mpg",
               "excess_tvd_time", "q_value_league_time", "q_value_league_poss"]
    selected = selected[columns]
    selected.to_csv(RESULTS / "face_validity_cases.csv", index=False)
    return selected


if __name__ == "__main__":
    print(select().round(3).to_string(index=False))
