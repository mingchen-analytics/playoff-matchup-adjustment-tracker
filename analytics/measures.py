"""Realized share (S), assignment rate (A) and overlap opportunity (O).

For one offensive player in one game, every recorded defender d has

    M_d  recorded matchup seconds
    S_d  = M_d / sum_j M_j                    realized matchup share
    A_d  = both_on_percent_d / 100            assignment rate
    O_d  = M_d / A_d                          overlap opportunity (seconds)

so that M_d = O_d * A_d exactly.

What the NBA percentage fields mean is not documented by NBA.com or nba_api
(field names only). The interpretation used here rests on identities that the
bundled data satisfy, checked by ``audit_measures``:

* ``off_time_percent`` sums to ~100 per offensive player-game, so it equals S.
* ``def_time_percent`` sums to ~100 per defender-game.
* O never exceeds either player's full-game minutes, and summed over the
  recorded defenders it is close to five times the offensive player's
  recorded matchup time (five defenders share the floor with him).

Therefore A reads as "of the time both players were on the floor while this
offensive player was being tracked on offense, the fraction this defender
guarded him". O is in tracked-offense seconds, not box-score minutes, and is
only observable for defenders with a recorded matchup: a defender who shared
the floor but never guarded him has no row.

``both_on_percent`` is published with one decimal, so a very small assignment
rate can round to 0. Those rows keep their M and S but have A and O missing.
"""

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = {
    "game_number",
    "off_player_id",
    "off_player",
    "off_team",
    "def_player_id",
    "def_player",
    "matchup_seconds",
    "partial_possessions",
    "both_on_percent",
    "off_time_percent",
    "def_time_percent",
}
KEY = ["game_number", "off_player_id", "def_player_id"]


def matchup_measures(snapshot):
    """One row per game, offensive player and defender with M, S, A and O.

    ``snapshot`` uses the processed schema columns (``series_schema``) and
    must hold a single series.
    """
    missing = REQUIRED_COLUMNS - set(snapshot.columns)
    if missing:
        raise ValueError(f"Missing columns for matchup measures: {sorted(missing)}")
    if "series_id" in snapshot.columns and snapshot.series_id.nunique() > 1:
        raise ValueError("matchup_measures expects one series at a time.")
    if snapshot.duplicated(KEY).any():
        raise ValueError("Duplicate game/offensive/defensive player rows.")
    if (snapshot.matchup_seconds < 0).any():
        raise ValueError("Negative matchup seconds.")

    frame = snapshot[sorted(REQUIRED_COLUMNS)].copy()
    frame = frame.rename(columns={"matchup_seconds": "M"})
    group = frame.groupby(["game_number", "off_player_id"])
    frame["M_total"] = group.M.transform("sum")
    frame["S"] = frame.M / frame.M_total
    frame["A"] = (frame.both_on_percent / 100).where(frame.both_on_percent > 0)
    frame["O"] = frame.M / frame.A
    frame["measurable"] = frame.A.notna() & (frame.M > 0)
    frame["possessions"] = group.partial_possessions.transform("sum")
    return frame.sort_values(KEY).reset_index(drop=True)


def audit_measures(
    snapshot, player_minutes=None, min_total_seconds=300, min_row_seconds=30
):
    """Check the identities the S/A/O interpretation relies on.

    ``player_minutes`` optionally maps (game_number, player_id) to full-game
    seconds from the verified box score. Returns plain numbers so callers can
    serialise them.
    """
    frame = matchup_measures(snapshot)
    by_off = frame.groupby(["game_number", "off_player_id"])
    by_def = snapshot.groupby(["game_number", "def_player_id"])

    off_totals = by_off.M.sum()
    off_pct = by_off.off_time_percent.sum()[off_totals >= min_total_seconds]
    def_totals = by_def.matchup_seconds.sum()
    def_pct = by_def.def_time_percent.sum()[def_totals >= min_total_seconds]

    measurable = frame[frame.measurable]
    sum_o = measurable.groupby(["game_number", "off_player_id"]).O.sum()
    ratio = (sum_o / off_totals.reindex(sum_o.index))[
        off_totals.reindex(sum_o.index) >= min_total_seconds
    ]

    result = {
        "rows": int(len(frame)),
        "rows_assignment_rounded_to_zero": int(((frame.M > 0) & frame.A.isna()).sum()),
        "off_time_percent_sum_median": float(off_pct.median()),
        "off_time_percent_sum_within_1pt": float((off_pct.sub(100).abs() <= 1).mean()),
        "def_time_percent_sum_median": float(def_pct.median()),
        "def_time_percent_sum_within_1pt": float((def_pct.sub(100).abs() <= 1).mean()),
        "s_vs_off_time_percent_max_abs_pp": float(
            (frame.S * 100 - frame.off_time_percent).abs().max()
        ),
        "sum_o_over_recorded_time_median": float(ratio.median()),
        "sum_o_over_recorded_time_p10": float(ratio.quantile(0.10)),
        "sum_o_over_recorded_time_p90": float(ratio.quantile(0.90)),
        "player_games_checked": int(len(ratio)),
    }

    if player_minutes is not None:
        court = np.minimum(
            [player_minutes.get((g, p), np.nan) for g, p in zip(measurable.game_number, measurable.off_player_id)],
            [player_minutes.get((g, p), np.nan) for g, p in zip(measurable.game_number, measurable.def_player_id)],
        )
        over = pd.Series(measurable.O.to_numpy() / court, index=measurable.index)
        large = measurable.M >= min_row_seconds
        result["court_check_min_row_seconds"] = int(min_row_seconds)
        result["o_over_court_minutes_median"] = float(over[large].median())
        result["o_over_court_minutes_max"] = float(over[large].max())
        result["o_exceeds_court_minutes_rows"] = int((over[large] > 1).sum())
        # Below the threshold one-decimal rounding of both_on_percent dominates.
        result["o_exceeds_court_minutes_small_rows"] = int((over[~large] > 1).sum())
    return result
