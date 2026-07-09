"""Operational warehouse — SQLite (local) or Postgres (Docker).

Loads a **1998 MLB season** warehouse via `pybaseball` into a query-friendly
schema for text-to-SQL demos.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .db import connect
from .mlb_loader import load_mlb_1998

SQLITE_SCHEMA = """
CREATE TABLE players (
    player_id   TEXT PRIMARY KEY,
    first_name  TEXT,
    last_name   TEXT,
    full_name   TEXT,
    bats        TEXT,
    throws      TEXT,
    debut       TEXT
);

CREATE TABLE teams (
    team_id     TEXT PRIMARY KEY,
    name        TEXT,
    league      TEXT,
    division    TEXT,
    wins        INTEGER,
    losses      INTEGER,
    win_pct     REAL,
    runs_scored INTEGER,
    runs_allowed INTEGER,
    attendance  INTEGER,
    park        TEXT
);

-- Lahman (1998) player-season-by-team rows (traditional stats).
CREATE TABLE batting (
    player_id TEXT,
    team_id   TEXT,
    stint     INTEGER,
    g         INTEGER,
    ab        INTEGER,
    r         INTEGER,
    h         INTEGER,
    doubles   INTEGER,
    triples   INTEGER,
    hr        INTEGER,
    rbi       INTEGER,
    sb        INTEGER,
    bb        INTEGER,
    so        INTEGER,
    hbp       INTEGER,
    sf        INTEGER
);

CREATE TABLE pitching (
    player_id TEXT,
    team_id   TEXT,
    stint     INTEGER,
    w         INTEGER,
    l         INTEGER,
    era       REAL,
    g         INTEGER,
    gs        INTEGER,
    cg        INTEGER,
    so        INTEGER,
    bb        INTEGER,
    h         INTEGER,
    hr        INTEGER,
    ip_outs   INTEGER,
    er        INTEGER
);

CREATE TABLE fielding (
    player_id TEXT,
    team_id   TEXT,
    stint     INTEGER,
    position  TEXT,
    g         INTEGER,
    gs        INTEGER,
    po        INTEGER,
    a         INTEGER,
    e         INTEGER,
    dp        INTEGER
);

CREATE TABLE salaries (
    player_id TEXT,
    team_id   TEXT,
    league    TEXT,
    salary    INTEGER
);

CREATE TABLE awards (
    player_id TEXT,
    award_id  TEXT,
    league    TEXT,
    tie       TEXT
);

CREATE TABLE all_stars (
    player_id     TEXT,
    team_id       TEXT,
    league        TEXT,
    starting_pos  INTEGER
);

CREATE TABLE standings (
    team       TEXT,
    league     TEXT,
    division   TEXT,
    wins       INTEGER,
    losses     INTEGER,
    win_pct    REAL,
    games_back TEXT
);

-- FanGraphs (1998) advanced metrics (denormalized for easier NLQ).
CREATE TABLE fangraphs_batting (
    player_name TEXT,
    team        TEXT,
    pa          INTEGER,
    ab          INTEGER,
    h           INTEGER,
    hr          INTEGER,
    rbi         INTEGER,
    avg         REAL,
    obp         REAL,
    slg         REAL,
    ops         REAL,
    woba        REAL,
    wrc_plus    INTEGER,
    war         REAL
);

CREATE TABLE fangraphs_pitching (
    player_name TEXT,
    team        TEXT,
    w           INTEGER,
    l           INTEGER,
    era         REAL,
    ip          REAL,
    so          INTEGER,
    bb          INTEGER,
    fip         REAL,
    war         REAL
);

CREATE TABLE fangraphs_fielding (
    player_name TEXT,
    team        TEXT,
    position    TEXT,
    inn         REAL,
    drs         REAL,
    uzr         REAL
);

