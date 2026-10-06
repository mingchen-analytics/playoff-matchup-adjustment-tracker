"""Phase 5: league-level transition table and findings.

Works on either dataset:

* ``league`` - ``data/league/*.csv.gz`` from ``scripts/fetch_playoffs.py``
* ``dev``    - the seven bundled API series (development sample)

Definitions fixed here, before results are read:

* Primary offensive player: averages >= 28 minutes over the series games he
  played AND ranks top-2 on his team in usage per game, usage = FGA + 0.44 FTA
  + turnovers (box score). Independent of the matchup data being studied.
* Robust adjustment: league-level BH q < 0.10 on BOTH the time and the
  possession noise bases.
* Blowout: final margin of 20+ points in either game of the transition.
* Defending team: the offensive player's opponent; "after a loss" means the
  defending team lost the earlier game of the transition.
* Outcomes (box score): points per 36 minutes and true-shooting percentage,
  each as a deviation from the player's own mean over his *other* games in the
  series, so a player is compared with himself.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from analytics.decomposition import decompose_series
from analytics.measures import matchup_measures
from analytics.null_model import benjamini_hochberg, series_noise
from data_sources.league_fetch import discover_playoff_games
from research.data import ROOT, api_series_ids, load_matchups

PRIMARY_MIN_MINUTES = 28
PRIMARY_TOP_USAGE = 2
Q = 0.10
BLOWOUT_MARGIN = 20
KEYS = ["series_id", "off_player_id", "from_game", "to_game"]


def league_available(root=ROOT):
    return (Path(root) / "data/league/matchups.csv.gz").exists()


def _two_sided(log):
    """The bundled context files keep one team's row per game; add the other."""
    log = log.copy()
    one = log.groupby("GAME_ID").GAME_ID.transform("size").eq(1)
    single = log[one]
    if single.empty:
        return log
    parts = single.MATCHUP.str.extract(r"^(\w+) (vs\.|@) (\w+)$")
    other = single.copy()
    other["TEAM_ABBREVIATION"] = parts[2]
    other["MATCHUP"] = parts[2] + parts[1].map({"vs.": " @ ", "@": " vs. "}) + parts[0]
    other["WL"] = single.WL.map({"W": "L", "L": "W"})
    other["PTS"] = single.PTS - single.PLUS_MINUS
    other["PLUS_MINUS"] = -single.PLUS_MINUS
    return pd.concat([log, other], ignore_index=True)


def load_dataset(source="auto", root=ROOT):
    """List of (series_id, matchups, boxscores, games) for the chosen source."""
    if source == "auto":
        source = "league" if league_available(root) else "dev"
    if source == "league":
        base = Path(root) / "data/league"
        matchups = pd.read_csv(base / "matchups.csv.gz", dtype={"game_id": str})
        boxes = pd.read_csv(base / "boxscores.csv.gz", dtype={"game_id": str})
        games = pd.read_csv(base / "games.csv.gz", dtype={"game_id": str})
        bundles = [
            (sid, m, boxes[boxes.series_id.eq(sid)], games[games.series_id.eq(sid)])
            for sid, m in matchups.groupby("series_id")
        ]
        return source, bundles
    if source != "dev":
        raise ValueError("source must be auto, league or dev")
    bundles = []
    for sid in api_series_ids(root):
        matchups = load_matchups(sid, root)
        boxes = pd.read_csv(Path(root) / "data/player_context" / f"{sid}.csv",
                            dtype={"game_id": str}).assign(series_id=sid)
        log = pd.read_csv(Path(root) / "data/context" / f"{sid}.csv",
                          dtype={"GAME_ID": str, "SEASON_ID": str})
        games = discover_playoff_games(_two_sided(log), matchups.season.iloc[0]).assign(series_id=sid)
        bundles.append((sid, matchups, boxes, games))
    return source, bundles


