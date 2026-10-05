# Playoff Matchup Adjustment Tracker

[Open the live Streamlit dashboard](https://playoff-matchup-adjustment-tracker-zdee28tjezgw42ujydet6v.streamlit.app/)

> **Rebuild in progress (`rebuild` branch).** The project is moving from a dashboard to measurement research: separating rotation, assignment choice and sampling noise in matchup changes. Phases 1–3 (measure audit, decomposition, noise baselines) are in [research/FINDINGS.md](research/FINDINGS.md). The V1 dashboard is preserved at tag `v1-archive`; development logs moved to `archive/`.

A reusable basketball analytics system for tracking how defensive assignments change **game by game** during a playoff series.

**Current status:** V1.0 implementation and validation are complete under the owner-approved independent API snapshot policy. Seven complete real API series are bundled across two seasons and four playoff stages, covering 39 games. See the [series catalog and expansion validation](archive/SERIES_EXPANSION.md). The original five-game manual sample remains the default; its values and formulas are unchanged. API/manual numerical parity remains **failed**, not silently waived or relabeled as passing. See [validation findings](archive/V1_VALIDATION.md).

**First V2 milestone:** Verified offline game context is available for all seven API series: scores, result, home/away, point differential, and series records before/after each game. The table follows the selected player's team and the selected adjustment transition. See [game-context design and validation](archive/V2_GAME_CONTEXT.md).

**Player game context:** All seven API series also include full-game player box scores:
minutes, starter status, points, FGA, FTA, turnovers, personal fouls and plus/minus.
Player IDs join these records to matchup identities. DNP/inactive entries retain
their source comments and blank statistics. See [player-context validation and CLI](archive/V2_PLAYER_CONTEXT.md).

**Event timelines:** All seven API series include verified substitution/foul observations
with regulation and overtime clocks. In Game Transition Comparison, open
**Substitutions and Fouls** to inspect either game, filter teams/event types, and
compare the chart with the original event descriptions. See [event timeline design](archive/V2_EVENT_TIMELINE.md).

**Defensive personnel context:** In Game Transition Comparison, open
**Defensive Personnel Comparison** to compare the opponent's full roster across
the selected games: starting status, participation, full-game minutes/personal
fouls and recorded matchup time/share. All seven API series use their existing
offline assets. Separate chart axes and game-duration labels preserve the
interpretation of percentage points versus minutes. See [validation and the
five-player lineup source checkpoint](archive/V2_DEFENSIVE_PERSONNEL.md).

## Why I Built This

Series-level matchup totals are useful, but they can hide the timing of tactical adjustments.

This project adds a game-by-game timeline layer so an analyst can quickly answer questions such as:

- Who was the primary defender on a specific offensive player?
- Did that assignment change during the series?
- Which defenders shared the responsibility?
- How much matchup time did each defender receive?

The concept was inspired by Databallr's playoff matchup pages and focuses on making matchup changes easier to see across games.

## Case Study

The bundled case study uses a five-game **Oklahoma City vs. San Antonio** sample (Games 1–5). NBA game discovery identifies seven played games in the full series.

The dataset contains:

- 1,074 player-matchup rows
- 29 offensive players
- 5 games
- matchup time and partial possessions
- points, field goals, three-point attempts, assists, turnovers, blocks, and related matchup statistics

Victor Wembanyama is the default offensive player in the dashboard.

## Example Finding

Wembanyama's primary defensive matchup changed throughout the series:

| Game | Primary matchup | Matchup time |
| --- | --- | ---: |
| 1 | Alex Caruso | 8:18 |
| 2 | Isaiah Hartenstein | 7:55 |
| 3 | Chet Holmgren | 5:13 |
| 4 | Isaiah Hartenstein | 4:22 |
| 5 | Isaiah Hartenstein | 6:46 |

Game 3 is especially interesting because Holmgren (5:13) and Hartenstein (5:10) split the assignment almost evenly.

A series-level total can make this look like one blended defensive strategy. The timeline shows that Oklahoma City changed the allocation of the matchup over time.

## Dashboard Features

- Select an offensive player
- View matchup time for every game in the series
- Compare game-by-game matchup share in a defender × game heatmap
- Highlight one defender while fading the others
- Identify primary and secondary defenders by game
- Inspect matchup share, partial possessions, shooting, eFG%, and PTS/75 in hover details
- Compare defensive responsibility across games

## Methodology

### Matchup time

The original matchup-time field is converted into seconds so assignments can be compared and visualized consistently.

### Matchup share

For each game:

```text
matchup share = defender matchup time / total recorded matchup time
```

### Primary and secondary defender

Defenders are ranked within each game by matchup time.

The defender with the most recorded matchup time is labeled **Primary** and the second-most is labeled **Secondary**.

### Matchup Share Heatmap

The heatmap reorganizes the same matchup-time data into a **defender × game matrix**.

Each cell represents:

```text
defender matchup time / total recorded matchup time for that game
```

This view is designed for series-level pattern recognition: it makes it easier to see when responsibility shifts from one defender to another, when a two-player split emerges, or when the defense settles into a more stable matchup plan.

For readability, the dashboard displays the defenders with the most total matchup time across the selected player's series.

### Series Adjustment Leaderboard

The leaderboard is also the entry point into the player-level analysis workflow.

After scanning the series, users can choose an eligible player directly beneath the leaderboard. The full dashboard below then updates to that player, including:

- game-by-game matchup timeline
- matchup-share heatmap
- concentration metrics
- outcome context
- Adjustment Score
- rule-based Adjustment Event Summary

The defender highlight remains a secondary control in the sidebar so the main workflow stays focused on **series scan → player selection → deeper analysis**.


The dashboard can also scan the entire series and rank offensive players by their **largest game-to-game matchup redistribution**.

For each eligible player, the leaderboard reports:

- Largest Adjustment Score
- Transition where the largest change occurred
- Average Adjustment Score across the series
- Number of primary-defender changes
- Average HHI matchup concentration
- Total recorded matchup minutes

Because low-volume players can produce unstable matchup-share swings, the leaderboard uses explicit eligibility filters.

The default view requires:

- **5 games played**
- **30 minutes of recorded matchup time across the series**

Users can adjust both thresholds in the sidebar.

Under the default eligibility settings, Victor Wembanyama ranks first in this series with a largest Adjustment Score of **0.620**, followed by Isaiah Hartenstein (**0.590**) and Keldon Johnson (**0.580**).

### Game Transition Comparison

The player-level dashboard also lets users inspect any available **game-to-game transition** directly rather than only the largest adjustment.

For the selected transition, the dashboard shows:

- each defender's matchup share before and after
- percentage-point changes in defender responsibility
- matchup time before and after
- Adjustment Score
- HHI concentration change
- primary-defender change
- PTS/75 change
- eFG% change
- TOV/75 change

A horizontal change chart makes it easy to see which defenders gained or lost the most matchup responsibility.

This turns the tool from a passive summary into an interactive scouting workflow: an analyst can identify an interesting transition, inspect the redistribution of assignments, and then compare the offensive outcomes over the same interval.

### Adjustment Event Summary

The dashboard generates a **rule-based summary** of the largest game-to-game matchup adjustment for the selected offensive player.

The summary combines:

- the largest Adjustment Score
- the defender with the largest matchup-share change
- any change in the primary defender
- the direction of HHI matchup concentration
- PTS/75, eFG%, and TOV/75 over the same transition
- an explicit caution that the outcome changes are descriptive rather than causal

This summary is generated deterministically from the calculated metrics rather than by a language model. The goal is to reduce the amount of manual interpretation required while keeping the logic transparent and reproducible.

### Outcome Context

The dashboard also summarizes the selected offensive player's recorded outcomes by game:

- Player points
- Partial possessions
- PTS/75
- eFG%
- TOV/75

These metrics are used as **descriptive context**, not as causal evidence that a specific defender or matchup adjustment produced the outcome.

For Wembanyama, the largest matchup adjustment occurred from Game 1 to Game 2. Over the same transition:

- **PTS/75:** 38.3 → 22.1
- **eFG%:** 66.2% → 64.7%
- **TOV/75:** 2.9 → 4.6

The scoring rate declined sharply and turnovers increased, while shooting efficiency changed only slightly. That distinction matters: the result suggests the change was not simply a matter of shots no longer falling.

Because these are small, game-level matchup samples, the dashboard avoids claiming that the defensive adjustment caused the outcome.

### Matchup Concentration

The dashboard also measures whether a team's matchup plan is concentrated on one or two defenders or distributed more broadly.

For each game it reports:

- **Primary Defender Share** — the largest individual matchup-time share
- **Top-2 Defender Share** — the combined share of the two most-used defenders
- **HHI Matchup Concentration** — the sum of squared defender matchup shares
- **Effective Defenders** — `1 / HHI`, a concentration-equivalent count

Higher HHI means the matchup allocation is more concentrated. A lower Effective Defenders value means fewer defenders account for most of the matchup responsibility.

For Victor Wembanyama:

| Game | Primary Share | Top-2 Share | HHI | Effective Defenders |
| --- | ---: | ---: | ---: | ---: |
| 1 | 36.2% | 54.1% | 0.204 | 4.90 |
| 2 | 54.6% | 71.8% | 0.340 | 2.94 |
| 3 | 33.9% | 67.5% | 0.250 | 3.99 |
| 4 | 36.1% | 57.7% | 0.209 | 4.79 |
| 5 | 45.5% | 70.0% | 0.283 | 3.53 |

This adds a second layer to the adjustment analysis. Game 2 was not only a different matchup distribution; it was also a more concentrated assignment. Game 3 then became a two-defender split, with Holmgren and Hartenstein combining for 67.5% of the recorded matchup time.

### Game-to-game Adjustment Score

The dashboard quantifies changes in matchup allocation using **total variation distance** between consecutive games.

```text
Adjustment Score = 0.5 × Σ |share_current − share_previous|
```

where each share is a defender's proportion of the offensive player's recorded matchup time in that game.

The score ranges from:

- **0.0** — identical matchup allocation
- **1.0** — completely different matchup allocation

For Victor Wembanyama, the largest change occurred from **Game 1 to Game 2 (0.620)**. Isaiah Hartenstein's matchup share increased by roughly **53 percentage points**, while Alex Caruso's fell by about **30 percentage points**.

### Efficiency metrics

The dashboard also calculates:

```text
eFG% = (FGM + 0.5 × 3PM) / FGA

PTS/75 = player points / partial possessions × 75
```

These statistics are shown as supporting context rather than proof of individual defensive effectiveness.

Single-game matchup samples can be very small, so the main analytical signal in this project is **matchup allocation**, not short-run shooting results.

## Project Structure

```text
playoff-matchup-adjustment-tracker/
├── app.py
├── data_pipeline.py
├── series_manifest.py
├── series_schema.py
├── series_ingestion.py
├── series_catalog.py
├── series/
├── docs/
├── data_sources/
│   ├── __init__.py
│   ├── nba_matchups.py
│   └── game_discovery.py
├── scripts/
│   ├── __init__.py
│   ├── fetch_matchup_game.py
│   ├── compare_api_manual.py
│   └── fetch_series.py
├── analytics/
│   ├── __init__.py
│   └── metrics.py
├── visualizations/
│   ├── __init__.py
│   └── charts.py
├── tests/
│   └── test_metrics.py
├── data/
│   └── OKC Spurs Matchup Data.csv
├── requirements.txt
├── requirements-dev.txt
├── requirements-data.txt
└── README.md
```

The project separates ingestion, data validation, analytics, visualization, and UI responsibilities:

- **`series_manifest.py` / `series_schema.py`** — configuration and versioned processed schema
- **`series_ingestion.py` / `data_sources/`** — cached CLI acquisition and game discovery
- **`series_catalog.py`** — local series loading and provenance checks
- **`data_pipeline.py`** — schema normalization, validation, and matchup-time parsing
- **`app.py`** — Streamlit controls, layout, and user workflow
- **`analytics/metrics.py`** — reusable matchup, concentration, outcome, transition, and summary logic
- **`visualizations/charts.py`** — Plotly chart construction

The data pipeline runs before any analytics are calculated. It checks required columns, player and team identities, game numbers, matchup-time values, numeric fields, negative values, duplicate rows, and team consistency. The app stops rather than silently analyzing invalid data.

The analytics module does not depend on Streamlit or Plotly, which keeps the core calculations easier to test and reuse.

## Tech Stack

- Python
- pandas
- Plotly
- Streamlit

## Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Windows checkouts may convert LF line endings to CRLF. Snapshot verification
accepts this conversion while still rejecting content changes; `.gitattributes`
keeps newly checked-out snapshots and approval evidence in their original format.
If an older checkout reports `Dataset hash differs from its ingestion report`,
stop Streamlit, run `git pull --ff-only`, and restart with
`python -m streamlit run app.py`. Do not edit the data or its report to bypass verification.

### Run Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The test suite covers core analytical properties and data validation, including:

- identical matchup distributions produce an Adjustment Score of 0
- complete redistribution produces an Adjustment Score of 1
- an even two-defender split produces HHI = 0.5 and Effective Defenders = 2
- valid matchup data passes the preparation pipeline
- missing required columns fail validation
- invalid matchup-time formats fail validation
- negative numeric values fail validation
- exact duplicate rows fail validation

## NBA Matchup Data Ingestion

The repository includes an adapter for NBA.com's game-level matchup data through the community-maintained `nba_api` package.

The target endpoint is `BoxScoreMatchupsV3`, which accepts a 10-digit NBA Game ID and exposes the same core fields used by this project, including matchup minutes, partial possessions, defender/offensive time shares, points, assists, turnovers, blocks, shooting, free throws, and shooting fouls.

The adapter normalizes the API response into the same schema as the current manually collected CSV, while retaining useful API-only fields such as player IDs, switches, potential assists, and help-defense statistics.

### Install data-ingestion dependencies

```bash
pip install -r requirements.txt
pip install -r requirements-data.txt
```

### Fetch one game

2026 Western Conference Finals Game 1 (San Antonio at Oklahoma City) uses NBA Game ID `0042500311`.

```bash
python -m scripts.fetch_matchup_game \
  --game-id 0042500311 \
  --game-number 1
```

By default, the normalized result is written to:

```text
data/api/0042500311_matchups.csv
```

The raw PlayerStats snapshot is also saved to `data/raw/<game_id>.csv`. These cache outputs are ignored by Git.

### Compare API data with the manually collected Game 1

```bash
python -m scripts.compare_api_manual \
  --game-id 0042500311 \
  --game-number 1
```

The comparison checks:

- matchup rows by offensive player, defensive player, and teams
- matchup time
- partial possessions
- defender/offensive/both-on time percentages
- points, assists, turnovers, blocks, shooting, free throws, and shooting fouls

Small tolerances are allowed for fields displayed with rounding on NBA.com. The command writes a JSON report and exits with code 1 when differences remain. Duplicate keys, missing fields, empty datasets, and missing numeric values cannot pass.

On 2026-10-05, the live Game 1 request succeeded: all 176 matchup identities aligned after correcting the adapter to treat `teamTricode` as the **offensive** team. Some times and statistics still differed. This has **not** passed parity validation. See [the recorded report](docs/api_manual_game1_comparison.json); the cause of the remaining differences is not established.

### Network reliability note

NBA Stats endpoints can time out or block requests from cloud-hosted environments. A GitHub Actions smoke test confirmed that `stats.nba.com` was not reachable reliably from the hosted runner, even though the rest of the project's automated tests passed.

For that reason, NBA network ingestion is intentionally separated from the dashboard and normal CI. The intended architecture is:

```text
NBA Game ID
    ↓
Local / controlled data fetch
    ↓
Normalized cached CSV
    ↓
Data validation
    ↓
Analytics
    ↓
Streamlit dashboard
```

This avoids making the user-facing app dependent on a live NBA endpoint and gives the project a reproducible raw-data layer.

## Series Pipeline

The dashboard only reads local reference files and validated processed snapshots. Network work stays in CLI ingestion commands.

```text
Series manifest / NBA game log
        ↓
Raw PlayerStats CSV cache
        ↓
Normalization + per-game validation
        ↓
Standardized series CSV + coverage/provenance report
        ↓
Season → Round → Series → Player → existing analytics
```

### Build the bundled manual sample (no network)

```bash
python -m scripts.fetch_series --manifest series/2026_okc_sas_sample.yml --offline
```

This writes `data/processed/2026_okc_sas_sample.csv` and its `.report.json`. The app can also validate and load the manual reference directly, so a fresh checkout still runs without ingestion or `nba_api`.

### Discover a series

```bash
python -m scripts.fetch_series \
  --season 2025-26 --season-type Playoffs --team-a OKC --team-b SAS \
  --round "Western Conference Finals" --discover-only
```

Discovery queries NBA `LeagueGameFinder`, verifies season/opponents/playoff IDs, removes exact duplicates, orders games chronologically, and checks gaps/conflicting dates/results. The generic round name comes from the playoff Game ID; `--round` supplies the conference-specific label. One team reaching four wins marks a best-of-seven series complete.

Discovery creates `series/<series_id>.yml` and caches the game log under `data/discovery/`. Existing curated manifests are never silently overwritten. Use a distinct `--series-id` when the intended snapshot differs.

For offline discovery, add `--offline --game-log-csv path/to/league_game_finder.csv`. Game IDs must remain strings with leading zeros.

### Acquire a separately versioned API snapshot

The owner approved an independent-snapshot policy on 2026-10-05, recorded in `docs/source_policy.json`. This requires unchanged benchmark/adapter hashes and the recorded one-to-one identity comparison. Numerical differences remain acknowledged, and the original manual dataset is never replaced.

```bash
python -m scripts.fetch_series \
  --season 2024-25 --team-a OKC --team-b IND --round "NBA Finals" \
  --series-id 2025_okc_ind_api_NEW_TIMESTAMP \
  --source-policy separate_snapshot --output-dir data/snapshots
```

Use a new timestamped series ID for each published version. `data/snapshots/` is checked in so the dashboard runs without network access or `nba_api`. Published snapshot CSVs cannot be overwritten through ingestion. Reports retain acquisition timestamps, raw and dataset hashes, manifest/discovery hashes, source policy hash, coverage, and the explicit failed manual-parity status. The imported Game 1 cache has an unknown acquisition timestamp, explicitly recorded as null rather than invented. Future fresh requests record UTC acquisition times.

### Optional strict historical parity gate

```bash
python -m scripts.compare_api_manual --game-id 0042500311 --game-number 1
python -m scripts.fetch_series \
  --manifest path/to/manifest.yml \
  --verification-report data/api/verification.json
```

Without `--source-policy separate_snapshot`, strict parity remains the default and currently refuses live acquisition because the comparison has not passed. A passing report must match the current adapter and original manual benchmark hash. Do not increase tolerances to hide differences or label snapshots as parity-verified.

With a passing gate, ingestion uses raw caches first, fetches missing games, retries a bounded number of times, spaces requests, validates each game, and publishes only when every configured game is present. Tune `--timeout`, `--retries`, and `--request-interval`; defaults are 20 seconds, 2 attempts, and 2 seconds between requests. Use `--cache-dir` or `--output-dir` for an alternative working location.

### Explore cached API snapshots offline

```bash
python -m scripts.fetch_series --manifest path/to/manifest.yml --offline
```

Offline mode makes no NBA requests and requires `data/raw/<game_id>.csv` for every configured game. These snapshots remain explicitly **unverified against the manual source**, both in their report and the dashboard. Offline mode is for reproducible exploration, not approval of API/manual parity.

### Add another series without analytical code changes

1. Place a valid YAML manifest in `series/` (copy the bundled examples).
2. For a manual source, set `source_csv` to its project-relative legacy CSV path. For API sources, omit it and include every game ID.
3. Generate its processed data and report using `scripts.fetch_series`.
4. Start/reload the app and select the season, round, and series.

Only successfully validated data reaches analytics. API manifests without processed datasets produce a clear unavailable message. The bundled dated manifests each have a complete real dataset and provenance report; tests verify real-series switching across seasons and rounds, including multiple series in one round, and synthetic edge cases. The old pending OKC–SAS configuration was replaced by its dated, fully acquired snapshot configuration.

### Schema and reports

`series_schema.py` defines schema version 1: season/round/series and game metadata; team/player IDs and names; matchup seconds/partial possessions; percentage fields in **0–100 display scale**; shooting/outcome and API-only context fields. Unknown IDs and dates remain null rather than being invented. `to_analytics` preserves the existing analytics interface and fractional seconds.

Reports distinguish:

- `coverage_complete`: every game explicitly listed in the manifest was loaded.
- `series_complete`: the manifest represents a decided series, rather than a sample or ongoing series.
- `source_verification`: strict parity `pass`, `offline_unverified` exploration, or `approved_separate_snapshot` (which explicitly retains `manual_parity: fail`).

A failed/partial run records individual failed IDs and exits non-zero without publishing a complete dataset. The dashboard refuses an incomplete report or changed dataset/manifest hash. For dated series it prefers the frozen published snapshot over disposable working caches. Writes are atomic; raw/processed/report working cache folders are ignored by Git, while published `data/snapshots/` files are versioned.

## Validation and V1.0 Acceptance

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
```

Normal CI installs only app/test dependencies, blocks live HTTP in tests, and validates manifests, discovery, schema, cache reuse, partial failures, source gates, and actual Streamlit interactions. It preserves the original Wembanyama largest adjustment of **0.620**. The existing manual-only API smoke workflow remains separate from normal CI.

V1.0 is implemented, merged and verified with the original two full real series under the approved source policy; the catalog now includes seven complete API series. Historical parity remains failed and visible; its cause is unconfirmed. Detailed evidence is recorded in [V1_VALIDATION.md](archive/V1_VALIDATION.md). Hosted Streamlit deployment has not been confirmed updated.

Team results and player game box scores are the first V2 context milestones.
Substitution/foul timelines and defensive personnel comparisons are available.
Five-player lineup reconstruction still requires validated substitution IDs and
period-opening players. Possession
models, ML, video, scouting PDFs and major UI redesign remain deferred.

## Author

**Ming Chen**  
Wake Forest University MSBA — Sports Analytics
