-- InsightRAG Postgres bootstrap (runs on first container start)
CREATE EXTENSION IF NOT EXISTS vector;

-- Operational warehouse (1998 MLB season via pybaseball).
CREATE TABLE IF NOT EXISTS players (
    player_id   TEXT PRIMARY KEY,
    first_name  TEXT,
    last_name   TEXT,
    full_name   TEXT,
    bats        TEXT,
    throws      TEXT,
    debut       TEXT
);

CREATE TABLE IF NOT EXISTS teams (
    team_id      TEXT PRIMARY KEY,
    name         TEXT,
    league       TEXT,
    division     TEXT,
    wins         INTEGER,
    losses       INTEGER,
    win_pct      DOUBLE PRECISION,
    runs_scored  INTEGER,
    runs_allowed INTEGER,
    attendance   INTEGER,
    park         TEXT
);

CREATE TABLE IF NOT EXISTS batting (
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

CREATE TABLE IF NOT EXISTS pitching (
    player_id TEXT,
    team_id   TEXT,
    stint     INTEGER,
    w         INTEGER,
    l         INTEGER,
    era       DOUBLE PRECISION,
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

CREATE TABLE IF NOT EXISTS fielding (
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

CREATE TABLE IF NOT EXISTS salaries (
    player_id TEXT,
    team_id   TEXT,
    league    TEXT,
    salary    INTEGER
);

CREATE TABLE IF NOT EXISTS awards (
    player_id TEXT,
    award_id  TEXT,
    league    TEXT,
    tie       TEXT
);

CREATE TABLE IF NOT EXISTS all_stars (
    player_id    TEXT,
    team_id      TEXT,
    league       TEXT,
    starting_pos INTEGER
);

CREATE TABLE IF NOT EXISTS standings (
    team       TEXT,
    league     TEXT,
    division   TEXT,
    wins       INTEGER,
    losses     INTEGER,
    win_pct    DOUBLE PRECISION,
    games_back TEXT
);

CREATE TABLE IF NOT EXISTS fangraphs_batting (
    player_name TEXT,
    team        TEXT,
    pa          INTEGER,
    ab          INTEGER,
    h           INTEGER,
    hr          INTEGER,
    rbi         INTEGER,
    avg         DOUBLE PRECISION,
    obp         DOUBLE PRECISION,
    slg         DOUBLE PRECISION,
    ops         DOUBLE PRECISION,
    woba        DOUBLE PRECISION,
    wrc_plus    INTEGER,
    war         DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS fangraphs_pitching (
    player_name TEXT,
    team        TEXT,
    w           INTEGER,
    l           INTEGER,
    era         DOUBLE PRECISION,
    ip          DOUBLE PRECISION,
    so          INTEGER,
    bb          INTEGER,
    fip         DOUBLE PRECISION,
    war         DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS fangraphs_fielding (
    player_name TEXT,
    team        TEXT,
    position    TEXT,
    inn         DOUBLE PRECISION,
    drs         DOUBLE PRECISION,
    uzr         DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS game_logs (
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

CREATE OR REPLACE VIEW players_1998 AS
SELECT DISTINCT p.player_id, p.first_name, p.last_name, p.full_name, p.bats, p.throws, p.debut
FROM players p
WHERE p.player_id IN (SELECT player_id FROM batting)
   OR p.player_id IN (SELECT player_id FROM pitching)
   OR p.player_id IN (SELECT player_id FROM fielding);

-- document_chunks table is created at ingest time with the correct embedding dimension