-- Game-by-game results (one row per team per game) for streak/date questions.
CREATE TABLE game_logs (
    game_date    TEXT,
    game_num     INTEGER,
    team_id      TEXT,
    team_name    TEXT,
    opponent     TEXT,
    home_away    TEXT,
    runs_for     INTEGER,
    runs_against INTEGER,
    result       TEXT,
    win          INTEGER,
    streak       INTEGER
);

-- Players who actually appeared in 1998 (avoids matching the all-time registry).
CREATE VIEW players_1998 AS
SELECT DISTINCT p.player_id, p.first_name, p.last_name, p.full_name, p.bats, p.throws, p.debut
FROM players p
WHERE p.player_id IN (SELECT player_id FROM batting)
   OR p.player_id IN (SELECT player_id FROM pitching)
   OR p.player_id IN (SELECT player_id FROM fielding);
"""

SCHEMA_DESCRIPTION = """
1998 MLB season warehouse (read-only).

This database includes Lahman (traditional stats, stable IDs) and FanGraphs
(advanced metrics) for the 1998 season.

Core tables (Lahman, 1998-only):
- players(player_id, first_name, last_name, full_name, bats, throws, debut)
- teams(team_id, name, league, division, wins, losses, win_pct, runs_scored, runs_allowed, attendance, park)
- batting(player_id, team_id, stint, g, ab, r, h, doubles, triples, hr, rbi, sb, bb, so, hbp, sf)
- pitching(player_id, team_id, stint, w, l, era, g, gs, cg, so, bb, h, hr, ip_outs, er)
- fielding(player_id, team_id, stint, position, g, gs, po, a, e, dp)
- salaries(player_id, team_id, league, salary)
- awards(player_id, award_id, league, tie)
- all_stars(player_id, team_id, league, starting_pos)
- standings(team, league, division, wins, losses, win_pct, games_back)  -- league AL/NL; division East/Central/West

Advanced tables (computed locally from Lahman, 1998):
- fangraphs_batting(player_name, team, pa, ab, h, hr, rbi, avg, obp, slg, ops, woba, wrc_plus, war)  -- one row per player; wrc_plus and war are ESTIMATES
- fangraphs_pitching(player_name, team, w, l, era, ip, so, bb, fip, war)  -- one row per player; war is an ESTIMATE
- fangraphs_fielding(player_name, team, position, inn, drs, uzr)  -- empty (DRS/UZR not derivable); use `fielding` for fielding

Helper view:
- players_1998 = only players who appeared in 1998 (use this for name lookups instead of `players`, which is the all-time registry).

Join paths:
- Use Lahman IDs: players.player_id = batting.player_id = pitching.player_id = fielding.player_id
- Teams: teams.team_id = batting.team_id (same for pitching/fielding/salaries)

