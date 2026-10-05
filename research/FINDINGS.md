# Measurement research: phases 1–3

Status as of 2026-10-05 on the `rebuild` branch. Development sample: the seven
bundled API series (39 games, 7,432 matchup rows). Everything below is
regenerated offline by:

```bash
python -m research.run_measure_audit
python -m research.run_decomposition
python -m research.run_noise_model        # --simulations 4000 --seed 20261005
```

Outputs land in `research/results/`. The library code is in
`analytics/measures.py`, `analytics/decomposition.py` and
`analytics/null_model.py`; tests in `tests/test_measurement_research.py`.

The core claim this work sets up:

> Observed matchup change = overlap opportunity (rotation) + assignment choice
> + sampling noise.

## Phase 1 — what the NBA percentage fields measure

Neither NBA.com nor the `nba_api` endpoint documentation defines
`percentageDefenderTotalTime`, `percentageOffensiveTotalTime` or
`percentageTotalTimeBothOn` (field names only). The interpretation is therefore
established from identities in the data (`research/results/measure_audit.json`):

| Check | Result |
| --- | --- |
| `off_time_percent` summed over defenders, per offensive player-game | median 100.0 in every series |
| `def_time_percent` summed over offensive players, per defender-game | median 100.0 in every series |
| Implied overlap O = M ÷ (`both_on_percent`/100), summed over recorded defenders ÷ recorded matchup time | median 4.70–4.88 by series |
| O above either player's full-game minutes, matchups ≥ 30 s | 0 rows |
| Same, matchups < 30 s | 18 rows, all ≤ 20 s (one-decimal rounding) |
| `both_on_percent` rounded to 0 with recorded time | 23 of 7,432 rows |

Consequences:

- `off_time_percent` **is** the existing matchup share S.
- `both_on_percent` is an assignment rate A: of the time both players were on
  the floor while the offensive player was tracked on offense, the fraction this
  defender guarded him. The ≈5× sum matches five defenders sharing the floor.
- Overlap opportunity O is in tracked-offense seconds, **not** box-score
  minutes; minutes are context only. O exists only for defenders with a
  recorded matchup, and is missing where A rounds to 0.
- Three measures are kept side by side: S (realized workload, sums to 100%,
  used by TVD), A (tendency when available), O (opportunity), with M = O × A.

## Phase 2 — rotation, assignment and entry/exit

Each transition's share change is split with a two-factor Shapley average over
defenders measurable in both games; defenders seen in only one game (or with A
rounded to 0) form an explicit entry/exit part. TVD is attributed by the sign
of each defender's change, so the three parts add to the TVD exactly. f(O, A)
is scale-free, so a longer overtime game is not counted as rotation.

**Case: Wembanyama, OKC–SAS Game 1 → Game 2** (API snapshot; Game 1 went to
double overtime). TVD 0.648 = rotation 0.310 + assignment 0.333 + entry/exit
0.005.

| Defender | Share G1 → G2 | Change | Rotation | Assignment |
| --- | ---: | ---: | ---: | ---: |
| Isaiah Hartenstein | 1.6% → 58.3% | +56.7 pp | +38.4 | +19.6 |
| Alex Caruso | 36.2% → 6.5% | −29.7 pp | −3.2 | −26.5 |
| Jalen Williams | 17.8% → 2.5% | −15.3 pp | −10.1 | −5.2 |
| Luguentz Dort | 13.2% → 1.3% | −11.9 pp | −2.2 | −9.7 |
| Chet Holmgren | 12.3% → 18.0% | +5.7 pp | −7.0 | +13.1 |

Reading: OKC gave Hartenstein far more floor time with Wembanyama *and* used
him on Wembanyama more often when both were on (A 29% → 76%); Caruso's drop is
almost entirely a choice, not a rotation effect. The adjustment was about half
rotation and half assignment.

Development-sample observation (not a league finding): across 123 transitions
that are not flagged uncertain and have league q < 0.10, assignment accounts for
49% of summed TVD, rotation 35%, entry/exit 16%.

## Phase 3 — sampling-noise baseline

Parametric bootstrap, not a permutation test: the data are aggregated per game.
Stated assumptions:

1. A game behaves like n independent draws from the defender shares, n = the
   offensive player's partial possessions, rounded.
2. Draws are independent. Real matchups come in stretches, so this
   **understates** noise; significance here is optimistic.

Per transition: observed TVD, possessions, null median and 95th percentile,
excess TVD (observed − null median), p-value, q-value. Per player: the null of
the *largest* transition under a no-change series, which corrects for picking
each player's maximum. Benjamini–Hochberg q-values are computed within series
and pooled across all seven (`q_value_league`). Transitions whose null median
is ≥ 0.25 are flagged `uncertain` instead of being dropped by a minutes cutoff.
`game_gap` > 1 marks a transition across games the player missed.

| Quantity | Value |
| --- | ---: |
| Transitions | 681 |
| Flagged uncertain | 255 |
| Spanning missed games | 38 |
| League q < 0.10 | 182 |
| Players with max-adjusted league q < 0.10 | 71 of 183 |

The earlier informal audit reproduces from this code (both games ≥ 20
possessions, 477 transitions): median observed TVD 0.267 vs. null 0.192; 37.5%
above the null 95th percentile; correlation between TVD and the smaller game's
possessions −0.36. Wembanyama G1 → G2: excess 0.481, league q 0.006. His other
transitions in that series are not distinguishable from noise after Game 3.

The max-adjusted leaderboard is still led by low-volume bench players and by
transitions across missed games. Ranking only becomes meaningful once phase 5
restricts it to primary offensive players defined from box scores.

## Not done yet

- Phase 4: multi-season acquisition (`fetch_playoffs.py`, local machine only).
- Phase 5: primary offensive players, league findings with FDR, performance
  relative to the player's own baseline, README/app/article rewrite.
- The dashboard and its original leaderboard are unchanged; they will adopt
  these measures in the phase 5 rewrite.
- Block resampling needs stretch-level data and stays a future sensitivity check.
