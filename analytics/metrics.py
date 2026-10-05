"""Core analytics for playoff matchup adjustment analysis."""

import pandas as pd


def seconds_to_label(seconds):
    minutes = int(seconds) // 60
    sec = int(seconds) % 60
    return f"{minutes}:{sec:02d}"


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


def calculate_transition_share_changes(player_df, from_game, to_game):
    """
    Compares defender matchup shares between two selected games.
    """
    if player_df.empty:
        return pd.DataFrame()

    transition_df = player_df[
        player_df["game"].isin([from_game, to_game])
    ].copy()

    if transition_df["game"].nunique() < 2:
        return pd.DataFrame()

    grouped = (
        transition_df.groupby(["game", "defense_player"], as_index=False)["matchup_seconds"]
        .sum()
    )

    grouped["game_total_seconds"] = (
        grouped.groupby("game")["matchup_seconds"].transform("sum")
    )

    grouped["matchup_share_pct"] = (
        grouped["matchup_seconds"]
        / grouped["game_total_seconds"]
        * 100
    )

    share_matrix = (
        grouped
        .pivot(index="defense_player", columns="game", values="matchup_share_pct")
        .fillna(0)
    )

    time_matrix = (
        grouped
        .pivot(index="defense_player", columns="game", values="matchup_seconds")
        .fillna(0)
    )

    for game in [from_game, to_game]:
        if game not in share_matrix.columns:
            share_matrix[game] = 0
        if game not in time_matrix.columns:
            time_matrix[game] = 0

    comparison = pd.DataFrame({
        "Defender": share_matrix.index,
        "From Share %": share_matrix[from_game].values,
        "To Share %": share_matrix[to_game].values,
        "Share Change (pp)": (
            share_matrix[to_game].values
            - share_matrix[from_game].values
        ),
        "From Time": [
            seconds_to_label(value)
            for value in time_matrix[from_game].values
        ],
        "To Time": [
            seconds_to_label(value)
            for value in time_matrix[to_game].values
        ]
    })

    comparison["Absolute Change"] = (
        comparison["Share Change (pp)"].abs()
    )

    return comparison.sort_values(
        "Absolute Change",
        ascending=False
    ).reset_index(drop=True)


def calculate_series_adjustment_leaderboard(
    data,
    min_games=5,
    min_matchup_minutes=30
):
    """
    Ranks offensive players by their largest game-to-game matchup redistribution.

    Eligibility filters are explicit because low-volume matchup samples can create
    very large share swings that are not necessarily meaningful strategic changes.
    """
    records = []

    for (off_team, offense_player), player_df in data.groupby(
        ["off_team", "offense_player"]
    ):
        player_df = player_df.copy()
        game_count = player_df["game"].nunique()
        total_matchup_minutes = player_df["matchup_seconds"].sum() / 60

        if game_count < 2:
            continue

        adjustment_df = calculate_adjustment_scores(player_df)
        concentration_df = calculate_matchup_concentration(player_df)

        if adjustment_df.empty:
            continue

        largest = adjustment_df.loc[
            adjustment_df["Adjustment Score"].idxmax()
        ]

        primary_by_game = (
            player_df.groupby(["game", "defense_player"], as_index=False)["matchup_seconds"]
            .sum()
            .sort_values(["game", "matchup_seconds"], ascending=[True, False])
            .groupby("game")
            .head(1)
            .sort_values("game")
        )

        primary_defenders = primary_by_game["defense_player"].tolist()
        primary_changes = sum(
            current != previous
            for previous, current in zip(
                primary_defenders[:-1],
                primary_defenders[1:]
            )
        )

        records.append({
            "Team": off_team,
            "Player": offense_player,
            "Games": game_count,
            "Matchup Min": total_matchup_minutes,
            "Largest Adjustment": largest["Adjustment Score"],
            "Largest Transition": (
                f'{largest["From"]} → {largest["To"]}'
            ),
            "Average Adjustment": adjustment_df["Adjustment Score"].mean(),
            "Primary Changes": primary_changes,
            "Average HHI": (
                concentration_df["HHI"].mean()
                if not concentration_df.empty
                else 0
            )
        })

    leaderboard = pd.DataFrame(records)

    if leaderboard.empty:
        return leaderboard

    leaderboard = leaderboard[
        (leaderboard["Games"] >= min_games)
        & (leaderboard["Matchup Min"] >= min_matchup_minutes)
    ].copy()

    leaderboard = leaderboard.sort_values(
        ["Largest Adjustment", "Average Adjustment"],
        ascending=[False, False]
    ).reset_index(drop=True)

    leaderboard.insert(0, "Rank", range(1, len(leaderboard) + 1))

    return leaderboard


