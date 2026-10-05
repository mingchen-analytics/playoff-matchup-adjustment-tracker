# V2 player game context — 2026-10-05

This document records the initial two-series milestone. The current seven-series
catalog and new acquisition evidence are in [Series expansion](SERIES_EXPANSION.md).

The second context milestone adds traditional full-game player box scores to
both independent API series. This completes the team-result and player-game
portions of the handoff's game-context stage, not possession or lineup analysis.

## Available data

| Series | Games | Player-game roster rows | Played | Non-participants |
| --- | ---: | ---: | ---: | ---: |
| 2026 OKC–SAS | 7 | 193 | 169 | 24 |
| 2025 OKC–IND | 7 | 203 | 159 | 44 |

Frozen CSVs and separate reports are in `data/player_context/`. The dashboard
loads them without `nba_api` or live requests. It shows minutes, starter status,
points, field-goal attempts, free-throw attempts, turnovers, personal fouls and
plus/minus. The selected adjustment displays the two corresponding box-score
rows. Changing the player or series changes this context automatically.

These are **full-game** statistics, separate from the existing matchup-attributed
PTS/75, eFG% and TOV/75. No historical reference, matchup dataset, source approval
or analytical formula has changed. The manual sample receives no current API
context and remains a separate dataset.

## Source and identity

All 14 games were acquired from NBA `BoxScoreTraditionalV3` on 2026-10-05 using
`nba_api` 1.11.4. [Endpoint documentation](https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/boxscoretraditionalv3.md)
describes the player and team fields. Acquisition metadata records endpoint,
game ID, actual UTC fetch time and raw JSON SHA-256. Raw responses are retained
in the ignored `data/raw/player_boxes/` cache; they are not needed by the app.

Player `personId` and team code join to the offensive/defensive player IDs in
the existing matchup snapshots. Display-name spelling does not control the join.
Every matchup identity is checked against that game's box-score roster.

The source populates `position` for the five starters; this determines the
displayed starter flag and is checked against five starters per team. Blank
minutes plus a source comment identify non-participants. Their comments are
retained, while their statistical fields and starter status remain missing.
They are not displayed as zero-point performances. A player missing entirely
from a game's source roster is labeled **Not listed in box score**, not DNP.

## Validation and provenance

- Exact manifest games, dates, teams and player IDs; no duplicated identities.
- Finite, integer counts with valid shooting relationships and scoring equation.
- Player points reconcile to the independently verified team game score.
- Summed player plus/minus reconciles to five times the team's final margin.
- Game duration comes from team playing time: 48 minutes plus five-minute OTs.
  Individual minutes cannot exceed duration; summed player time must reconcile
  to five players on court, allowing at most one second per participant for rounding.
- Explicit played/starter states and source comments; no nonzero DNP statistics.
- Dataset, manifest, team-game-log and matchup-source hashes, plus per-game
  coverage, row counts and timestamped raw acquisition evidence.
- LF/CRLF conversion remains compatible; other content changes fail integrity.

Publication is cache-first and bounded. A missing or invalid game never produces
a partial published series; the failure report is written under ignored
`data/processed/`. Acquisition evidence must match its raw cache. Previously
published player context cannot be overwritten by the CLI.

Missing optional context leaves the matchup dashboard usable. Invalid context
is hidden with a warning and never populates the player or transition table.

## Reproduce

For a series with a published matchup snapshot and verified team game context:

```bash
pip install -r requirements-data.txt
python -m scripts.fetch_player_context \
  --manifest series/YOUR_NEW_SERIES.yml \
  --timeout 20 --retries 2 --request-interval 2
```

Use `--offline` to require existing raw caches and make no NBA requests. Use a
new versioned series ID when publishing another snapshot version. The bundled
series are already published, so attempting to republish them is rejected.

## Evidence and limitations

The complete suite has **117 passing tests**, including real frozen sources,
the original raw Game 1 fixture, DNP and absent-roster semantics, ID-based joins,
invalid statistics/minutes, corrupted evidence, raw-cache reuse, bounded retry,
publication immutability, failed-ingestion reporting and actual dashboard
player/transition interactions. Normal CI is independent of live NBA services.

For example, the full-game API box score records Wembanyama at 41 points and
48:42 in Game 1; those are full-game numbers and are not replacements for his
defender-attributed matchup outcome metrics. The manual largest Adjustment
Score remains 0.620 for Game 1 → Game 2.

Personal-foul totals cannot locate foul trouble within the game. Minutes do not
describe substitution timing. Plus/minus describes the team's scoring margin
while a player was on court, not the player's causal impact. To inspect timing,
the next data layer is now available as separately validated
[substitution/foul timelines](V2_EVENT_TIMELINE.md). No coaching intent is asserted
from these descriptive observations.
