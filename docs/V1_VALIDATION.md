# V1 implementation and validation — 2026-10-05

## Status

**Reusable software implemented; full V1.0 acceptance blocked by unresolved source parity.** No merge or deployment has been performed. The original CSV and analytical formulas are unchanged.

## Completed engineering

- Strict YAML manifests with string NBA Game IDs, chronological dates, explicit sample/series completeness, and configurable defaults.
- NBA LeagueGameFinder discovery, with season/opponent/playoff filtering, exact-duplicate removal, chronological ordering, series/gap validation, and best-of-seven completion checks.
- Resumable raw-cache-first ingestion, bounded retries, request spacing, normalized caches, per-game and combined validation, and atomic processed/report writes.
- Versioned standardized schema with IDs, dates, source provenance, display-scale percentages, and unchanged legacy analytics compatibility.
- Local series catalog and Season → Round → Series → Player controls, including missing-data, sample/ongoing, and unverified-cache states.
- API/manual parity reports that fail on missing values, empty data, duplicate identities, unmatched rows, or differences outside the existing tolerances.
- Live series acquisition requires a passing report for the current adapter and original manual benchmark; offline exploration stays explicitly unverified.
- Deterministic normal CI, cache/coverage/hash validation, CLI tests, and actual Streamlit switching tests.

## Baseline and regression checks

The baseline was 14 passing tests before changes; the expanded suite now has **53 passing tests**. The expanded suite additionally exercises configuration, discovery, schema, cache reuse, partial failures, verification gates, and dashboard interactions. All tests run without live HTTP; synthetic data exists only in temporary test roots.

The original dashboard still renders without exceptions and keeps Wembanyama as the default for the manual sample. His maximum Adjustment Score remains **0.620**, Game 1 → Game 2. The manual data still contains **1,074 rows, 29 offensive players, and five recorded games**. No empirical thresholds or causal claims were added.

## Real source finding 1: offensive/defensive team mapping

A live `nba_api` 1.11.4 `BoxScoreMatchupsV3` request for `0042500311` succeeded in this environment. It returned 176 PlayerStats rows.

The old adapter interpreted `teamTricode` as the defensive team. The response and manual reference establish that it represents the **offensive** team. For example, its first row is Jalen Williams (OKC offense) versus Harrison Barnes (SAS defense), with `teamTricode=OKC`. This direction was fixed, and non-breaking spaces in manual names were normalized for comparison.

After this fix, **all 176 matchup identities align one-to-one** with the original manual Game 1. No rows are exclusive to either source.

## Real source finding 2: values still differ

Recorded evidence: [api_manual_game1_comparison.json](api_manual_game1_comparison.json). It includes benchmark/adapter hashes, timestamp, matched counts, tolerances, and individual mismatches. Its status is **fail**.

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

The original dataset covers Games 1–5 only. It is now configured as `2026_okc_sas_sample`, with `series_complete: false`. Its existing numerical findings remain intact. A separately discovered seven-game manifest, `2025_26_okc_sas`, is checked in as a **pending configuration**; it does not claim a completed matchup dataset.

## Acceptance checkpoint

| Criterion | Evidence / status |
| --- | --- |
| Identify a playoff series | Manifest and team/season CLI paths implemented |
| Obtain/discover Game IDs | Live seven-game discovery succeeded; offline filtering tests pass |
| Acquire or load matchup data | Live single-game fetch succeeded; raw-cache/offline and bounded-fetch paths tested |
| Normalize each game | Adapter direction fixed; canonical round-trip tests pass |
| Automatically validate | Per-game, full coverage, numeric, identity, metadata, hash, and source checks implemented |
| Combine standardized dataset | Manual five-game build passed; synthetic cached API series build passed |
| Load multiple series in app | Actual switching verified with temporary synthetic second series |
| Preserve analytical engine | Existing functions/formulas unchanged; 0.620 result preserved |
| Passing tests | Expanded suite passes locally; remote PR CI reported separately |
| Network-independent normal CI | No nba_api dependency required for ordinary tests; live HTTP blocked by fixture |
| Document full pipeline | README and this validation record |
| Understandable failures | Missing-game/stale-file/unverified-source tests and visible app errors |
| Resolve source parity / real-series acceptance | **Blocked**; complete live multi-game ingestion and a second real series have not been approved or demonstrated |

## Concrete decision needed

Before proceeding to production API series acquisition, Ming must choose the source policy for the documented discrepancies:

1. **Recommended:** Keep the manual five-game historical case study and introduce current API snapshots as separate, timestamped datasets, clearly documenting that they are not identical. This requires explicitly approving a revised source gate based on schema/identity validation and acknowledged snapshot differences rather than exact historical parity.
2. Keep exact API/manual parity as mandatory; obtain the original NBA.com snapshot or further evidence and resolve the discrepancies before continuing live series ingestion.

No automatic source-policy bypass was added. Both the original case study and pending seven-game configuration are available for review, and the next code change can be scoped to the approved policy. Full V1.0 should only be declared after that policy is implemented, a real full-series ingestion passes, and real multi-series behavior is demonstrated.

This stop follows the project handoff's Phase 1 decision gate (“Do not proceed to full automation until the source relationship is understood”) and its rule to ask when public results would need rewriting or a new source decision is required. Routine engineering continued to a reviewable PR before raising this decision.
