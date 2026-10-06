# Series expansion — 2026-10-05

Five complete 2026 playoff series are added to the existing two API snapshots.
The catalog now covers seven complete series, two seasons and four playoff stages.
Each API series has matchup, verified team results, player boxes and substitution/
foul timelines available offline. The original manual sample remains separate
and is still the startup default.

## Published catalog

| Season | Series | Round | Games | Matchup rows | Player roster rows | Events | Addition |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 2024-25 | OKC–IND | NBA Finals | 7 | 1,388 | 203 | 826 | Existing |
| 2025-26 | CLE–NYK | Eastern Conference Finals | 4 | 721 | 119 | 380 | New |
| 2025-26 | DEN–MIN | First Round | 6 | 1,009 | 164 | 597 | New |
| 2025-26 | LAL–OKC | Western Conference Semifinals | 4 | 794 | 107 | 430 | New |
| 2025-26 | MIN–SAS | Western Conference Semifinals | 6 | 1,135 | 172 | 623 | New |
| 2025-26 | NYK–SAS | NBA Finals | 5 | 872 | 150 | 557 | New |
| 2025-26 | OKC–SAS | Western Conference Finals | 7 | 1,513 | 193 | 842 | Existing |
| Total | | | 39 | 7,432 | 1,108 | 4,255 | |

The 4,255 published event observations were selected from 20,328
raw play-by-play actions; only substitutions and fouls are published.
Player roster rows include non-participants, whose statistics remain blank.
The new batch covers 25 games, 4,531 matchup rows, 712 player roster rows and
2,587 event observations. It does not claim to cover every 2026 series.

## Acquisition and validation

- NBA LeagueGameFinder season 2025-26, Playoffs, league 00 identified the actual
  opponents, dates and games; five selected complete series reached four wins.
  The per-series discovery excerpts retain both teams' original source rows.
- BoxScoreMatchupsV3, BoxScoreTraditionalV3 and PlayByPlayV3 were fetched through
  `nba_api` 1.11.4 with bounded retries, cache-first reuse and spaced requests.
- Every configured game has validated coverage. Player/team identities, scoring,
  full-game duration, five-player time totals, plus/minus, period boundaries and
  final play-by-play scores reconcile through the existing validators.
- Published reports retain manifest/data/dependency hashes, raw SHA-256 hashes,
  endpoint and actual UTC acquisition times. Offline reprocessing preserves
  acquisition evidence and the exact player dataset bytes.
- The approved separate-snapshot policy is unchanged. Historical API/manual
  numerical parity remains **failed**; no reference, formula, adapter or tolerance
  is changed, and no snapshot is described as manual-parity verified.

Frozen assets use dated series IDs in `series/`, `data/snapshots/`, `data/context/`,
`data/player_context/` and `data/event_context/`. Raw endpoint caches remain local
under ignored `data/raw/`; the dashboard and CI do not need them or live NBA access.

## Source minutes format

NBA Traditional V3 game `0042500404` records Jeremy Sochan (`1631110`, NYK)
with minutes `2:60`. The parser accepts an exact seconds component of `60` and
carries it into elapsed time: 180 seconds. Raw acquisition data is unchanged.
The cause of this source formatting is unknown. Seconds above 60 or a fractional
60 (e.g. `2:60.1`) remain invalid. The existing game-duration and team-total
checks are unchanged and pass after conversion. The player is a participant,
not a DNP. New player reports record the final parser's source hash; existing
published datasets and reports remain unchanged.

## Dashboard and regression checks

Season → Round → Series now spans first round, conference semifinals,
conference finals and NBA Finals. Two new series share Western Conference
Semifinals, exercising selection within a round. The default round follows the
first catalog entry for that season, preserving the manual startup reference
when more round names are present.

`tests/test_series_expansion.py` loads all five new context chains offline,
checks Windows LF/CRLF conversion, validates timestamped complete acquisition,
and exercises all new series and rounds plus switching between seasons. It also
covers the real `2:60` participant and rejects invalid minutes. Existing tests
continue to preserve Wembanyama's manual largest adjustment of **0.620**.

Validation result: **175 tests passed** locally in 80.12 seconds on Python 3.12.
Ruff checks for changed Python files and `git diff --check` also passed.

Run validation with:

```bash
python -m pytest -q
```

After updating the local NBA repository, restart Streamlit and choose a season,
round and series in the sidebar. No new runtime dependencies are required.
