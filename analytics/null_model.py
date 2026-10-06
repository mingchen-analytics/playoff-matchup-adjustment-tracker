"""Sampling-noise baselines for matchup-share changes.

The data are aggregated per game, so there is nothing to permute. The baseline
is a parametric bootstrap with two stated assumptions:

1. Sampling unit: a game's recorded allocation behaves like n independent
   draws from the defender shares, with n = the offensive player's partial
   possessions in that game, rounded (at least 1).

   The primary statistic is a *time* share (basis="time"), while n counts
   possessions, so unit and statistic do not match exactly: one possession can
   be split across defenders after a switch. As a robustness model,
   basis="possessions" tests possession shares (each defender's partial
   possessions / total), whose sampling unit matches n. Conclusions that hold
   on both bases are stronger; divergence is reported, not hidden.
2. Independence: draws are independent. Real matchups arrive in stretches,
   so this understates noise and makes the baseline too permissive. Results
   should be read as optimistic about detecting change.

Transitions run between consecutive games in which the player has recorded
matchups; ``game_gap`` > 1 marks one that spans games he did not play.

Per transition (two-game null): both games share one allocation, estimated by
pooling the two games' implied counts, n1 S1 + n2 S2.

Per player (series null, for the maximum): every game the player appears in
shares one allocation, pooled across the series. Simulated games are compared
in the same adjacent order, and the null distribution of the *largest* TVD is
used, so selecting each player's biggest transition is accounted for.

Reported per transition: observed TVD, possessions, null median and 95th
percentile, excess TVD (observed minus null median), and a one-sided p-value
with the +1 correction. ``high_noise`` (null median >= 0.25) is a display
heuristic for transitions where noise alone moves the allocation a lot; it is
not a significance rule and nothing is dropped because of it. Benjamini-Hochberg q-values are added across whatever
set of tests the caller pools.
"""

import numpy as np
import pandas as pd

DEFAULT_SIMULATIONS = 4000
DEFAULT_HIGH_NOISE_NULL_MEDIAN = 0.25
BASES = {"time": "M", "possessions": "partial_possessions"}


def _possession_units(possessions):
    return max(1, int(round(float(possessions))))


def _tvd_rows(left, right):
    return 0.5 * np.abs(left - right).sum(axis=-1)


def _game_shares(player_rows, basis="time"):
    """game -> (defender share vector over a shared index, possession units)."""
    if basis not in BASES:
        raise ValueError(f"basis must be one of {sorted(BASES)}")
    table = player_rows.pivot_table(
        index="game_number", columns="def_player_id", values=BASES[basis], aggfunc="sum",
        fill_value=0,
    ).astype(float)
    table = table[table.sum(axis=1) > 0]
    shares = table.div(table.sum(axis=1), axis=0)
    units = (
        player_rows.groupby("game_number").possessions.first().reindex(shares.index)
        .map(_possession_units)
    )
    return shares, units


def transition_noise(player_rows, simulations=DEFAULT_SIMULATIONS, rng=None,
                     high_noise_null_median=DEFAULT_HIGH_NOISE_NULL_MEDIAN,
                     basis="time"):
    """Two-game null for every adjacent transition of one offensive player."""
    rng = np.random.default_rng(rng)
    shares, units = _game_shares(player_rows, basis)
    games = shares.index.tolist()
    records = []
    for g1, g2 in zip(games[:-1], games[1:]):
        s1, s2 = shares.loc[g1].to_numpy(), shares.loc[g2].to_numpy()
        n1, n2 = int(units[g1]), int(units[g2])
        pooled = (n1 * s1 + n2 * s2) / (n1 + n2)
        x = rng.multinomial(n1, pooled, size=simulations) / n1
        y = rng.multinomial(n2, pooled, size=simulations) / n2
        null = _tvd_rows(x, y)
        observed = float(_tvd_rows(s1, s2))
        median = float(np.median(null))
        records.append({
            "from_game": int(g1),
            "to_game": int(g2),
            "game_gap": int(g2 - g1),
            "possessions_before": n1,
            "possessions_after": n2,
            "tvd": observed,
            "null_median": median,
            "null_p95": float(np.quantile(null, 0.95)),
            "excess_tvd": observed - median,
            "p_value": float((1 + (null >= observed - 1e-12).sum()) / (simulations + 1)),
            "high_noise": median >= high_noise_null_median,
        })
    return pd.DataFrame(records)


def player_max_noise(player_rows, simulations=DEFAULT_SIMULATIONS, rng=None,
                     basis="time"):
    """Series null for the player's largest adjacent-transition TVD."""
    rng = np.random.default_rng(rng)
    shares, units = _game_shares(player_rows, basis)
    if len(shares) < 2:
        return None
    s = shares.to_numpy()
    n = units.to_numpy()
    observed = _tvd_rows(s[:-1], s[1:])
    pooled = (n[:, None] * s).sum(axis=0) / n.sum()
    simulated = np.stack(
        [rng.multinomial(k, pooled, size=simulations) / k for k in n], axis=1
    )
    null_max = _tvd_rows(simulated[:, :-1], simulated[:, 1:]).max(axis=1)
    best = int(np.argmax(observed))
    largest = float(observed[best])
    median = float(np.median(null_max))
    return {
        "games": int(len(n)),
        "total_possessions": int(n.sum()),
        "largest_tvd": largest,
        "largest_transition": f"{shares.index[best]}->{shares.index[best + 1]}",
        "largest_spans_missed_games": bool(shares.index[best + 1] - shares.index[best] > 1),
        "null_max_median": median,
        "null_max_p95": float(np.quantile(null_max, 0.95)),
        "excess_largest_tvd": largest - median,
        "p_value": float((1 + (null_max >= largest - 1e-12).sum()) / (simulations + 1)),
    }


def benjamini_hochberg(p_values):
    """BH-adjusted q-values in the input order."""
    p = np.asarray(p_values, dtype=float)
    if p.size == 0:
        return p
    order = np.argsort(p)
    ranked = p[order] * p.size / np.arange(1, p.size + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    q = np.empty_like(ranked)
    q[order] = np.minimum(ranked, 1.0)
    return q


def series_noise(measures, simulations=DEFAULT_SIMULATIONS, seed=0, basis="time"):
    """Transition table and max-adjusted player leaderboard for one series.

    q-values here are within the series; pool p-values across series and call
    ``benjamini_hochberg`` again for league-level claims.
    """
    rng = np.random.default_rng(seed)
    transitions, players = [], []
    for (player_id, player, team), rows in measures.groupby(
        ["off_player_id", "off_player", "off_team"]
    ):
        noise = transition_noise(rows, simulations, rng, basis=basis)
        if noise.empty:
            continue
        noise.insert(0, "off_team", team)
        noise.insert(0, "off_player", player)
        noise.insert(0, "off_player_id", player_id)
        transitions.append(noise)
        summary = player_max_noise(rows, simulations, rng, basis=basis)
        players.append({"off_player_id": player_id, "off_player": player,
                        "off_team": team, **summary})
    transitions = pd.concat(transitions, ignore_index=True)
    transitions["q_value"] = benjamini_hochberg(transitions.p_value)
    leaderboard = pd.DataFrame(players)
    leaderboard["q_value"] = benjamini_hochberg(leaderboard.p_value)
    leaderboard = leaderboard.sort_values("excess_largest_tvd", ascending=False)
    return transitions, leaderboard.reset_index(drop=True)
