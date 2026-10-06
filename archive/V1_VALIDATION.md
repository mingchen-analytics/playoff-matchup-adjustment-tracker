# V1 implementation and validation — 2026-10-05

## Status

**V1.0 implementation and validation complete under the owner-approved independent-snapshot policy.** Two full real seven-game series are published and exercised in the dashboard. V1 and the Windows checkout fix are merged; the owner confirmed the local dashboard works. Hosted Streamlit deployment has not been confirmed updated. The original CSV and analytical formulas are unchanged. Historical numerical parity still fails; this is explicitly recorded rather than relabeled as passing.

## Completed engineering

- Strict YAML manifests with string NBA Game IDs, chronological dates, explicit sample/series completeness, and configurable defaults.
- NBA LeagueGameFinder discovery, with season/opponent/playoff filtering, exact-duplicate removal, chronological ordering, series/gap validation, and best-of-seven completion checks.
- Resumable raw-cache-first ingestion, bounded retries, request spacing, normalized caches, per-game and combined validation, and atomic processed/report writes.
- Versioned standardized schema with IDs, dates, source provenance, display-scale percentages, and unchanged legacy analytics compatibility.
- Local series catalog and Season → Round → Series → Player controls, including missing-data, sample/ongoing, and unverified-cache states.
- API/manual parity reports that fail on missing values, empty data, duplicate identities, unmatched rows, or differences outside the existing tolerances.
- Strict parity remains the default acquisition gate. The explicitly selected independent-snapshot policy requires the owner's approval record, unchanged adapter/benchmark hashes, and the recorded complete identity comparison. Offline exploration without that policy stays unverified.
- Frozen dated snapshots, per-game acquisition metadata, raw/dataset/manifest/discovery hashes, source-policy hash, and visible failed-parity warnings. Snapshot ingestion refuses to overwrite a published dataset.
- Deterministic normal CI, cache/coverage/hash validation, CLI tests, and actual Streamlit switching tests.

## Baseline and regression checks

The baseline was 14 passing tests before changes; the expanded suite now has **66 passing tests**. It additionally exercises configuration, discovery, schema, cache reuse, partial failures, verification gates, approved-policy rejection on changed evidence, snapshot immutability, acquisition timestamps/cache metadata, real frozen data, tampered dataset/manifest rejection, and actual dashboard interactions. All tests run without live HTTP; synthetic data exists only in temporary test roots.

The original dashboard still renders without exceptions and keeps Wembanyama as the default for the manual sample. His maximum Adjustment Score remains **0.620**, Game 1 → Game 2. The manual data still contains **1,074 rows, 29 offensive players, and five recorded games**. No empirical thresholds or causal claims were added.

## Real source finding 1: offensive/defensive team mapping

A live `nba_api` 1.11.4 `BoxScoreMatchupsV3` request for `0042500311` succeeded in this environment. It returned 176 PlayerStats rows.

The old adapter interpreted `teamTricode` as the defensive team. The response and manual reference establish that it represents the **offensive** team. For example, its first row is Jalen Williams (OKC offense) versus Harrison Barnes (SAS defense), with `teamTricode=OKC`. This direction was fixed, and non-breaking spaces in manual names were normalized for comparison.

After this fix, **all 176 matchup identities align one-to-one** with the original manual Game 1. No rows are exclusive to either source.

## Real source finding 2: values still differ

Recorded evidence: [api_manual_game1_comparison.json](../docs/api_manual_game1_comparison.json). It includes benchmark/adapter hashes, timestamp, matched counts, tolerances, and individual mismatches. Its status is **fail**.

| Field | Rows beyond existing tolerance | Maximum absolute difference |
| --- | ---: | ---: |
| Matchup time | 9 | 3 seconds |
| Player points | 2 | 2 points |
| Team points | 3 | 2 points |
| FGM | 2 | 1 |
| FGA | 4 | 1 |
| Shooting fouls | 1 | 1 |
| Partial possessions | 2 | 0.6 |
| Defender time percent | 8 | 0.3 percentage points |
| Offensive time percent | 7 | 0.2 percentage points |
| Both-on time percent | 9 | 0.3 percentage points |
| FG percent | 4 | 50 percentage points |

Assists, turnovers, blocks, three-point makes/attempts/percentages, and free throws match within their configured tolerances.

Concrete example: Wembanyama versus Caruso changes from 8:18 to 8:21; player points from 9 to 7; and field goals from 4/5 to 3/4. These count differences cannot be explained by display rounding. A separate traditional-box-score request was inspected, but overall player totals cannot establish how the tracking provider attributed each defender matchup. The reason for the discrepancy remains **unconfirmed**. It may reflect historical snapshot differences or collection differences; neither explanation is asserted as fact.

