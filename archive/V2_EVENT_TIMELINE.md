# V2 substitution and foul timelines — 2026-10-05

This document records the initial two-series milestone. The current seven-series
catalog and new acquisition evidence are in [Series expansion](SERIES_EXPANSION.md).

The third context milestone adds observed event timing to the two independent
API series. It does not reconstruct five-player lineups or identify when an
on-ball defender assignment changed within a game.

## Published observations

| Series | Games | Full cached source actions | Published substitutions/fouls |
| --- | ---: | ---: | ---: |
| 2026 OKC–SAS | 7 | 3,832 | 842 |
| 2025 OKC–IND | 7 | 3,744 | 826 |

All 14 games were acquired from NBA `PlayByPlayV3` on 2026-10-05 with `nba_api`
1.11.4. [Endpoint documentation](https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/playbyplayv3.md)
lists the event IDs, clocks, periods, player IDs, types and descriptions.

Full raw JSON and acquisition metadata remain in ignored
`data/raw/play_by_play/`. The published `data/event_context/<series_id>/` folder
contains one CSV per game plus a series provenance report. Only substitutions
and fouls are published for this milestone. Full source period boundaries and
final scores are validated during acquisition and summarized in the report.

## Dashboard

In **Game Transition Comparison**, open **Substitutions and Fouls**. Choose
either game in the selected transition, both teams or a specific team, and
substitutions/fouls. The chart shows elapsed game minutes with period boundaries;
the table shows quarter/OT, remaining clock, team, event subtype, recorded player,
unchanged source description and zero-based source row. An empty filter selection
shows a clear message rather than an error.

Larger markers highlight the selected player's recorded ID. They do not capture
every substitution involving that player: the V3 substitution record identifies
the recorded outgoing player in the bundled data, while the incoming player is
provided in the description. For example, `SUB: Caruso FOR Hartenstein` records
Hartenstein's ID. Incoming IDs are not guessed from abbreviated names. The
complete team event table retains the original descriptions for manual inspection.

Three source events name a coach technical foul but have no team code. These
remain **Unassigned**, preserve the source person ID and description, and appear
under **Both teams**. They are not assigned to a team by guessing from the name.
Foul subtypes are retained; counting all foul events is not a personal-foul count.

## Time and ordering

The first four periods last 12 minutes; overtime periods last five. Clock
validation preserves fractional seconds and rejects values outside their period.
Expected period coverage comes from the separately verified box-score game
duration. The first 2026 OKC–SAS game includes two overtimes, ending at 58 elapsed
game minutes, and exercises this path in real-data tests.

The source contains repeated action numbers and non-monotonic action-number
ordering. Records are not merged by action number. Published events retain
their action ID and source array index, then sort by elapsed time and source
order so events at the same clock retain their relative source ordering.
Duplicate published source rows or action IDs are rejected.

## Validation and reproducibility

Ingestion checks the Game ID, exact manifest dates/numbers, expected periods,
complete ordered period start/end markers, valid clocks, final home/away scores
against verified game results, player IDs against that game's roster, original
descriptions, and per-game event counts. Non-player technical fouls retain their
unresolved identity. The loader repeats row/identity/clock validation and checks
the snapshot, manifest, team-result, player-source and timestamped acquisition
evidence. LF/CRLF conversion is accepted; other modifications fail integrity.

The command is bounded and cache-first:

```bash
pip install -r requirements-data.txt
python -m scripts.fetch_event_context \
  --manifest series/YOUR_NEW_SERIES.yml \
  --timeout 20 --retries 2 --request-interval 2
```

Publish verified matchup, team and player snapshots first. `--offline` requires
existing raw caches and makes no requests. An existing event publication cannot
be overwritten; use a new versioned series ID. Validated files and their report
are staged together, then the complete directory is atomically renamed into
place. Failed acquisition/validation writes a diagnostic under ignored
`data/processed/` and never publishes a partial series. The app requires no NBA
ingestion dependency or network access.

## Tests and limits

The complete suite has **155 passing tests**, including 38 new event checks for
real frozen series, OT/fractional clocks, a curated real Game 1 event excerpt,
source descriptions/IDs, repeated action numbers, invalid coverage/scores,
changed provenance, CRLF compatibility, bounded retry, cache reuse, publication
immutability, atomic failure handling, chart coordinates and actual dashboard
game/team/type filtering. Normal CI makes no live NBA requests.

The original matchup formulas, manual reference, API source approval, matchup
snapshots, team context and player box scores remain unchanged. Wembanyama's
manual maximum Adjustment Score remains 0.620 for Game 1 → Game 2.

These are event observations, not proof of coaching intent or matchup-adjustment
causality. Reliable lineup reconstruction needs both substitution player IDs,
period-opening players and consistency checks against player minutes. Resolving
those inputs is the next checkpoint before any five-player lineup claim.

The next context milestone and the completed source-feasibility checkpoint are
recorded in [Defensive personnel context](V2_DEFENSIVE_PERSONNEL.md). Five-player
lineup reconstruction remains gated on the missing identity/opening evidence.
