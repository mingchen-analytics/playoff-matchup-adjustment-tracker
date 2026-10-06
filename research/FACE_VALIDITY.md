# Face-validity check: do model readings match game reporting?

Checked 2026-10-05. The model separates overlap (who shares the floor) from
assignment (who guards whom when both are on). It cannot see coaching intent.
This check asks whether the readings line up with contemporaneous reporting.

## Design

Cases were chosen by a rule fixed in code before any coverage was read
(`research/select_face_validity_cases.py`, output
`results/face_validity_cases.csv`). Population: consecutive games, comparable
coverage ≥ 0.80, offensive player averaging ≥ 28 minutes.

- **A — assignment-dominant, robust:** q < 0.10 on both noise bases,
  assignment ≥ 2 × overlap; top 4 by excess TVD, one per series.
- **B — overlap-dominant, robust:** same q rule, overlap ≥ 2 × assignment;
  top 3, one per series.
- **C — large but noise-like:** TVD ≥ 0.30, q ≥ 0.10 on both bases; top 2.

Wembanyama OKC–SAS G1→G2 is the motivating case. It was not selected blind and
is reported separately.

Every case got the same questions: does reporting describe a matchup or
rotation change, does it name the defenders, and does the direction agree with
the model? Coverage is limited to what web search and fetch could reach; film
and paywalled analysis were not reviewed. "Not found" means no reachable
reporting described the change, not that it did not happen.

## Results

| Group | Case | Model reading | Reporting | Verdict |
| --- | --- | --- | --- | --- |
| Motivating | Wembanyama, OKC–SAS G1→G2 | Hartenstein 2% → 58% (+38 overlap, +20 assignment); Caruso 36% → 6%, mostly assignment | NBA.com: Caruso drew Wembanyama in Game 1; Hartenstein's minutes went from 12 to 27 and he spent the most time on Wembanyama in Game 2, a deliberate plan to wear him down | **Confirmed**, both components |
| A | Dosunmu, DEN–MIN G4→G5 | Braun 20% → 37% (+22 assignment); Murray 39% → 21% | After Dosunmu's 43 points in Game 4, Denver coverage made him the Game 5 point of emphasis; no named defender | **Partial**: emphasis yes, Braun not named |
| A | Edwards, MIN–SAS G4→G5 | Vassell 52% → 34% (−19 assignment); Harper and Bryant up | Previews mention Spurs doubling Edwards; no named reassignment | **Not found** |
| A | Josh Hart, CLE–NYK G3→G4 | Jarrett Allen 34% → 8% (−27 assignment) | Game 4 was a 130–93 Knicks blowout; no matchup reporting | **Not found**; blowout confound |
| A | Marcus Smart, LAL–OKC G2→G3 | Ajay Mitchell 28% → 6% (−25 assignment); Gilgeous-Alexander 33% → 46% | Game 3 was a 131–108 Thunder blowout; preview silent on matchups | **Not found**; blowout confound |
| B | Vassell, MIN–SAS G2→G3 | Shannon 45% → 15%, Edwards 17% → 34%, mostly overlap | Edwards was back early from a knee bone bruise on managed minutes; his minutes rose from 24 to 41 | **Consistent** (availability) |
| B | Wembanyama, OKC–SAS G2→G3 | Hartenstein 58% → 35% (−24 overlap); Jaylin Williams up on overlap | AP built the Game 3 story around 76 Thunder bench points | **Consistent** (rotation) |
| B | Wembanyama, NYK–SAS G3→G4 | Towns 60% → 37% (−20 overlap, −2 assignment); Robinson up on overlap | Towns was in foul trouble in Game 4 | **Consistent** (foul trouble) |
| C | Castle, OKC–SAS G3→G4 | TVD 0.31 but within noise | No reported change on Castle | No reported change (weak support) |
| C | Holmgren, OKC–IND G6→G7 (2025) | TVD 0.31 but within noise | No reported change on Holmgren | No reported change (weak support) |

## What this says about the model

1. **The overlap component tracks documented causes.** All three
   overlap-dominant cases match a reported availability, rotation or
   foul-trouble story. This is the strongest external support so far, and it
   shows why separating overlap matters: these would otherwise look like
   coaching reassignments.
2. **The assignment component is rarely reported.** Press coverage names
   defenders mainly for stars (the Wembanyama case). For three of four blind
   assignment cases, nothing specific was found. Reporting is a weak source at
   this level of detail; film review is the right next check for group A.
3. **Blowouts are a confound.** Two of the four assignment cases came from
   20-plus-point games, where garbage-time units change who guards whom. Phase 5
   should control for final margin (available in the game-context data) or
   report results with and without lopsided games.
4. **Noise-like cases drew no reports of change**, which is consistent with the
   model but weak evidence: silence is the default.

Bottom line: the model's split is *plausible* where it can be checked, and the
overlap side has real support. The assignment side is not yet externally
confirmed beyond the motivating case. The project measures assignment
allocation; it does not identify coaching intent.

Note on the motivating case: Game 1 is one of the five games with the
percentage-field scale issue, so Hartenstein's assignment-rate level there
(≈29%) should be read loosely. The realized shares and the split do not use the
affected field, and the reported Caruso → Hartenstein change matches them.

## Sources (pages opened)

- [Isaiah Hartenstein plays his game vs. Victor Wembanyama — NBA.com](https://api-hub.nba.com/news/isaiah-hartenstein-plays-his-game-vs-victor-wembanyama)
- [Preview: Nuggets' season on the line in Game 5 — Denver Stiffs](https://www.denverstiffs.com/preview-nuggets-season-future-on-the-line-in-elimination-game-5/)
- [Nuggets–Timberwolves Game 5 gallery — Denver Gazette](https://www.denvergazette.com/?p=549805)
- [3 things to watch: Timberwolves–Spurs Game 6 — NBA.com](https://nba.com/news/3-things-to-watch-timberwolves-spurs-game-6)
- [Spurs beat Timberwolves, Game 5 — Boston Globe](https://www.bostonglobe.com/2026/05/12/sports/spurs-beat-timberwolves-nba/)
- [Knicks annihilate Cavs in Game 4 — Cleveland 19](https://www.cleveland19.com/2026/05/26/knicks-annihilate-cavs-game-4-ending-clevelands-season/)
- [3 things to watch in Thunder–Lakers Game 3 — NBA.com](https://www.nba.com/news/3-things-to-watch-in-thunder-lakers-game-3)
- [Thunder charge past Lakers 131–108 in Game 3 — AP via Tribune-Star](https://www.tribstar.com/region/thunder-charge-past-lakers-131-108-in-game-3-for-another-blowout-in-champs-7/article_7e652cff-4f89-5f77-bd77-eb421d14bccb.html)
- [Edwards cleared to play in series opener after expedited rehab — AP via WTOP](https://wtop.com/sports/2026/05/edwards-cleared-to-play-for-timberwolves-in-series-opener-against-spurs-after-expedited-rehab/)
- [Thunder get 76 points off the bench in Game 3 win — AP via Bozeman Daily Chronicle](https://www.bozemandailychronicle.com/ap_news/sports/thunder-get-76-points-off-the-bench-the-key-to-a-game-3-win-over/article_a81f2a22-1b1d-59fb-8a61-6ca7575d77d5.html)
- [NBA world reacts to Robinson's elbow, Finals Game 4 — Pro Football Network](https://www.profootballnetwork.com/nba/receipt-jalen-brunson-nba-world-reacts-mitchell-robinsons-dumb-elbow-victor-wembanyama-spurs-knicks-game-4-june-2026/)