def primary_players(boxes):
    """(series_id, player_id) rows with mpg, usage rank and the primary flag."""
    played = boxes[boxes.played.astype(bool) & boxes.minutes_seconds.notna()].copy()
    played["usage"] = played.fga + 0.44 * played.fta + played.turnovers
    per = played.groupby(["series_id", "team", "player_id"]).agg(
        games=("game_id", "nunique"),
        mpg=("minutes_seconds", lambda s: s.mean() / 60),
        usage=("usage", "mean"),
    ).reset_index()
    per["usage_rank"] = per.groupby(["series_id", "team"]).usage.rank(
        ascending=False, method="first")
    per["primary"] = per.mpg.ge(PRIMARY_MIN_MINUTES) & per.usage_rank.le(PRIMARY_TOP_USAGE)
    return per


def player_outcomes(boxes):
    """Per player-game points/36 and TS%, plus deviation from his other games."""
    played = boxes[boxes.played.astype(bool) & boxes.minutes_seconds.gt(0)].copy()
    played["pts36"] = played.points / played.minutes_seconds * 36 * 60
    attempts = 2 * (played.fga + 0.44 * played.fta)
    played["ts"] = (played.points / attempts).where(attempts > 0)
    keys = ["series_id", "player_id"]
    for col in ("pts36", "ts"):
        total = played.groupby(keys)[col].transform("sum")
        count = played.groupby(keys)[col].transform("count")
        other_mean = (total - played[col]) / (count - 1)
        played[f"{col}_dev"] = (played[col] - other_mean).where(count > 1)
    return played[keys + ["game_number", "pts36", "ts", "pts36_dev", "ts_dev"]]


def series_transitions(series_id, matchups, boxes, games, simulations, seed):
    measures = matchup_measures(matchups)
    decomposition = decompose_series(measures)
    noise = {}
    for basis in ("time", "possessions"):
        table, _ = series_noise(measures, simulations, seed, basis=basis)
        noise[basis] = table[["off_player_id", "from_game", "to_game", "tvd",
                              "null_median", "excess_tvd", "p_value",
                              "possessions_before", "possessions_after"]]
    frame = decomposition.merge(
        noise["time"].drop(columns="tvd"), on=["off_player_id", "from_game", "to_game"]
    ).merge(
        noise["possessions"].rename(columns=lambda c: c if c in KEYS else f"{c}_poss")
        .drop(columns=["possessions_before_poss", "possessions_after_poss"]),
        on=["off_player_id", "from_game", "to_game"], how="left",
    )
    frame.insert(0, "series_id", series_id)
    teams = measures.drop_duplicates("off_player_id").set_index("off_player_id").off_team
    frame["off_team"] = frame.off_player_id.map(teams)

    result = games.set_index(["team", "game_number"])
    opponent = games.drop_duplicates("team").set_index("team").opponent
    frame["def_team"] = frame.off_team.map(opponent)
    frame["def_lost_before"] = [
        result.wl.get((t, g)) == "L" for t, g in zip(frame.def_team, frame.from_game)
    ]
    margin = games.drop_duplicates("game_number").set_index("game_number").margin.abs()
    frame["blowout"] = (frame.from_game.map(margin).ge(BLOWOUT_MARGIN)
                        | frame.to_game.map(margin).ge(BLOWOUT_MARGIN))

    roles = primary_players(boxes)
    roles = roles[roles.series_id.eq(series_id)].set_index("player_id")
    frame["primary"] = frame.off_player_id.map(roles.primary).fillna(False).astype(bool)
    frame["mpg"] = frame.off_player_id.map(roles.mpg)

    outcomes = player_outcomes(boxes).set_index(["player_id", "game_number"])
    for col in ("pts36_dev", "ts_dev"):
        frame[f"{col}_before"] = [outcomes[col].get((p, g)) for p, g in zip(frame.off_player_id, frame.from_game)]
        frame[f"{col}_after"] = [outcomes[col].get((p, g)) for p, g in zip(frame.off_player_id, frame.to_game)]
    return frame


