"""Rich, live schema context for text-to-SQL.

The goal is to give a local 7B model everything it needs to write correct SQLite
against the 1998 MLB warehouse: column meanings, real row counts, sample values,
join paths, and strict name-matching rules. Built once and cached per settings.
"""

from __future__ import annotations

from .config import Settings
from .warehouse import run_query

# table -> (one-line purpose, [(column, meaning), ...])
_TABLES: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "teams": (
        "One row per team (season totals).",
        [
            ("team_id", "Lahman team code, e.g. NYA, BOS, ATL"),
            ("name", "full team name, e.g. New York Yankees"),
            ("league", "AL or NL"),
            ("division", "E, C, or W"),
            ("wins", "team wins"),
            ("losses", "team losses"),
            ("win_pct", "winning percentage"),
            ("runs_scored", "team runs scored (use this for team offense totals)"),
            ("runs_allowed", "team runs allowed (use this for team pitching/defense totals)"),
            ("attendance", "home attendance"),
            ("park", "ballpark name"),
        ],
    ),
    "standings": (
        "Final 1998 standings by league+division with games-back.",
        [
            ("team", "full team name"),
            ("league", "AL or NL"),
            ("division", "East, Central, or West"),
            ("wins", "wins"),
            ("losses", "losses"),
            ("win_pct", "winning percentage"),
            ("games_back", "games behind division leader ('-' for leader)"),
        ],
    ),
    "players": (
        "All-time player registry (19k). Do NOT use for 1998 lookups; use players_1998.",
        [
            ("player_id", "Lahman id"),
            ("full_name", "player full name"),
            ("bats", "batting hand"),
            ("throws", "throwing hand"),
            ("debut", "MLB debut date"),
        ],
    ),
    "players_1998": (
        "Only players who appeared in 1998. USE THIS for name lookups.",
        [
            ("player_id", "Lahman id (join to batting/pitching/fielding)"),
            ("full_name", "player full name"),
        ],
    ),
    "batting": (
        "1998 batting, one row per player per team stint. SUM across stints per player.",
        [
            ("player_id", "join to players_1998.player_id"),
            ("team_id", "join to teams.team_id"),
            ("stint", "stint number if traded mid-season"),
            ("g", "games"), ("ab", "at-bats"), ("r", "runs"), ("h", "hits"),
            ("doubles", "2B"), ("triples", "3B"), ("hr", "home runs"),
            ("rbi", "runs batted in"), ("sb", "stolen bases"), ("bb", "walks"),
            ("so", "strikeouts"), ("hbp", "hit by pitch"), ("sf", "sacrifice flies"),
        ],
    ),
    "pitching": (
        "1998 pitching, one row per player per team stint. SUM across stints per player.",
        [
            ("player_id", "join to players_1998.player_id"),
            ("team_id", "join to teams.team_id"),
            ("w", "wins"), ("l", "losses"), ("era", "earned run average"),
            ("g", "games"), ("gs", "games started"), ("cg", "complete games"),
            ("so", "strikeouts"), ("bb", "walks"), ("h", "hits allowed"),
            ("hr", "home runs allowed"),
            ("ip_outs", "outs pitched; innings = ip_outs/3.0"),
            ("er", "earned runs"),
        ],
    ),
    "fielding": (
        "1998 fielding by position and stint.",
        [
            ("player_id", "join to players_1998.player_id"),
            ("team_id", "join to teams.team_id"),
            ("position", "P, C, 1B, 2B, 3B, SS, OF, etc."),
            ("g", "games"), ("gs", "games started"), ("po", "putouts"),
            ("a", "assists"), ("e", "errors"), ("dp", "double plays"),
        ],
    ),
    "salaries": (
        "1998 player salaries.",
        [
            ("player_id", "join to players_1998.player_id"),
            ("team_id", "join to teams.team_id"),
            ("league", "AL or NL"),
            ("salary", "salary in US dollars"),
        ],
    ),
    "awards": (
        "1998 player awards.",
        [
            ("player_id", "join to players_1998.player_id"),
            ("award_id", "award name, e.g. 'Most Valuable Player', 'Cy Young Award', 'Gold Glove'"),
            ("league", "AL or NL"),
            ("tie", "Y if tied"),
        ],
    ),
    "all_stars": (
        "1998 All-Star Game selections.",
        [
            ("player_id", "join to players_1998.player_id"),
            ("team_id", "join to teams.team_id"),
            ("league", "AL or NL"),
            ("starting_pos", "starting position number if a starter, else null"),
        ],
    ),
    "fangraphs_batting": (
        "1998 advanced batting, ONE row per player (already aggregated). "
        "Keyed by player_name (not id). wrc_plus and war are ESTIMATES.",
        [
            ("player_name", "player full name"),
            ("team", "primary team code"),
            ("pa", "plate appearances (use pa>=502 for batting-title qualifier)"),
            ("ab", "at-bats"), ("h", "hits"), ("hr", "home runs"), ("rbi", "RBI"),
            ("avg", "batting average"), ("obp", "on-base pct"), ("slg", "slugging"),
            ("ops", "OBP+SLG"), ("woba", "weighted on-base"),
            ("wrc_plus", "wRC+ estimate (100=league avg)"), ("war", "WAR estimate"),
        ],
    ),
    "fangraphs_pitching": (
        "1998 advanced pitching, ONE row per player (already aggregated). "
        "Keyed by player_name (not id). war is an ESTIMATE.",
        [
            ("player_name", "player full name"),
            ("team", "primary team code"),
            ("w", "wins"), ("l", "losses"), ("era", "ERA"),
            ("ip", "innings pitched (use ip>=162 for ERA-title qualifier)"),
            ("so", "strikeouts"), ("bb", "walks"), ("fip", "fielding-independent pitching"),
            ("war", "WAR estimate"),
        ],
    ),
    "game_logs": (
        "1998 game-by-game results, one row per team per game (for streaks/dates).",
        [
            ("game_date", "date string like 'Tuesday, Apr 7'"),
            ("game_num", "team's game number 1..162 in date order"),
            ("team_id", "Lahman team code"),
            ("team_name", "full team name"),
            ("opponent", "opponent team code"),
            ("home_away", "'home' or 'away'"),
            ("runs_for", "runs the team scored"),
            ("runs_against", "runs the team allowed"),
            ("result", "W or L (may include extra-inning suffix)"),
            ("win", "1 if won, 0 if lost"),
            ("streak", "running streak: +N during an N-game win streak, -N during a losing streak; "
                       "MAX(streak) per team = longest win streak, MIN(streak) = longest losing streak"),
        ],
    ),
}