Do not expand tolerances or modify the reference CSV to make this check appear to pass.

## Real source finding 3: five-game sample versus seven-game series

A live NBA LeagueGameFinder query for OKC versus SAS, 2025-26 Playoffs, returned seven played games:

| Game | Game ID | Date | OKC result |
| --- | --- | --- | --- |
| 1 | `0042500311` | 2026-05-18 | L |
| 2 | `0042500312` | 2026-05-20 | W |
| 3 | `0042500313` | 2026-05-22 | W |
| 4 | `0042500314` | 2026-05-24 | L |
| 5 | `0042500315` | 2026-05-26 | W |
| 6 | `0042500316` | 2026-05-28 | L |
| 7 | `0042500317` | 2026-05-30 | L |

The original dataset covers Games 1–5 only. It is configured as `2026_okc_sas_sample`, with `series_complete: false`; its findings remain intact. The former pending seven-game configuration was replaced by `2026_okc_sas_api_20261005`, with a full validated API dataset and provenance report.

## Real published snapshots

Both series were discovered from NBA LeagueGameFinder and acquired from BoxScoreMatchupsV3. All configured games passed individual and combined schema/identity/numeric/coverage checks. Published CSVs and reports are in `data/snapshots/`, enabling offline dashboard use without ingestion dependencies.

| Snapshot | Games | Matchup rows | Per-game row counts |
| --- | ---: | ---: | --- |
| 2026 OKC–SAS Western Conference Finals | 7 | 1,513 | 176, 204, 236, 249, 222, 263, 163 |
| 2025 OKC–IND NBA Finals | 7 | 1,388 | 189, 233, 175, 168, 182, 258, 183 |

The 2025 series has IDs `0042400401` through `0042400407`; the 2026 series has IDs `0042500311` through `0042500317`. Reports include UTC run/acquisition times and source hashes. The pre-existing Game 1 OKC–SAS cache has no known original acquisition timestamp; its provenance explicitly records null and an imported-cache explanation. No acquisition time is fabricated.

AppTest exercises manual → real OKC–SAS → different-season real OKC–IND switching, with no exceptions/errors, valid player controls, calculated metrics, and visible source warnings. Published snapshots are immutable through the ingestion command; future versions require a new series ID. Disposable raw caches are reusable unless the operator intentionally uses a fresh cache directory.

## Acceptance checkpoint

| Criterion | Evidence / status |
| --- | --- |
| Identify a playoff series | Manifest and team/season CLI paths implemented |
| Obtain/discover Game IDs | Live seven-game discovery succeeded; offline filtering tests pass |
| Acquire or load matchup data | Both real seven-game series acquired; raw-cache/offline and bounded-fetch paths tested |
| Normalize each game | Adapter direction fixed; canonical round-trip tests pass |
| Automatically validate | Per-game, full coverage, numeric, identity, metadata, hash, and source checks implemented |
| Combine standardized dataset | Manual sample plus both complete real API series passed |
| Load multiple series in app | Actual real-series and cross-season switching verified, plus synthetic one-game edge case |
| Preserve analytical engine | Existing functions/formulas unchanged; 0.620 result preserved |
| Passing tests | Expanded suite passes locally; remote PR CI reported separately |
| Network-independent normal CI | No nba_api dependency required for ordinary tests; live HTTP blocked by fixture |
| Document full pipeline | README and this validation record |
| Understandable failures | Missing-game/stale-file/unverified-source tests and visible app errors |
| Source policy / real-series acceptance | Owner approved independent snapshots; two complete real series validated. Historical parity remains failed and visible |

## Approved source decision

On 2026-10-05 Ming explicitly approved the recommended policy: preserve the historical manual sample and create separate timestamped current API snapshots. The approval is recorded in [source_policy.json](../docs/source_policy.json), bound to the unchanged comparison report hash. Numerical discrepancies are acknowledged; their cause remains unconfirmed.

`--source-policy separate_snapshot` is explicit, not an automatic fallback after strict verification fails. It rejects changed comparison, adapter, benchmark, or approval evidence. The normal strict gate is retained and still rejects live ingestion on the failed numerical comparison. No tolerances or comparison outcomes were altered.

The revised policy, full-series acquisition, second real series, and real multi-series dashboard tests have now been completed and merged in PR #1. PR #2 fixed LF/CRLF snapshot validation on Windows, with 68 passing tests. The owner confirmed the local dashboard works after updating. Hosted deployment remains a separate unresolved step.

The earlier pause followed the handoff's Phase 1 source-decision gate. Work resumed only after the explicit owner approval. The first post-V1 milestone is documented in [V2_GAME_CONTEXT.md](V2_GAME_CONTEXT.md); ML, play-by-play, lineups, video, scouting PDFs and major UI redesign remain deferred.
