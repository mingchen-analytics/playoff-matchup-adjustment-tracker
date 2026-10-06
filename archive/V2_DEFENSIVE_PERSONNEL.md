# V2 defensive personnel context — 2026-10-05

A large recorded matchup-share change needs surrounding personnel context.
The dashboard now compares the defending team's full roster in the two selected
games: participation, starting status, full-game minutes and personal fouls,
alongside its recorded matchup time/share against the selected offensive player.
All seven API series support this comparison using the existing frozen assets.

## Dashboard

In **Game Transition Comparison**, open **Defensive Personnel Comparison**.
Changing the offensive player selects the opposing roster; changing the
transition changes both game columns. The chart presents separate horizontal
axes for matchup-share change (percentage points) and full-game minute change.
It shows up to ten defenders ordered by absolute share change. The table contains
the union of the full defending rosters, including non-participants.

Matchup-share denominators remain the sum of all recorded defender seconds
against the selected offensive player in that game. Full-game minutes come
from the independently verified traditional box score. These are different
measurements, and the panel does not replace the existing adjustment score,
matchup-attributed offensive outcomes or full-game player box table.

Game durations are displayed with the comparison because an overtime game and
a regulation game offer different playing-time opportunities. Full-game minutes
can change with both rotation and game length. Personal fouls are full-game
counts, not a timed foul-trouble label or evidence of why a substitution occurred.

## Identity and missing-data rules

- Join on game ID, opposing team and NBA player ID. Display the latest roster
  name for that player in the selected pair; no abbreviated-name matching.
- NBA endpoints differ in accents/suffixes: the matchup source has
  `Jonas Valanciunas` and `Terrence Shannon Jr`, while the box score has
  `Jonas Valančiūnas` and `Terrence Shannon Jr.`. These are joined by their IDs,
  `202685` and `1630545`, without changing either published source.
- Source DNP/inactive comments remain visible. Their starter, minutes and
  personal-foul fields remain missing. An absent roster entry is **Not listed
  in box score**, not a guessed DNP or injury.
- Minute change is unavailable when either game lacks a played box-score row.
- Zero recorded matchup time means no recorded allocation against that player.
  It does not convert missing box minutes into a zero-point performance.
- If a game has no positive recorded exposure for the selected offensive player,
  its share and share change remain missing; no zero denominator is filled.
- Unknown/duplicate defensive IDs, wrong opponents or game IDs, nonfinite/negative
  matchup seconds and positive exposure for a non-participant are rejected.

The manual sample has no API personnel join and displays a clear unavailable
message. API data keeps its existing independent-snapshot warning and failed
historical manual-parity status. Published datasets, reports, source policy,
benchmark, analytical definitions and numerical tolerances are unchanged.

## Reproducible example

For **2026 OKC–SAS independent API snapshot**, Wembanyama Game 1 → Game 2:

| Defender | Recorded share change | Full-game minutes before | After |
| --- | ---: | ---: | ---: |
| Isaiah Hartenstein | +56.7 pp | 12.17 | 27.33 |
| Alex Caruso | −29.7 pp | 31.67 | 25.45 |
| Jalen Williams | −15.3 pp | 37.27 | 7.30 |

Game 1 lasted 58 minutes (two overtimes), while Game 2 lasted 48. Hartenstein's
starting flag is true in both games. These observations supply descriptive
context; they do not establish coaching intent or a causal defensive effect.
This example uses the API snapshot and is separate from the unchanged manual
case study's 0.620 Adjustment Score.

## Five-player lineup source checkpoint

The 39 cached NBA PlayByPlayV3 games contain 2,480 substitution records. The
[endpoint's documented fields](https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/playbyplayv3.md)
include one `personId` and an original description. They do not expose both
substitution player IDs. Existing published observations identify the recorded
outgoing player; incoming IDs have not been reconstructed from name strings.

Bounded feasibility probes on 2026-10-05 using `nba_api` 1.11.4:

| Source/query | Observed result | Adoption |
| --- | --- | --- |
| NBA Live PlayByPlay, `0042500311`, timeout 15s | JSON decoding failed; no usable response was acquired | No production dependency |
| NBA Stats PlayByPlayV2, same game, timeout 10s | Library warned this endpoint is deprecated; request/parser failed with missing `resultSet` | No production dependency |
| TraditionalV3, same game, RangeType=2, StartRange=7200, EndRange=7210, StartPeriod=2, EndPeriod=2, timeout 15s | Partial box returned five positive-minute players per team; team minutes were `0:14`, player values `0:03` | Feasibility observation only; exact time-window semantics and all-period opening coverage were not validated |

The [maintainer's V2 implementation](https://github.com/swar/nba_api/blob/master/src/nba_api/stats/endpoints/playbyplayv2.py)
also advertises the deprecation. Failure observations above are limited to these
queries, not a claim that every NBA data route is permanently unavailable.
No probe response is used by the comparison panel or described as validated
lineup data.

Five-player reconstruction remains gated on verified IDs for both substitution
participants, opening players for every regulation/OT period, source-order rules
for simultaneous substitutions, and reconstructed minutes that reconcile to
verified player boxes. The comparison panel reports roster/starter observations;
it does not identify the five players simultaneously on court or help-defender
positioning. This preserves the handoff's next lineup checkpoint without
inventing the missing inputs.

## Validation

`tests/test_defensive_personnel.py` covers all seven series in both offensive
team directions across adjacent transitions, total recorded exposure, 100% share
sums where available, NBA-ID joins with real spelling differences, DNP/absent
roster states, missing exposure, conflicting identities, chronological controls,
chart units/missing minutes and actual Streamlit player/transition switching.
The new ID-level shares also reconcile to the existing transition-allocation
engine in the Wembanyama API case. Normal tests block live HTTP.

Validation: **207 tests passed** locally in 92.78 seconds (32 new personnel
checks). A separate offline audit successfully built **681 player-transition
comparisons** across all seven series. Changed Python Ruff checks and
`git diff --check` passed. Existing frozen data and analytics files have no diff.

Run:

```bash
python -m pytest -q
```

No new runtime dependencies or NBA downloads are needed. After pulling updates,
restart the existing local Streamlit app and open the comparison expander.
