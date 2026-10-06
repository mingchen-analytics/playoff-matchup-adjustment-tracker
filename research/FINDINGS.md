# Measurement research: phases 1–3.5

Status as of 2026-10-05 on the `rebuild` branch. Development sample: the seven
bundled API series (39 games, 7,432 matchup rows). Everything below is
regenerated offline by:

```bash
python -m research.run_measure_audit
python -m research.run_decomposition
python -m research.run_noise_model        # --simulations 4000 --seed 20261005
```

Outputs land in `research/results/`. Library code: `analytics/measures.py`,
`analytics/decomposition.py`, `analytics/null_model.py`. Tests:
`tests/test_measurement_research.py`.

The framework this sets up:

> Observed matchup change = overlap opportunity (rotation) + assignment choice
> + sampling noise.

All p- and q-values below are **model-based, preliminary evidence**. They depend
on the stated sampling assumptions and are not final inferential results.

## Phase 1 — what the NBA percentage fields measure

Neither NBA.com nor the `nba_api` endpoint documentation defines
`percentageDefenderTotalTime`, `percentageOffensiveTotalTime` or
`percentageTotalTimeBothOn` (field names only). The reading below rests on
identities checked in `research/results/measure_audit.json`.

| Check | Result |
| --- | --- |
| `def_time_percent` summed over offensive players, per defender-game | 100 in every game |
| `off_time_percent` summed over defenders, per offensive player-game | 100 in 34 of 39 games |
| Same, in OKC–SAS G1, MIN–SAS G3/G4/G6, NYK–SAS G5 | off by a factor of 0.86–1.27 |
| Those 5 games after renormalizing `off_time_percent` within each player-game | max gap to S 2.75 pp (rounding on tiny rows) |
| Implied overlap O, summed over recorded defenders ÷ recorded matchup time | median 4.70–4.87; 5.01–5.13 in the 5 games |
| O above either player's full-game minutes, matchups ≥ 30 s | 0 rows |
| `both_on_percent` rounded to 0 with recorded time | 23 of 7,432 rows |

What this supports:

- **S is computed from matchup seconds, never taken from `off_time_percent`.**
  The published field closely reproduces S in most player-games, but in five
  games every defender's value for a player-game is off by the same factor.
  That pattern points to a different denominator on the source side, not a
  different allocation: renormalized, the field agrees with S. Acquisition
  metadata does not separate these games from clean ones fetched in the same
  batch. The cause is not established.
- `both_on_percent` reads as an assignment rate A: of the time both players
  were on the floor while the offensive player was tracked on offense, the
  fraction this defender guarded him. The ≈5× sum matches five defenders on
  the floor. The higher ratio in the same five games suggests the field shares
  the scale issue there.
- Overlap O = M ÷ A is in tracked-offense seconds, not box-score minutes. It is
  observable only for defenders with a recorded matchup.
- S, A and O are kept side by side, with M = O × A.

## Phase 2 — overlap, assignment and entry/exit

Each transition's share change is split with a two-factor Shapley average over
defenders measurable in both games. Defenders seen in only one game (or with A
rounded to 0) form an explicit entry/exit part. TVD is attributed by the sign of
each defender's change, so the parts add to the TVD exactly.

- The **overlap effect** ("overlap / rotation") is a change in who shares the
  floor with the offensive player. It can come from substitutions, foul
  trouble, availability or the opponent's rotation; it does not by itself show
  a coaching decision.
- f(O, A) is invariant to scaling O or A within a player-game, so overtime and
  a constant scale error in the percentage fields do not move the split.
- **Coverage** = min share of the two games held by comparable defenders.
  Transitions below 0.80 (fixed before looking at results) are `low_coverage`:
  199 of 681, median coverage 0.93. Their split should not be read precisely.

**Case: Wembanyama, OKC–SAS Game 1 → Game 2** (API snapshot; Game 1 went to
double overtime; coverage 0.979). TVD 0.648 = overlap 0.310 + assignment 0.333
+ entry/exit 0.005.