def describe_change(current_value, previous_value, unit="", decimals=1):
    delta = current_value - previous_value

    if abs(delta) < 10 ** (-decimals):
        return f"was essentially unchanged at {current_value:.{decimals}f}{unit}"

    direction = "rose" if delta > 0 else "fell"
    return (
        f"{direction} from {previous_value:.{decimals}f}{unit} "
        f"to {current_value:.{decimals}f}{unit}"
    )


def build_adjustment_event_summary(
    selected_player,
    adjustment_df,
    concentration_df,
    outcome_df
):
    """
    Builds a rule-based summary of the largest game-to-game matchup adjustment.
    The language is descriptive and intentionally avoids causal attribution.
    """
    if adjustment_df.empty:
        return None

    largest = adjustment_df.loc[
        adjustment_df["Adjustment Score"].idxmax()
    ]

    previous_game = largest["From"]
    current_game = largest["To"]
    score = largest["Adjustment Score"]
    defender = largest["Largest Share Change"]
    share_delta = largest["Share Change (pp)"]

    if share_delta > 0:
        share_sentence = (
            f"{defender}'s matchup share increased by "
            f"{abs(share_delta):.1f} percentage points."
        )
    elif share_delta < 0:
        share_sentence = (
            f"{defender}'s matchup share decreased by "
            f"{abs(share_delta):.1f} percentage points."
        )
    else:
        share_sentence = (
            f"{defender}'s matchup share was essentially unchanged."
        )

    sentences = [
        (
            f"The largest matchup redistribution for **{selected_player}** occurred "
            f"from **{previous_game} to {current_game}**, with an Adjustment Score "
            f"of **{score:.3f}**."
        ),
        share_sentence
    ]

    previous_concentration = concentration_df[
        concentration_df["Game"] == previous_game
    ]
    current_concentration = concentration_df[
        concentration_df["Game"] == current_game
    ]

    if not previous_concentration.empty and not current_concentration.empty:
        previous_concentration = previous_concentration.iloc[0]
        current_concentration = current_concentration.iloc[0]

        previous_primary = previous_concentration["Primary Defender"]
        current_primary = current_concentration["Primary Defender"]

        if previous_primary != current_primary:
            sentences.append(
                f"The primary matchup changed from **{previous_primary}** "
                f"({previous_concentration['Primary Share %']:.1f}%) to "
                f"**{current_primary}** "
                f"({current_concentration['Primary Share %']:.1f}%)."
            )
        else:
            sentences.append(
                f"**{current_primary}** remained the primary matchup, while "
                + describe_change(
                    current_concentration["Primary Share %"],
                    previous_concentration["Primary Share %"],
                    unit="%",
                    decimals=1
                )
                + "."
            )

        hhi_delta = (
            current_concentration["HHI"]
            - previous_concentration["HHI"]
        )

        if abs(hhi_delta) < 0.005:
            concentration_direction = "remained similarly concentrated"
        elif hhi_delta > 0:
            concentration_direction = "became more concentrated"
        else:
            concentration_direction = "became more distributed"

        sentences.append(
            f"The overall matchup allocation **{concentration_direction}** "
            f"(HHI {previous_concentration['HHI']:.3f} → "
            f"{current_concentration['HHI']:.3f})."
        )

    previous_outcome = outcome_df[
        outcome_df["Game"] == previous_game
    ]
    current_outcome = outcome_df[
        outcome_df["Game"] == current_game
    ]

    if not previous_outcome.empty and not current_outcome.empty:
        previous_outcome = previous_outcome.iloc[0]
        current_outcome = current_outcome.iloc[0]

        pts_change = describe_change(
            current_outcome["PTS/75"],
            previous_outcome["PTS/75"],
            decimals=1
        )
        efg_change = describe_change(
            current_outcome["eFG%"],
            previous_outcome["eFG%"],
            unit="%",
            decimals=1
        )
        tov_change = describe_change(
            current_outcome["TOV/75"],
            previous_outcome["TOV/75"],
            decimals=1
        )

        outcome_sentence = (
            f"Over the same transition, PTS/75 {pts_change}, "
            f"eFG% {efg_change}, and TOV/75 {tov_change}."
        )
        sentences.append(outcome_sentence)

    sentences.append(
        "*Outcome changes are descriptive context only and should not be "
        "interpreted as evidence that the matchup adjustment caused the result.*"
    )

    return "\n\n".join(sentences)