_JOIN_MAP = """Join paths:
- Player names -> ids: join players_1998 p ON <table>.player_id = p.player_id, filter LOWER(p.full_name) LIKE '%name%'.
- Teams: <table>.team_id = teams.team_id. Team full name is teams.name.
- Traditional stats (batting/pitching/fielding) use player_id + SUM across stints.
- Advanced stats (fangraphs_batting/fangraphs_pitching) are pre-aggregated, one row per player, matched by player_name."""

_RULES = """Rules:
- SQLite dialect. Return ONE read-only SELECT (or WITH). No comments, no markdown, no prose.
- For a player's season totals from batting/pitching, SUM columns and GROUP BY player.
- For team offense totals use teams.runs_scored; do NOT sum batting for team runs.
- Batting-title qualifier = pa >= 502 (fangraphs_batting.pa). ERA-title qualifier = ip >= 162 (fangraphs_pitching.ip).
- Player name matching: use players_1998 (not players) and LOWER(full_name) LIKE '%lastname%'.
- Advanced metrics (OPS/OBP/SLG/wOBA/WAR/wRC+): use fangraphs_batting; pitching WAR/FIP: fangraphs_pitching.
- IMPORTANT: fangraphs_batting/fangraphs_pitching have NO player_id column. They are keyed by player_name only. Do NOT join them to players_1998/batting/pitching by id.
- To filter advanced stats by league/division: JOIN teams t ON fangraphs_batting.team = t.team_id, then filter t.league / t.division.
- To rank a TRADITIONAL counting stat (HR, RBI, SB, SO, wins, saves) by league: use batting/pitching JOIN players_1998 JOIN teams t ON team_id=t.team_id WHERE t.league='AL'/'NL', SUM and GROUP BY player.
- wrc_plus and war are estimates; still fine to rank/return.
- Always add a sensible LIMIT (e.g. 5-10) for leaderboards."""