| Defender | Share G1 → G2 | Change | Overlap | Assignment |
| --- | ---: | ---: | ---: | ---: |
| Isaiah Hartenstein | 1.6% → 58.3% | +56.7 pp | +38.4 | +19.6 |
| Alex Caruso | 36.2% → 6.5% | −29.7 pp | −3.2 | −26.5 |
| Jalen Williams | 17.8% → 2.5% | −15.3 pp | −10.1 | −5.2 |
| Luguentz Dort | 13.2% → 1.3% | −11.9 pp | −2.2 | −9.7 |
| Chet Holmgren | 12.3% → 18.0% | +5.7 pp | −7.0 | +13.1 |

Hartenstein shared far more of Wembanyama's floor time *and* guarded him more
often when both were on (assignment rate roughly 29% → 76%; Game 1 is a
percentage-scale anomaly game, so treat the Game 1 level as approximate). Caruso's drop is almost entirely an
assignment change. The redistribution was about half overlap, half assignment.
Game 1 is one of the five games with the `off_time_percent` scale issue; S and
the split do not use that field.

Development-sample observation, not a league finding: among 66 transitions
flagged on both noise bases with coverage ≥ 0.80, assignment accounts for 56% of
summed TVD, overlap 37%, entry/exit 7%; assignment exceeds overlap in 74%.

## Phase 3 — sampling-noise baseline on two bases

A parametric bootstrap, not a permutation test (the data are per-game
aggregates). Assumptions:

1. A game behaves like n independent draws, n = the offensive player's partial
   possessions, rounded.
2. Draws are independent. Matchups come in stretches, so noise is
   **understated** and significance is optimistic.

The primary statistic is a **time** share, while n counts possessions, and one
possession can be split between defenders after a switch. So the same tests are
also run on **possession** shares (each defender's partial possessions ÷ total),
whose unit matches n:

| | Time basis | Possession basis |
| --- | ---: | ---: |
| Transitions | 681 | 678 |
| League q < 0.10 | 182 | 141 |
| Players with max-adjusted league q < 0.10 | 71 of 183 | 54 of 183 |
| High-noise heuristic (null median ≥ 0.25) | 255 | 261 |

Agreement over 676 matched transitions: TVD correlation 0.94, excess-TVD
correlation 0.85. 122 are flagged on both bases, 60 only on time, 19 only on
possessions, 475 on neither. The possession basis is more conservative; the 122
flagged on both are the robust set.

Wembanyama G1 → G2 holds on both: time TVD 0.648, excess 0.481, league q 0.006;
possession TVD 0.597, excess 0.426, league q 0.006.

Other choices:

- Each player's largest transition is tested against the null of the *largest*
  TVD in a no-change series, correcting for picking the maximum.
- Benjamini–Hochberg q-values within series and pooled league-wide.
- `high_noise` is a display heuristic, not a significance rule; nothing is
  dropped because of it. Tables report observed TVD, null median, null 95th
  percentile, excess TVD and possessions.
- `game_gap` > 1 marks transitions across games the player missed (38).

The earlier informal audit reproduces from this code (both games ≥ 20
possessions, 477 transitions): median TVD 0.267 vs. null 0.192; 37.5% above the
null 95th percentile; correlation between TVD and the smaller game's possessions
−0.36.

The max-adjusted leaderboard is still led by low-volume bench players and
transitions across missed games. Ranking becomes meaningful only once phase 5
restricts it to primary offensive players defined from box scores.

## Open items

- Cause of the five-game percentage scale issue (NBA source side).
- External validity: see `research/FACE_VALIDITY.md`. The overlap component
  matches documented causes; the assignment component is not yet confirmed
  beyond the motivating case.

## Not done yet

- Phase 4: multi-season acquisition (`fetch_playoffs.py`, local machine only).
- Phase 5: primary offensive players, league findings with FDR, performance
  relative to the player's own baseline, README/app/article rewrite.
- The dashboard and its original leaderboard are unchanged.
- Block resampling needs stretch-level data and stays a future sensitivity check.
