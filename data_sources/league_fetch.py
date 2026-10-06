"""League-wide playoff acquisition: discovery, per-game raw caches, normalization.

Network access happens only through the injected fetchers, so everything here
is testable offline. Raw responses are cached per game; a rerun skips cached
games, so an interrupted acquisition resumes where it stopped.

Outputs (under ``data/league/``):

    games.csv.gz      one row per team per game (LeagueGameFinder fields)
    matchups.csv.gz   BoxScoreMatchupsV3 rows in the research schema
    boxscores.csv.gz  BoxScoreTraditionalV3 player rows
    fetch_report.json per-season counts, failed games with reasons, and the
                      per-game off_time_percent scale check
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from data_sources.nba_matchups import normalize_boxscore_matchups
from player_context import normalize_player_boxscore

SEASON_PATTERN = re.compile(r"^\d{4}-\d{2}$")
PLAYOFF_GAME = re.compile(r"^004\d{7}$")
ROUNDS = {"1": "First Round", "2": "Conference Semifinals",
          "3": "Conference Finals", "4": "NBA Finals"}
GAME_LOG_COLUMNS = ["SEASON_ID", "TEAM_ABBREVIATION", "GAME_ID", "GAME_DATE",
                    "MATCHUP", "WL", "PTS", "PLUS_MINUS"]
MATCHUP_COLUMNS = [
    "season", "playoff_round", "series_id", "game_id", "game_number", "game_date",
    "off_team", "off_player_id", "off_player", "def_team", "def_player_id",
    "def_player", "matchup_seconds", "partial_possessions", "def_time_percent",
    "off_time_percent", "both_on_percent", "player_points", "team_points", "ast",
    "tov", "blk", "fgm", "fga", "three_pm", "three_pa", "ftm", "fta",
    "shooting_fouls", "switches_on", "data_source",
]


def check_season(season):
    if not SEASON_PATTERN.fullmatch(season):
        raise ValueError(f"Season must look like 2024-25, got {season!r}.")
    start = int(season[:4])
    if int(season[5:]) != (start + 1) % 100:
        raise ValueError(f"Season {season!r} is not a consecutive pair of years.")
    return season


def discover_playoff_games(game_log, season):
    """Long table (one row per team per game) of played playoff games."""
    check_season(season)
    missing = set(GAME_LOG_COLUMNS) - set(game_log.columns)
    if missing:
        raise ValueError(f"Game log missing columns: {sorted(missing)}")
    log = game_log[GAME_LOG_COLUMNS].copy()
    log["GAME_ID"] = log.GAME_ID.astype(str).str.zfill(10)
    log = log[log.GAME_ID.str.fullmatch(PLAYOFF_GAME)]
    log = log[log.GAME_ID.str[3:5].eq(season[2:4])]
    log = log.drop_duplicates(["GAME_ID", "TEAM_ABBREVIATION"])
    counts = log.groupby("GAME_ID").size()
    if (counts != 2).any():
        bad = counts[counts != 2].index.tolist()[:5]
        raise ValueError(f"Games without exactly two team rows: {bad}")
    if not log.WL.isin(["W", "L"]).all():
        raise ValueError("Every played game needs a W/L result.")
    teams = log.groupby("GAME_ID").TEAM_ABBREVIATION.agg(lambda s: tuple(sorted(s)))
    log["opponent"] = [
        [t for t in teams[g] if t != team][0]
        for g, team in zip(log.GAME_ID, log.TEAM_ABBREVIATION)
    ]
    series_key = log.GAME_ID.str[:-1]
    pair = series_key.map(log.groupby(series_key).apply(
        lambda f: "_".join(sorted(set(f.TEAM_ABBREVIATION)))
    ))
    if (series_key.groupby(series_key).transform("size") > 14).any():
        raise ValueError("A series has more than seven games.")
    log["season"] = season
    log["playoff_round"] = log.GAME_ID.str[7].map(ROUNDS).fillna("Playoffs")
    log["series_id"] = (season.replace("-", "_") + "_" + pair).str.lower()
    log["game_number"] = log.GAME_ID.str[-1].astype(int)
    log["GAME_DATE"] = pd.to_datetime(log.GAME_DATE).dt.strftime("%Y-%m-%d")
    games = log.rename(columns={
        "GAME_ID": "game_id", "GAME_DATE": "game_date", "TEAM_ABBREVIATION": "team",
        "WL": "wl", "PTS": "points", "PLUS_MINUS": "margin", "MATCHUP": "matchup",
    })
    games["home"] = games.matchup.str.contains(" vs. ", regex=False)
    columns = ["season", "playoff_round", "series_id", "game_id", "game_number",
               "game_date", "team", "opponent", "home", "wl", "points", "margin"]
    return games[columns].sort_values(["series_id", "game_number", "team"]).reset_index(drop=True)


def _seconds(text):
    if not isinstance(text, str) or ":" not in text:
        raise ValueError(f"Bad matchup time {text!r}.")
    minutes, seconds = text.split(":")
    return int(minutes) * 60 + int(seconds)


def normalize_matchups(raw, game, teams=None):
    """BoxScoreMatchupsV3 PlayerStats -> research schema for one game."""
    frame = normalize_boxscore_matchups(raw, game_number=int(game.game_number))
    if not frame["Game ID"].eq(game.game_id).all():
        raise ValueError("Matchup response belongs to a different game.")
    if teams is not None and set(frame["OFF Team"]) != set(teams):
        raise ValueError("Matchup response teams do not match the game.")
    out = pd.DataFrame({
        "season": game.season,
        "playoff_round": game.playoff_round,
        "series_id": game.series_id,
        "game_id": game.game_id,
        "game_number": int(game.game_number),
        "game_date": game.game_date,
        "off_team": frame["OFF Team"],
        "off_player_id": frame["OFF Player ID"].astype(int),
        "off_player": frame["Offense Player"],
        "def_team": frame["DEF Team"],
        "def_player_id": frame["DEF Player ID"].astype(int),
        "def_player": frame["Defense Player"],
        "matchup_seconds": frame["MIN"].map(_seconds),
        "partial_possessions": frame["Partial Poss"],
        "def_time_percent": frame["DEF Time Percent"],
        "off_time_percent": frame["OFF Time Percent"],
        "both_on_percent": frame["Both On Percent"],
        "player_points": frame["Players PTS"],
        "team_points": frame["Team PTS"],
        "ast": frame["AST"], "tov": frame["TOV"], "blk": frame["BLK"],
        "fgm": frame["FGM"], "fga": frame["FGA"], "three_pm": frame["3PM"],
        "three_pa": frame["3PA"], "ftm": frame["FTM"], "fta": frame["FTA"],
        "shooting_fouls": frame["SFL"], "switches_on": frame["Switches On"],
        "data_source": "nba_boxscorematchupsv3",
    })
    if out.duplicated(["off_player_id", "def_player_id"]).any():
        raise ValueError("Duplicate offensive/defensive pairs in one game.")
    return out[MATCHUP_COLUMNS]


def normalize_boxscores(payload, game, teams):
    meta = SimpleNamespace(game_id=game.game_id, game_number=int(game.game_number),
                           game_date=game.game_date)
    manifest = SimpleNamespace(team_a=teams[0], team_b=teams[1])
    frame = normalize_player_boxscore(payload, meta, manifest)
    frame.insert(0, "series_id", game.series_id)
    return frame


def percentage_scale(matchups, tolerance=0.01):
    """Per game: how many player-games have off_time_percent sums off 100%."""
    sums = matchups.groupby(["game_id", "off_player_id"]).off_time_percent.sum() / 100
    off = (sums - 1).abs() > tolerance
    by_game = off.groupby(level=0).sum()
    return {g: int(n) for g, n in by_game.items() if n}


class LeagueFetcher:
    """Resumable acquisition with injected network fetchers."""

    def __init__(self, root, game_log_fetcher, matchup_fetcher, boxscore_fetcher,
                 request_interval=2.0, offline=False, log=print):
        self.root = Path(root)
        self.out = self.root / "data" / "league"
        self.raw = self.out / "raw"
        self.fetch_game_log = game_log_fetcher
        self.fetch_matchups = matchup_fetcher
        self.fetch_boxscore = boxscore_fetcher
        self.interval = request_interval
        self.offline = offline
        self.log = log
        self.requests = 0

    def _pause(self):
        if self.requests and self.interval:
            time.sleep(self.interval)
        self.requests += 1

    def game_log(self, season):
        path = self.raw / "game_logs" / f"{season}.csv"
        if not path.exists():
            if self.offline:
                raise FileNotFoundError(f"No cached game log for {season}.")
            self._pause()
            frame = self.fetch_game_log(season)
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(path, index=False)
        return pd.read_csv(path, dtype={"GAME_ID": str, "SEASON_ID": str})

    def _cached(self, path, fetch, write):
        if path.exists():
            return path
        if self.offline:
            raise FileNotFoundError(f"Not cached: {path.name}")
        self._pause()
        data = fetch()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        write(data, tmp)
        tmp.replace(path)
        return path

    def run(self, seasons, max_games=None):
        report = {"started_at": datetime.now(timezone.utc).isoformat(),
                  "seasons": {}, "failed_games": [], "percentage_scale_games": {}}
        all_games, all_matchups, all_boxes = [], [], []
        fetched = 0
        for season in seasons:
            games = discover_playoff_games(self.game_log(season), season)
            unique = games.drop_duplicates("game_id")
            ok = 0
            for game in unique.itertuples(index=False):
                if max_games is not None and fetched >= max_games:
                    break
                teams = tuple(sorted(games[games.game_id.eq(game.game_id)].team))
                try:
                    mpath = self._cached(
                        self.raw / "matchups" / f"{game.game_id}.csv",
                        lambda: self.fetch_matchups(game.game_id),
                        lambda frame, p: frame.to_csv(p, index=False),
                    )
                    bpath = self._cached(
                        self.raw / "boxscores" / f"{game.game_id}.json",
                        lambda: self.fetch_boxscore(game.game_id),
                        lambda payload, p: p.write_text(json.dumps(payload)),
                    )
                    raw = pd.read_csv(mpath, dtype={"gameId": str})
                    raw["gameId"] = raw.gameId.str.zfill(10)
                    all_matchups.append(normalize_matchups(raw, game, teams))
                    all_boxes.append(normalize_boxscores(
                        json.loads(bpath.read_text()), game, teams))
                    ok += 1
                    fetched += 1
                except Exception as exc:  # recorded, never silently dropped
                    report["failed_games"].append({
                        "season": season, "game_id": game.game_id,
                        "series_id": game.series_id, "error": f"{type(exc).__name__}: {exc}",
                    })
                    self.log(f"  {game.game_id}: {type(exc).__name__}: {exc}")
            all_games.append(games)
            report["seasons"][season] = {
                "series": int(games.series_id.nunique()),
                "games": int(len(unique)), "games_acquired": ok,
            }
            self.log(f"{season}: {ok}/{len(unique)} games")
        self.out.mkdir(parents=True, exist_ok=True)
        games = pd.concat(all_games, ignore_index=True) if all_games else pd.DataFrame()
        matchups = pd.concat(all_matchups, ignore_index=True) if all_matchups else pd.DataFrame(columns=MATCHUP_COLUMNS)
        boxes = pd.concat(all_boxes, ignore_index=True) if all_boxes else pd.DataFrame()
        games.to_csv(self.out / "games.csv.gz", index=False)
        matchups.to_csv(self.out / "matchups.csv.gz", index=False)
        boxes.to_csv(self.out / "boxscores.csv.gz", index=False)
        if not matchups.empty:
            report["percentage_scale_games"] = percentage_scale(matchups)
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        report["rows"] = {"games": int(len(games)), "matchups": int(len(matchups)),
                          "boxscores": int(len(boxes))}
        (self.out / "fetch_report.json").write_text(json.dumps(report, indent=2) + "\n")
        return report


def probe(seasons, game_log_fetcher, matchup_fetcher, log=print):
    """Which seasons return matchup rows? Tries the first playoff game of each."""
    results = {}
    for season in seasons:
        try:
            games = discover_playoff_games(game_log_fetcher(season), season)
            game_id = games.game_id.min()
            rows = len(matchup_fetcher(game_id))
            results[season] = {"game_id": game_id, "rows": rows}
        except Exception as exc:
            results[season] = {"error": f"{type(exc).__name__}: {exc}"}
        log(f"{season}: {results[season]}")
    return results


def live_fetchers(timeout=30, retries=3):
    """nba_api-backed fetchers; imported lazily so tests never need nba_api."""
    from data_sources.nba_matchups import fetch_boxscore_matchups
    from data_sources.player_boxscores import fetch_player_boxscore

    def game_log(season):
        from nba_api.stats.endpoints import leaguegamefinder
        return leaguegamefinder.LeagueGameFinder(
            season_nullable=season, season_type_nullable="Playoffs",
            league_id_nullable="00", timeout=timeout,
        ).league_game_finder_results.get_data_frame()

    return (
        game_log,
        lambda game_id: fetch_boxscore_matchups(game_id, timeout=timeout, retries=retries),
        lambda game_id: fetch_player_boxscore(game_id, timeout=timeout, retries=retries),
    )