def _counts(settings: Settings) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in _TABLES:
        try:
            out[t] = int(run_query(settings, f"SELECT COUNT(*) FROM {t}").rows[0][0])
        except Exception:  # noqa: BLE001
            out[t] = 0
    return out


def _samples(settings: Settings) -> list[str]:
    lines: list[str] = []

    def q(sql: str) -> list:
        try:
            return [r[0] for r in run_query(settings, sql).rows if r[0] is not None]
        except Exception:  # noqa: BLE001
            return []

    teams = q("SELECT name FROM teams ORDER BY wins DESC")
    if teams:
        lines.append("Team names: " + ", ".join(teams))
    positions = q("SELECT DISTINCT position FROM fielding WHERE position IS NOT NULL")
    if positions:
        lines.append("Fielding positions: " + ", ".join(map(str, positions)))
    awards = q("SELECT DISTINCT award_id FROM awards WHERE award_id IS NOT NULL ORDER BY award_id")
    if awards:
        lines.append("Award names: " + ", ".join(map(str, awards[:20])))
    stars = q("SELECT full_name FROM players_1998 ORDER BY full_name LIMIT 6")
    if stars:
        lines.append("Example player full_name values: " + ", ".join(map(str, stars)))
    return lines


_CACHE: dict[int, str] = {}


def build_schema_context(settings: Settings, *, use_cache: bool = True) -> str:
    key = id(settings)
    if use_cache and key in _CACHE:
        return _CACHE[key]

    counts = _counts(settings)
    blocks = ["1998 MLB season warehouse (SQLite, read-only). Tables and columns:"]
    for table, (purpose, cols) in _TABLES.items():
        n = counts.get(table, 0)
        col_str = ", ".join(f"{c} ({m})" for c, m in cols)
        blocks.append(f"\n{table} [{n} rows] — {purpose}\n  {col_str}")

    ctx = "\n".join(blocks)
    ctx += "\n\n" + _JOIN_MAP + "\n\n" + _RULES
    samples = _samples(settings)
    if samples:
        ctx += "\n\nSample values:\n- " + "\n- ".join(samples)

    if use_cache:
        _CACHE[key] = ctx
    return ctx