def build_transitions(bundles, simulations=2000, seed=20261005):
    frames = [
        series_transitions(sid, m, b, g, simulations, seed + i)
        for i, (sid, m, b, g) in enumerate(bundles)
    ]
    table = pd.concat(frames, ignore_index=True)
    table["q_time"] = benjamini_hochberg(table.p_value)
    table["q_poss"] = benjamini_hochberg(table.p_value_poss.fillna(1.0))
    table["robust"] = table.q_time.lt(Q) & table.q_poss.lt(Q)
    return table


def cluster_bootstrap(table, statistic, draws=2000, seed=0):
    """Point estimate and 95% interval, resampling whole series."""
    rng = np.random.default_rng(seed)
    groups = {sid: g for sid, g in table.groupby("series_id")}
    ids = list(groups)
    point = statistic(table)
    values = []
    for _ in range(draws):
        sample = pd.concat([groups[s] for s in rng.choice(ids, len(ids))], ignore_index=True)
        value = statistic(sample)
        if value is not None and np.isfinite(value):
            values.append(value)
    if not values or point is None:
        return {"estimate": point, "low": None, "high": None}
    return {"estimate": float(point), "low": float(np.quantile(values, 0.025)),
            "high": float(np.quantile(values, 0.975))}


def _rate(frame, mask=None):
    frame = frame if mask is None else frame[mask(frame)]
    return float(frame.robust.mean()) if len(frame) else np.nan


def _component_share(component):
    def share(frame):
        sub = frame[frame.robust & ~frame.low_coverage]
        return float(sub[component].sum() / sub.tvd.sum()) if len(sub) else np.nan
    return share


def _loss_gap(frame):
    lost, won = frame[frame.def_lost_before], frame[~frame.def_lost_before]
    if not len(lost) or not len(won):
        return np.nan
    return float(lost.robust.mean() - won.robust.mean())


def _outcome_coefficient(column):
    def coefficient(frame):
        data = frame[[f"{column}_after", f"{column}_before", "robust"]].dropna()
        if len(data) < 8 or data.robust.nunique() < 2:
            return np.nan
        x = np.column_stack([np.ones(len(data)), data.robust.astype(float),
                             data[f"{column}_before"].astype(float)])
        beta, *_ = np.linalg.lstsq(x, data[f"{column}_after"].astype(float), rcond=None)
        return float(beta[1])
    return coefficient


def findings(table, draws=2000):
    base = table[table.game_gap.eq(1)]
    primary = base[base.primary]
    out = {"transitions": int(len(base)), "series": int(base.series_id.nunique()),
           "primary_transitions": int(len(primary)),
           "primary_players": int(primary.off_player_id.nunique())}
    for label, sample in (("all", primary), ("no_blowouts", primary[~primary.blowout])):
        block = {"n": int(len(sample))}
        if len(sample) and sample.series_id.nunique() > 1:
            block["robust_rate_primary"] = cluster_bootstrap(sample, _rate, draws)
            large = sample[sample.tvd.ge(0.30)]
            block["large_raw_changes"] = int(len(large))
            block["large_raw_surviving_noise"] = float(large.robust.mean()) if len(large) else None
            for component in ("overlap", "assignment", "entry_exit"):
                block[f"share_{component}"] = cluster_bootstrap(
                    sample, _component_share(component), draws)
            block["robust_rate_after_def_loss"] = _rate(sample, lambda f: f.def_lost_before)
            block["robust_rate_after_def_win"] = _rate(sample, lambda f: ~f.def_lost_before)
            block["loss_minus_win"] = cluster_bootstrap(sample, _loss_gap, draws)
            for column in ("pts36_dev", "ts_dev"):
                block[f"robust_coef_{column}"] = cluster_bootstrap(
                    sample, _outcome_coefficient(column), draws)
        out[label] = block
    bench = base[~base.primary]
    out["robust_rate_non_primary"] = float(bench.robust.mean()) if len(bench) else None
    out["robust_rate_primary_point"] = float(primary.robust.mean()) if len(primary) else None
    out["low_coverage_share_primary"] = float(primary.low_coverage.mean()) if len(primary) else None
    out["blowout_share_primary"] = float(primary.blowout.mean()) if len(primary) else None
    return out