Derived formulas (if needed):
- Batting AVG = h / ab
- Innings pitched (approx) = ip_outs / 3.0
- Pitching ERA = (er * 9) / (ip_outs / 3.0)
""".strip()


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple]
    sql: str


def init_warehouse(settings: Settings) -> None:
    if settings.uses_postgres:
        with connect(settings) as conn:
            cur = conn.cursor()
            for table in (
                "game_logs",
                "fangraphs_fielding",
                "fangraphs_pitching",
                "fangraphs_batting",
                "standings",
                "all_stars",
                "awards",
                "salaries",
                "fielding",
                "pitching",
                "batting",
                "teams",
                "players",
            ):
                cur.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE")
            conn.commit()
        return

    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    if settings.db_path.exists():
        settings.db_path.unlink()
    conn = sqlite3.connect(settings.db_path)
    try:
        conn.executescript(SQLITE_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def seed_warehouse(settings: Settings, seed_value: int = 42) -> dict[str, int]:
    del seed_value  # 1998 MLB load is deterministic for a fixed year
    data = load_mlb_1998()
    with connect(settings) as conn:
        cur = conn.cursor()
        if settings.uses_postgres:
            _insert_many(cur, "players", data["players"])
            _insert_many(cur, "teams", data["teams"])
            _insert_many(cur, "batting", data["batting"])
            _insert_many(cur, "pitching", data["pitching"])
            _insert_many(cur, "fielding", data["fielding"])
            _insert_many(cur, "salaries", data["salaries"])
            _insert_many(cur, "awards", data["awards"])
            _insert_many(cur, "all_stars", data["all_stars"])
            _insert_many(cur, "standings", data["standings"])
            _insert_many(cur, "fangraphs_batting", data["fangraphs_batting"])
            _insert_many(cur, "fangraphs_pitching", data["fangraphs_pitching"])
            _insert_many(cur, "fangraphs_fielding", data["fangraphs_fielding"])
            _insert_many(cur, "game_logs", data.get("game_logs", []))
        else:
            cur.executemany("INSERT INTO players VALUES (?,?,?,?,?,?,?)", data["players"])
            cur.executemany("INSERT INTO teams VALUES (?,?,?,?,?,?,?,?,?,?,?)", data["teams"])
            cur.executemany("INSERT INTO batting VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", data["batting"])
            cur.executemany("INSERT INTO pitching VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", data["pitching"])
            cur.executemany("INSERT INTO fielding VALUES (?,?,?,?,?,?,?,?,?,?)", data["fielding"])
            cur.executemany("INSERT INTO salaries VALUES (?,?,?,?)", data["salaries"])
            cur.executemany("INSERT INTO awards VALUES (?,?,?,?)", data["awards"])
            cur.executemany("INSERT INTO all_stars VALUES (?,?,?,?)", data["all_stars"])
            cur.executemany("INSERT INTO standings VALUES (?,?,?,?,?,?,?)", data["standings"])
            cur.executemany(
                "INSERT INTO fangraphs_batting VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                data["fangraphs_batting"],
            )
            cur.executemany(
                "INSERT INTO fangraphs_pitching VALUES (?,?,?,?,?,?,?,?,?,?)",
                data["fangraphs_pitching"],
            )
            cur.executemany(
                "INSERT INTO fangraphs_fielding VALUES (?,?,?,?,?,?)",
                data["fangraphs_fielding"],
            )
            cur.executemany(
                "INSERT INTO game_logs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                data.get("game_logs", []),
            )
        conn.commit()
    return {k: len(v) for k, v in data.items()}


def _insert_many(cur, table: str, rows: list[tuple]) -> None:
    if not rows:
        return
    placeholders = ", ".join(["%s"] * len(rows[0]))
    cur.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)


def init_db(db_path: Path) -> None:
    from .config import get_settings

    s = get_settings()
    if s.uses_postgres:
        init_warehouse(s)
    else:
        s.db_path = db_path
        init_warehouse(s)


def seed(db_path: Path, seed_value: int = 42) -> dict[str, int]:
    from .config import get_settings

    s = get_settings()
    if not s.uses_postgres:
        s.db_path = db_path
    return seed_warehouse(s, seed_value)


def is_read_only(sql: str) -> bool:
    s = sql.strip().strip(";").lower()
    if ";" in s:
        return False
    if not (s.startswith("select") or s.startswith("with")):
        return False
    forbidden = (
        "insert", "update", "delete", "drop", "alter", "create",
        "attach", "pragma", "replace", "truncate", "grant",
    )
    return not any(f in s for f in forbidden)


def run_query(settings: Settings, sql: str, limit: int = 100) -> QueryResult:
    if not is_read_only(sql):
        raise ValueError("Only read-only SELECT queries are permitted.")
    with connect(settings) as conn:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchmany(limit)
        if settings.uses_postgres:
            columns = [d.name for d in cur.description] if cur.description else []
        else:
            columns = [d[0] for d in cur.description] if cur.description else []
        return QueryResult(columns=columns, rows=rows, sql=sql)


def run_query_path(db_path: Path, sql: str, limit: int = 100) -> QueryResult:
    from .config import get_settings

    settings = get_settings()
    if not settings.uses_postgres:
        settings = settings.model_copy(update={"db_path": db_path})
    return run_query(settings, sql, limit)
