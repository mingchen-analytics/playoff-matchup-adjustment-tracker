# Playoff Matchup Adjustment Tracker

[Open the live Streamlit dashboard](https://playoff-matchup-adjustment-tracker-zdee28tjezgw42ujydet6v.streamlit.app/)

A basketball analytics prototype for tracking how defensive assignments change **game by game** during a playoff series.

## Why I Built This

Series-level matchup totals are useful, but they can hide the timing of tactical adjustments.

This project adds a game-by-game timeline layer so an analyst can quickly answer questions such as:

- Who was the primary defender on a specific offensive player?
- Did that assignment change during the series?
- Which defenders shared the responsibility?
- How much matchup time did each defender receive?

The concept was inspired by Databallr's playoff matchup pages and focuses on making matchup changes easier to see across games.

## Case Study

The current prototype uses a five-game **Oklahoma City vs. San Antonio** playoff series.

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
└── README.md
```

The project separates responsibilities into four layers:

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

## Limitations and Next Steps

This is currently a single-series product prototype rather than a league-wide automated system.

Potential extensions include:

- additional playoff series
- automated matchup-data ingestion
- team and series selectors
- possession-level video links
- clearer before/after adjustment annotations
- comparison of matchup allocation with lineup and scheme changes

## Author

**Ming Chen**  
Wake Forest University MSBA — Sports Analytics