# Curated question -> SQL examples spanning the query space. These anchor the
# model on correct joins, name matching, aggregation, and qualifiers.
FEW_SHOT: list[tuple[str, str]] = [
    (
        "Who hit the most home runs in 1998?",
        "SELECT p.full_name, SUM(b.hr) AS hr FROM batting b "
        "JOIN players_1998 p ON b.player_id = p.player_id "
        "GROUP BY p.player_id, p.full_name ORDER BY hr DESC LIMIT 5",
    ),
    (
        "What were Sammy Sosa's stats in 1998?",
        "SELECT p.full_name, SUM(b.g) AS g, SUM(b.ab) AS ab, SUM(b.h) AS h, "
        "SUM(b.hr) AS hr, SUM(b.rbi) AS rbi, SUM(b.sb) AS sb FROM batting b "
        "JOIN players_1998 p ON b.player_id = p.player_id "
        "WHERE LOWER(p.full_name) LIKE '%sosa%' GROUP BY p.player_id, p.full_name",
    ),
    (
        "Which pitcher had the lowest ERA among qualified pitchers?",
        "SELECT player_name, era, ip FROM fangraphs_pitching WHERE ip >= 162 "
        "ORDER BY era ASC LIMIT 5",
    ),
    (
        "Who had the best OPS in the American League?",
        "SELECT fb.player_name, fb.ops FROM fangraphs_batting fb "
        "JOIN teams t ON fb.team = t.team_id "
        "WHERE t.league = 'AL' AND fb.pa >= 502 ORDER BY fb.ops DESC LIMIT 5",
    ),
    (
        "Which team scored the most runs?",
        "SELECT name, runs_scored FROM teams ORDER BY runs_scored DESC LIMIT 5",
    ),
    (
        "Show me the AL East standings.",
        "SELECT team, wins, losses, games_back FROM standings "
        "WHERE league = 'AL' AND division = 'East' ORDER BY wins DESC",
    ),
    (
        "How many qualified hitters batted under .250?",
        "SELECT player_name, avg FROM fangraphs_batting WHERE pa >= 502 AND avg < 0.250 "
        "ORDER BY avg ASC",
    ),
    (
        "Who were the highest paid players in 1998?",
        "SELECT p.full_name, s.salary FROM salaries s "
        "JOIN players_1998 p ON s.player_id = p.player_id "
        "ORDER BY s.salary DESC LIMIT 5",
    ),
    (
        "Compare Mark McGwire and Sammy Sosa home runs and RBIs.",
        "SELECT p.full_name, SUM(b.hr) AS hr, SUM(b.rbi) AS rbi FROM batting b "
        "JOIN players_1998 p ON b.player_id = p.player_id "
        "WHERE LOWER(p.full_name) LIKE '%mcgwire%' OR LOWER(p.full_name) LIKE '%sosa%' "
        "GROUP BY p.player_id, p.full_name",
    ),
    (
        "Who won the AL MVP?",
        "SELECT p.full_name, a.award_id, a.league FROM awards a "
        "JOIN players_1998 p ON a.player_id = p.player_id "
        "WHERE a.award_id LIKE '%Most Valuable%' AND a.league = 'AL'",
    ),
    (
        "Which team had the best pitching (fewest runs allowed)?",
        "SELECT name, runs_allowed FROM teams ORDER BY runs_allowed ASC LIMIT 5",
    ),
    (
        "Who led the NL in strikeouts among pitchers?",
        "SELECT p.full_name, SUM(pit.so) AS so FROM pitching pit "
        "JOIN players_1998 p ON pit.player_id = p.player_id "
        "JOIN teams t ON pit.team_id = t.team_id AND t.league = 'NL' "
        "GROUP BY p.player_id, p.full_name ORDER BY so DESC LIMIT 5",
    ),
    (
        "Who led the American League in home runs?",
        "SELECT p.full_name, SUM(b.hr) AS hr FROM batting b "
        "JOIN players_1998 p ON b.player_id = p.player_id "
        "JOIN teams t ON b.team_id = t.team_id AND t.league = 'AL' "
        "GROUP BY p.player_id, p.full_name ORDER BY hr DESC LIMIT 5",
    ),
    (
        "Who had the highest OPS in the National League?",
        "SELECT fb.player_name, fb.ops FROM fangraphs_batting fb "
        "JOIN teams t ON fb.team = t.team_id "
        "WHERE t.league = 'NL' AND fb.pa >= 502 ORDER BY fb.ops DESC LIMIT 5",
    ),
    (
        "Which shortstop hit the most home runs?",
        "SELECT p.full_name, SUM(b.hr) AS hr FROM batting b "
        "JOIN players_1998 p ON b.player_id = p.player_id "
        "JOIN fielding f ON f.player_id = p.player_id AND f.position = 'SS' "
        "GROUP BY p.player_id, p.full_name ORDER BY hr DESC LIMIT 5",
    ),
    (
        "What was the Texas Rangers' longest winning streak?",
        "SELECT team_name, MAX(streak) AS longest_win_streak FROM game_logs "
        "WHERE LOWER(team_name) LIKE '%rangers%'",
    ),
    (
        "What was the Yankees' record in one-run games?",
        "SELECT SUM(win) AS wins, SUM(1 - win) AS losses FROM game_logs "
        "WHERE LOWER(team_name) LIKE '%yankees%' AND ABS(runs_for - runs_against) = 1",
    ),
    (
        "What was the Braves' home record?",
        "SELECT SUM(win) AS home_wins, SUM(1 - win) AS home_losses FROM game_logs "
        "WHERE LOWER(team_name) LIKE '%braves%' AND home_away = 'home'",
    ),
]


def few_shot_block() -> str:
    lines = ["Examples (question -> SQL):"]
    for q, sql in FEW_SHOT:
        lines.append(f"Q: {q}\nSQL: {sql}")
    return "\n\n".join(lines)


def known_identifiers() -> set[str]:
    """Lower-cased table/view names + columns for lightweight validation."""
    ids: set[str] = set()
    for table, (_, cols) in _TABLES.items():
        ids.add(table.lower())
        for c, _m in cols:
            ids.add(c.lower())
    return ids
