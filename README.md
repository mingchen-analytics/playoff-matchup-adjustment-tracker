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
├── requirements.txt
├── README.md
└── data/
    └── OKC Spurs Matchup Data.csv
```

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
