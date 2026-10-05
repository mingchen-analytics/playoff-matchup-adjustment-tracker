# First V2 milestone: offline game context

V1 is merged and the owner confirmed the local dashboard runs correctly. The
handoff's next stage is game context, beginning with team results rather than
play-by-play or a new analytical definition.

## What is available

Both published seven-game API series now include an optional game-context table:

- Game date, home/away, score, win/loss and point differential.
- Series record before and after each game, from the selected player's team.
- The two relevant game results alongside the selected matchup adjustment.

The historical manual sample has no attached context; the dashboard explicitly
shows that verified context is unavailable for that dataset. It does not silently
attach a current API record to the manual sample.

## Data and integrity

The original NBA LeagueGameFinder discovery logs are published unchanged in
`data/context/`. Each file must match the `discovery_sha256` already recorded in
its corresponding V1 snapshot report. These are existing verified caches, not
new live requests. The original matchup datasets, reports, source approval,
manual reference and metric formulas are unchanged.

The endpoint's documented columns include `PTS`, `PLUS_MINUS`, `WL`, `MATCHUP`,
`GAME_ID` and `GAME_DATE`: [nba_api LeagueGameFinder documentation](https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/leaguegamefinder.md).

The opponent score is derived as team points minus the **team** point differential.
This derivation is disclosed in the dashboard. Matchup-level points are never
summed to construct a game score. Home/away comes from the log's `vs.` / `@`
matchup. Score and series records reverse consistently for the other team.

Validation requires exact manifest game IDs and dates, playoff season, teams,
series completeness, finite integer nonnegative scores, a nonzero margin,
consistent W/L, and no conflicting duplicate rows. Series progression uses
chronological game results; the existing discovery check rejects games after
either team has won four. Windows CRLF conversion is allowed while actual
content modifications fail the hash check.

Missing context leaves the matchup dashboard usable. Invalid context shows a
warning and is hidden; it is never used to populate scores or transition tables.

## Reproduce publication

With an existing discovery cache and its completed V1 snapshot/report:

```bash
python -m scripts.publish_game_context \
  --manifest series/2026_okc_sas_api_20261005.yml \
  --game-log-csv data/discovery/2026_okc_sas_api_20261005.csv
```

The command makes no network calls, validates the evidence before writing,
and refuses to replace an existing published context with different content.
For another series, publish its V1 matchup snapshot/report first, then run the
same command with that series's manifest and discovery cache. The app requires
no series-specific changes.

## Validation

All **82 tests pass**, including the existing V1 and Windows regressions plus
14 game-context checks. Normal tests remain independent of live NBA requests.

The suite includes actual dashboard interactions for both team perspectives,
selected-transition alignment, missing context, CRLF compatibility, modified
source rejection, inconsistent scores/results, coverage/date mismatch, duplicate
conflicts, and CLI evidence checks before writing. The original manual
Wembanyama result remains 0.620 for Game 1 → Game 2.

## Next scope

This completes the team-result portion of game context, not all of V2.
The next milestone is separately cached and validated **player game box scores**:
minutes, starter status, points, FGA, FTA, turnovers, personal fouls and plus/minus.
Do not infer these from defender matchup rows. Only after that layer is stable
should play-by-play or lineup reconstruction be considered.

Game results provide descriptive context. They do not establish coaching intent
or that a matchup adjustment caused a win or changed an offensive outcome.
