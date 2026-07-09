"""Natural-language -> SQL agent over the operational warehouse."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import Settings
from .llm import LLM
from .sql_context import build_schema_context, few_shot_block, known_identifiers
from .warehouse import QueryResult, is_read_only, run_query


@dataclass
class SQLAnswer:
    sql: str
    result: QueryResult | None
    error: str | None = None


_SQL_SYSTEM = (
    "You are a SQLite expert for a 1998 MLB stats warehouse. "
    "Given the schema, rules, examples, and a question, return ONE read-only SQL "
    "query (SELECT or WITH only). Return ONLY the SQL text — no prose, no markdown, "
    "no code fences, no 'SQL:' label. Follow the schema's join paths and rules "
    "exactly: use players_1998 for name lookups, SUM across stints for player "
    "totals, teams.runs_scored for team offense, fangraphs_batting/fangraphs_pitching "
    "for advanced metrics, and add a LIMIT for leaderboards."
)

_MAX_SQL_TRIES = 3


def _round(expr: str) -> str:
    """ROUND to 2 decimals — CAST keeps Postgres and SQLite compatible."""
    return f"ROUND(CAST({expr} AS numeric), 2)"


_LEADERBOARD_WORDS = (
    "most", "led", "leader", "leaders", "best", "highest", "lowest",
    "top", "fewest", "least", "worst",
)
_POSITION_WORDS = (
    "shortstop", "catcher", "outfielder", "outfield", "first base", "second base",
    "third base", "designated hitter", "center field", "right field", "left field",
    "first baseman", "second baseman", "third baseman",
)


def _has_split_qualifier(q: str) -> bool:
    """League/position-filtered leaderboards need joins; defer to generative SQL."""
    has_lb = any(w in q for w in _LEADERBOARD_WORDS)
    if not has_lb:
        return False
    if "standing" in q or "division" in q:
        return False  # standings template is already league/division aware
    league = bool(
        re.search(r"\b(national league|american league)\b", q)
        or re.search(r"\bal\b", q)
        or re.search(r"\bnl\b", q)
    )
    position = any(p in q for p in _POSITION_WORDS)
    return league or position


def _rule_based_sql(question: str) -> str | None:
    """Offline / fallback templates for common 1998 MLB questions."""
    q = question.lower()

    # League/position-filtered leaderboards are handled by the generative loop,
    # which can write the necessary joins (templates would ignore the filter).
    if _has_split_qualifier(q):
        return None

    # Home run leaders / most HRs
    if ("home run" in q or "homer" in q or re.search(r"\bhr\b", q)) and (
        "most" in q or "led" in q or "leader" in q or "top" in q or "who" in q
    ):
        m = re.search(r"top\s+(\d+)", q)
        n = int(m.group(1)) if m else 5
        if "mark mcgwire" in q or "mcgwire" in q:
            return (
                "SELECT p.full_name AS player, SUM(b.hr) AS hr "
                "FROM batting b JOIN players_1998 p ON b.player_id = p.player_id "
                "WHERE LOWER(p.full_name) LIKE '%mcgwire%' "
                "GROUP BY p.player_id, p.full_name"
            )
        return (
            "SELECT p.full_name AS player, SUM(b.hr) AS hr "
            "FROM batting b JOIN players_1998 p ON b.player_id = p.player_id "
            "GROUP BY p.player_id, p.full_name "
            "ORDER BY hr DESC "
            f"LIMIT {n}"
        )

    if "mcgwire" in q and ("hr" in q or "home run" in q or "homer" in q):
        return (
            "SELECT p.full_name AS player, SUM(b.hr) AS hr "
            "FROM batting b JOIN players_1998 p ON b.player_id = p.player_id "
            "WHERE LOWER(p.full_name) LIKE '%mcgwire%' "
            "GROUP BY p.player_id, p.full_name"
        )

    # Named player home runs: "How many home runs did Sammy Sosa hit"
    if "home run" in q or "homer" in q or re.search(r"\bhr\b", q):
        m = re.search(
            r"(?:how many home runs did|home runs did)\s+([a-zà-ÿ'.\- ]+?)\s+(?:hit|have)",
            q,
        )
        if not m:
            m = re.search(r"([a-zà-ÿ'.\- ]+?)(?:'s)\s+(?:home runs|hr|homers)", q)
        if m:
            name = m.group(1).strip()
            name = re.sub(r"\s+(?:jr\.?|sr\.?|ii|iii|iv)$", "", name).strip()
            if len(name) >= 3:
                return (
                    "SELECT p.full_name AS player, SUM(b.hr) AS hr "
                    "FROM batting b JOIN players_1998 p ON b.player_id = p.player_id "
                    f"WHERE LOWER(p.full_name) LIKE '%{name}%' "
                    "GROUP BY p.player_id, p.full_name"
                )

    # RBI leaders
    if "rbi" in q and ("most" in q or "led" in q or "leader" in q or "top" in q or "who" in q):
        m = re.search(r"top\s+(\d+)", q)
        n = int(m.group(1)) if m else 5
        return (
            "SELECT p.full_name AS player, SUM(b.rbi) AS rbi "
            "FROM batting b JOIN players_1998 p ON b.player_id = p.player_id "
            "GROUP BY p.player_id, p.full_name "
            "ORDER BY rbi DESC "
            f"LIMIT {n}"
        )

    # ERA / Pedro Martínez  (\bera\b avoids matching "avERAge")
    if "pedro" in q and re.search(r"\bera\b", q):
        return (
            "SELECT p.full_name AS player, "
            f"{_round('pit.era')} AS era "
            "FROM pitching pit JOIN players_1998 p ON pit.player_id = p.player_id "
            "WHERE (LOWER(p.first_name) LIKE '%pedro%' "
            "AND LOWER(p.last_name) LIKE '%martinez%') "
            "OR LOWER(p.full_name) LIKE '%pedro%martinez%' "
            "OR LOWER(p.full_name) LIKE '%pedro%martínez%' "
            "ORDER BY pit.era ASC LIMIT 1"
        )

    if re.search(r"\bera\b", q) and (
        "best" in q or "lowest" in q or "led" in q or "leader" in q or "who" in q or "top" in q
    ):
        m = re.search(r"top\s+(\d+)", q)
        n = int(m.group(1)) if m else 5
        return (
            "SELECT player_name AS player, era, ip FROM fangraphs_pitching "
            f"WHERE ip >= 162 ORDER BY era ASC LIMIT {n}"
        )

    # Strikeout leaders (pitching)
    if ("strikeout" in q or "struck out" in q or "strike out" in q or re.search(r"\bso\b", q)
        or "k's" in q or "ks" in q) and (
        "most" in q or "led" in q or "leader" in q or "top" in q or "who" in q
    ):
        m = re.search(r"top\s+(\d+)", q)
        n = int(m.group(1)) if m else 5
        return (
            "SELECT p.full_name AS player, SUM(pit.so) AS so "
            "FROM pitching pit JOIN players_1998 p ON pit.player_id = p.player_id "
            "GROUP BY p.player_id, p.full_name "
            "ORDER BY so DESC "
            f"LIMIT {n}"
        )

    # Wins leaders
    if ("wins" in q or re.search(r"\bwins?\b", q)) and (
        "most" in q or "led" in q or "leader" in q or "top" in q or "who" in q
    ) and "team" not in q:
        m = re.search(r"top\s+(\d+)", q)
        n = int(m.group(1)) if m else 5
        return (
            "SELECT p.full_name AS player, SUM(pit.w) AS wins "
            "FROM pitching pit JOIN players_1998 p ON pit.player_id = p.player_id "
            "GROUP BY p.player_id, p.full_name "
            "ORDER BY wins DESC "
            f"LIMIT {n}"
        )

    # Team record / Yankees (overall only; game-split questions go to game_logs)
    _split = any(
        t in q for t in (
            "one-run", "one run", "1-run", "home", "away", "road", "month",
            "against", "vs", "streak", "april", "may", "june", "july",
            "august", "september", "extra inning", "day", "night",
        )
    )
    if "yankee" in q and not _split and (
        "record" in q or "wins" in q or "losses" in q or "how many" in q
    ):
        return (
            "SELECT name AS team, wins, losses, "
            f"{_round('win_pct')} AS win_pct "
            "FROM teams WHERE LOWER(name) LIKE '%yankee%'"
        )

    if ("most wins" in q or ("wins" in q and "team" in q)) and (
        "most" in q or "led" in q or "who" in q or "which" in q
    ):
        return (
            "SELECT name AS team, wins, losses "
            "FROM teams ORDER BY wins DESC LIMIT 5"
        )

    if "standings" in q or ("division" in q and ("record" in q or "standing" in q)):
        clauses = []
        if re.search(r"\b(american league|al)\b", q):
            clauses.append("league = 'AL'")
        elif re.search(r"\b(national league|nl)\b", q):
            clauses.append("league = 'NL'")
        if "east" in q:
            clauses.append("division = 'East'")
        elif "central" in q:
            clauses.append("division = 'Central'")
        elif "west" in q:
            clauses.append("division = 'West'")
        where = ("WHERE " + " AND ".join(clauses) + " ") if clauses else ""
        return (
            "SELECT team, league, division, wins, losses, win_pct, games_back "
            f"FROM standings {where}ORDER BY league, division, wins DESC"
        )

    # Batting average leaders (batting-title qualified = 502 PA).
    if ("batting average" in q or re.search(r"\bavg\b", q) or "hit for" in q or "batting title" in q) and (
        "led" in q or "leader" in q or "highest" in q or "best" in q or "who" in q or "won" in q
    ):
        return (
            "SELECT player_name AS player, avg FROM fangraphs_batting "
            "WHERE pa >= 502 ORDER BY avg DESC LIMIT 5"
        )

    # WAR leaders (batting WAR estimate; pitchers handled via 'pitcher' phrasing)
    if "war" in q and ("led" in q or "leader" in q or "most" in q or "highest" in q or "who" in q):
        if "pitch" in q:
            return (
                "SELECT player_name AS player, war FROM fangraphs_pitching "
                "WHERE ip >= 100 ORDER BY war DESC LIMIT 5"
            )
        return (
            "SELECT player_name AS player, war FROM fangraphs_batting "
            "WHERE pa >= 300 ORDER BY war DESC LIMIT 5"
        )

    # OPS leaders (batting-title qualified)
    if "ops" in q and ("led" in q or "leader" in q or "highest" in q or "best" in q or "who" in q):
        return (
            "SELECT player_name AS player, ops FROM fangraphs_batting "
            "WHERE pa >= 502 ORDER BY ops DESC LIMIT 5"
        )

    # OBP / SLG leaders (batting-title qualified)
    if ("on-base" in q or "obp" in q or "slugging" in q or "slg" in q) and (
        "led" in q or "leader" in q or "highest" in q or "best" in q or "who" in q
    ):
        metric = "obp" if ("on-base" in q or "obp" in q) else "slg"
        return (
            f"SELECT player_name AS player, {metric} FROM fangraphs_batting "
            f"WHERE pa >= 502 ORDER BY {metric} DESC LIMIT 5"
        )

    # Win/losing streaks (game_logs.streak: MAX = longest win, MIN = longest losing).
    if "streak" in q:
        team = _extract_team_name(q)
        where = f"WHERE LOWER(team_name) LIKE '%{team}%' " if team else ""
        if "los" in q or "losing" in q or "lose" in q:
            return (
                "SELECT team_name, ABS(MIN(streak)) AS longest_losing_streak "
                f"FROM game_logs {where}GROUP BY team_name "
                "ORDER BY longest_losing_streak DESC LIMIT 5"
            )
        return (
            "SELECT team_name, MAX(streak) AS longest_win_streak "
            f"FROM game_logs {where}GROUP BY team_name "
            "ORDER BY longest_win_streak DESC LIMIT 5"
        )

    # Team pitching quality: best/worst pitching == fewest/most runs allowed.
    if ("pitching" in q or "pitching staff" in q) and ("team" in q or "which" in q or "best" in q or "worst" in q):
        worst = "worst" in q or "most" in q or "highest" in q
        order = "DESC" if worst else "ASC"
        return (
            f"SELECT name AS team, runs_allowed FROM teams ORDER BY runs_allowed {order} LIMIT 5"
        )

    # Team offense: best/worst offense == most/fewest runs scored.
    if ("offense" in q or "offence" in q or "hitting" in q) and ("team" in q or "which" in q or "best" in q or "worst" in q):
        worst = "worst" in q or "fewest" in q or "least" in q or "lowest" in q
        order = "ASC" if worst else "DESC"
        return (
            f"SELECT name AS team, runs_scored FROM teams ORDER BY runs_scored {order} LIMIT 5"
        )

    # Team runs scored / allowed
    if ("runs" in q or "scored" in q) and ("team" in q or "which" in q) and (
        "most" in q or "led" in q or "highest" in q or "fewest" in q or "least" in q
    ):
        col = "runs_allowed" if ("allowed" in q or "fewest" in q or "least" in q) else "runs_scored"
        order = "ASC" if col == "runs_allowed" and ("fewest" in q or "least" in q) else "DESC"
        if "allowed" in q and ("most" in q or "highest" in q):
            col, order = "runs_allowed", "DESC"
        if "scored" in q and ("fewest" in q or "least" in q):
            col, order = "runs_scored", "ASC"
        return (
            f"SELECT name AS team, {col} "
            f"FROM teams ORDER BY {col} {order} LIMIT 5"
        )

    # Stolen bases
    if (
        "stolen base" in q
        or "stole" in q
        or re.search(r"\bsb\b", q)
        or "steal" in q
    ) and ("most" in q or "led" in q or "leader" in q or "top" in q or "who" in q):
        m = re.search(r"top\s+(\d+)", q)
        n = int(m.group(1)) if m else 5
        return (
            "SELECT p.full_name AS player, SUM(b.sb) AS sb "
            "FROM batting b JOIN players_1998 p ON b.player_id = p.player_id "
            "GROUP BY p.player_id, p.full_name "
            "ORDER BY sb DESC "
            f"LIMIT {n}"
        )

    # Named pitcher ERA: "What was Greg Maddux's ERA"
    if re.search(r"\bera\b", q):
        m = re.search(
            r"(?:what (?:was|were)|era (?:for|of))\s+([a-zà-ÿ'.\- ]+?)(?:'s|\s+era|\s+in|\?|$)",
            q,
        )
        if not m:
            m = re.search(r"([a-zà-ÿ'.\- ]+?)(?:'s)\s+era", q)
        if m:
            name = m.group(1).strip()
            # Drop leading filler words
            name = re.sub(r"^(what was|what were|the)\s+", "", name).strip()
            if len(name) >= 4 and name not in ("the most", "home runs", "the best"):
                return (
                    "SELECT p.full_name AS player, "
                    f"{_round('pit.era')} AS era "
                    "FROM pitching pit JOIN players_1998 p ON pit.player_id = p.player_id "
                    f"WHERE LOWER(p.full_name) LIKE '%{name}%' "
                    "ORDER BY pit.era ASC LIMIT 3"
                )

    # Salary
    if "salary" in q or "paid" in q or "highest paid" in q:
        if "highest" in q or "most" in q or "top" in q:
            return (
                "SELECT p.full_name AS player, s.salary "
                "FROM salaries s JOIN players_1998 p ON s.player_id = p.player_id "
                "ORDER BY s.salary DESC LIMIT 5"
            )

    # Awards / MVP / Cy Young / Rookie of the Year / Gold Glove
    if "mvp" in q or "most valuable" in q or "cy young" in q or "rookie of the year" in q or (
        "award" in q or "gold glove" in q
    ):
        if "mvp" in q or "most valuable" in q:
            award = "Most Valuable Player"
        elif "cy young" in q:
            award = "Cy Young Award"
        elif "rookie of the year" in q:
            award = "Rookie of the Year"
        elif "gold glove" in q:
            award = "Gold Glove"
        else:
            award = "%"
        league_clause = ""
        if re.search(r"\b(american league|\bal\b)\b", q):
            league_clause = "AND a.league = 'AL' "
        elif re.search(r"\b(national league|\bnl\b)\b", q):
            league_clause = "AND a.league = 'NL' "
        return (
            "SELECT p.full_name AS player, a.award_id, a.league "
            "FROM awards a JOIN players_1998 p ON a.player_id = p.player_id "
            f"WHERE a.award_id LIKE '{award}' {league_clause}"
            "ORDER BY a.award_id, a.league"
        )

    # Multi-player stat lines / comparisons: "both A and B stats", "compare A and B".
    if ("stat" in q or "numbers" in q or "compare" in q or "both" in q) and (
        " and " in q or " vs " in q or "versus" in q or "&" in q
    ):
        names = _extract_player_names(q)
        if len(names) >= 2:
            return _multi_player_batting_sql(names)

    # Individual player season line: "give me juan gonzalez stats", "Sosa's numbers"
    name = _extract_player_name(q)
    if name and ("stat" in q or "numbers" in q or "line" in q or "average" in q):
        return _player_batting_line_sql(name)

    return None


_TEAM_NICKNAMES = (
    "yankees", "red sox", "blue jays", "orioles", "devil rays", "rays",
    "indians", "white sox", "tigers", "royals", "twins",
    "rangers", "athletics", "angels", "mariners",
    "braves", "marlins", "mets", "phillies", "expos",
    "cubs", "reds", "astros", "brewers", "pirates", "cardinals",
    "diamondbacks", "rockies", "dodgers", "padres", "giants",
)


def _extract_team_name(q: str) -> str | None:
    for nick in _TEAM_NICKNAMES:
        if nick in q:
            return nick
    return None


def _extract_player_names(q: str) -> list[str]:
    """Extract multiple player names from comparison-style questions."""
    s = q
    for lead in ("compare", "give me", "show me", "both", "stats for", "stats of"):
        s = s.replace(lead, " ")
    s = re.sub(r"\b(stats?|numbers|stat line|in 1998|1998|and rbis?|home runs?)\b", " ", s)
    # Split on connectors.
    parts = re.split(r"\s+and\s+|\s+vs\.?\s+|\s+versus\s+|&|,", s)
    names: list[str] = []
    for part in parts:
        name = part.strip(" .?'\"")
        name = re.sub(r"\s+", " ", name)
        name = re.sub(r"\s+(?:jr\.?|sr\.?|ii|iii|iv)$", "", name).strip()
        if len(name) >= 4 and " " in name and name not in _NAME_STOP:
            names.append(name)
    # Deduplicate, keep order.
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out[:4]


def _multi_player_batting_sql(names: list[str]) -> str:
    clauses = " OR ".join(
        f"LOWER(p.full_name) LIKE '%{n.replace(chr(39), chr(39) * 2)}%'" for n in names
    )
    return (
        "SELECT p.full_name AS player, SUM(b.g) AS g, SUM(b.ab) AS ab, SUM(b.r) AS r, "
        "SUM(b.h) AS h, SUM(b.hr) AS hr, SUM(b.rbi) AS rbi, SUM(b.sb) AS sb, "
        f"{_round('CAST(SUM(b.h) AS REAL) / NULLIF(SUM(b.ab), 0)')} AS avg "
        "FROM batting b JOIN players_1998 p ON b.player_id = p.player_id "
        f"WHERE {clauses} "
        "GROUP BY p.player_id, p.full_name ORDER BY hr DESC"
    )


_NAME_STOP = {
    "the",
    "most",
    "best",
    "home",
    "runs",
    "home runs",
    "what",
    "was",
    "were",
    "his",
    "her",
    "their",
    "1998",
    "mlb",
    "season",
}


def _extract_player_name(q: str) -> str | None:
    """Pull a player name from common NL phrasings."""
    patterns = (
        r"(?:give me|show me|get me|pull up|look up)\s+([a-zà-ÿ'.\- ]+?)\s+"
        r"(?:stats?|numbers|stat line|line|batting|pitching)",
        r"(?:stats?|numbers|stat line)\s+(?:for|on|of)\s+([a-zà-ÿ'.\- ]+?)(?:\s+in|\s+from|\?|$)",
        r"(?:what (?:was|were)|how did)\s+([a-zà-ÿ'.\- ]+?)(?:'s)?\s+"
        r"(?:stats?|numbers|season|year)",
        r"([a-zà-ÿ'.\- ]+?)(?:'s)\s+(?:stats?|numbers|stat line|batting line)",
        r"^(?:player\s+)?([a-zà-ÿ'.\- ]+?)\s+stats?\s*$",
    )
    for pat in patterns:
        m = re.search(pat, q)
        if not m:
            continue
        name = m.group(1).strip(" .?'\"")
        name = re.sub(r"\s+", " ", name)
        name = re.sub(r"^(?:the|a|an)\s+", "", name)
        # Lahman often omits Jr/Sr suffixes.
        name = re.sub(r"\s+(?:jr\.?|sr\.?|ii|iii|iv)$", "", name).strip()
        if len(name) >= 4 and name not in _NAME_STOP and " " in name:
            return name
        # Allow single surname if long enough (e.g. "mcgwire stats")
        if len(name) >= 5 and name not in _NAME_STOP and re.fullmatch(r"[a-zà-ÿ'.\-]+", name):
            return name
    return None


def _player_batting_line_sql(name: str) -> str:
    safe = name.replace("'", "''")
    # Match full name, or first+last when middle initials differ.
    tokens = [t for t in safe.split() if t]
    if len(tokens) >= 2:
        where = (
            f"(LOWER(p.full_name) LIKE '%{safe}%' "
            f"OR (LOWER(p.full_name) LIKE '%{tokens[0]}%' "
            f"AND LOWER(p.full_name) LIKE '%{tokens[-1]}%'))"
        )
    else:
        where = f"LOWER(p.full_name) LIKE '%{safe}%'"
    return (
        "SELECT p.full_name AS player, "
        "SUM(b.g) AS g, SUM(b.ab) AS ab, SUM(b.r) AS r, SUM(b.h) AS h, "
        "SUM(b.doubles) AS doubles, SUM(b.triples) AS triples, "
        "SUM(b.hr) AS hr, SUM(b.rbi) AS rbi, SUM(b.sb) AS sb, "
        "SUM(b.bb) AS bb, SUM(b.so) AS so, "
        f"{_round('CAST(SUM(b.h) AS REAL) / NULLIF(SUM(b.ab), 0)')} AS avg "
        "FROM batting b JOIN players_1998 p ON b.player_id = p.player_id "
        f"WHERE {where} "
        "GROUP BY p.player_id, p.full_name "
        "ORDER BY SUM(b.ab) DESC"
    )


def _clean_sql(raw: str) -> str:
    """Normalize LLM SQL output (especially verbose local models)."""
    s = raw.strip()
    # Prefer fenced SQL block if present.
    fence = re.search(r"```(?:sql)?\s*(.*?)```", s, re.I | re.S)
    if fence:
        s = fence.group(1).strip()
    else:
        s = re.sub(r"^```(?:sql)?", "", s, flags=re.I).strip()
        s = re.sub(r"```$", "", s).strip()

    # Drop leading labels like "SQL:" / "Query:"
    s = re.sub(r"^(?:sql|query)\s*:\s*", "", s, flags=re.I).strip()

    # Keep from first SELECT/WITH onward (drop prose before/after).
    m = re.search(r"(?is)\b(with|select)\b", s)
    if m:
        s = s[m.start() :]
    # Cut trailing prose after the first statement.
    if ";" in s:
        s = s.split(";", 1)[0].strip()
    return s.strip().rstrip(";")


def _validate_sql(sql: str) -> str | None:
    """Cheap pre-execution checks. Returns an error hint, or None if OK."""
    if not sql:
        return "empty query"
    if not is_read_only(sql):
        return "query must be a single read-only SELECT/WITH statement"
    # Flag obviously-unknown table-ish tokens after FROM/JOIN.
    known = known_identifiers()
    refs = re.findall(r"(?is)\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", sql)
    for ref in refs:
        if ref.lower() not in known:
            return f"unknown table '{ref}'. Use only tables listed in the schema."
    return None


class SQLAgent:
    def __init__(self, settings: Settings, llm: LLM, offline: bool) -> None:
        self.settings = settings
        self.llm = llm
        self.offline = offline

    def generate_sql(self, question: str) -> str | None:
        """Template-only path (used by callers/tests that want a single SQL string)."""
        ruled = _rule_based_sql(question)
        if ruled:
            return ruled
        if self.offline:
            return None
        sql, _result, _err = self._generate_and_run(question)
        return sql or None

    def _generate_and_run(
        self, question: str
    ) -> tuple[str, QueryResult | None, str | None]:
        """Self-correcting loop: generate SQL, execute, feed errors back and retry."""
        context = build_schema_context(self.settings)
        base_prompt = (
            f"{context}\n\n{few_shot_block()}\n\n"
            f"Now write the SQL for this question.\nQ: {question}\nSQL:"
        )
        last_sql = ""
        last_err: str | None = None
        prompt = base_prompt

        for attempt in range(_MAX_SQL_TRIES):
            raw = self.llm.complete(_SQL_SYSTEM, prompt)
            sql = _clean_sql(raw)
            last_sql = sql or last_sql

            hint = _validate_sql(sql)
            if hint:
                last_err = hint
                prompt = (
                    f"{base_prompt}\n\nYour previous attempt was invalid: {hint}\n"
                    f"Previous SQL:\n{sql}\nReturn a corrected single SELECT."
                )
                continue

            try:
                result = run_query(self.settings, sql)
            except Exception as exc:  # noqa: BLE001
                last_err = str(exc)
                prompt = (
                    f"{base_prompt}\n\nYour previous SQL raised an error when executed:\n"
                    f"{exc}\nPrevious SQL:\n{sql}\nReturn a corrected single SELECT."
                )
                continue

            # Empty result: retry once with a nudge (name/join issues are common),
            # but accept emptiness after that since some answers are legitimately none.
            if not result.rows and attempt == 0:
                last_err = "no rows returned"
                prompt = (
                    f"{base_prompt}\n\nYour previous SQL returned NO rows:\n{sql}\n"
                    "If this is due to name matching, try LOWER(full_name) LIKE '%lastname%' "
                    "against players_1998, or relax filters. If the answer really is none, "
                    "you may return the same query. Return a single SELECT."
                )
                continue

            return sql, result, None

        return last_sql, None, last_err

    def answer(self, question: str) -> SQLAnswer:
        # Deterministic templates first (instant, work offline).
        ruled = _rule_based_sql(question)
        if ruled:
            if not is_read_only(ruled):
                return SQLAnswer(sql=ruled, result=None, error="Generated SQL was not read-only.")
            try:
                result = run_query(self.settings, ruled)
                # Trust non-empty template results. If a template returns nothing
                # (often a name-match miss), let the generative loop try instead.
                if result.rows or self.offline:
                    return SQLAnswer(sql=ruled, result=result)
            except Exception as exc:  # noqa: BLE001
                # Fall through to the generative loop if a template misfires.
                if self.offline:
                    return SQLAnswer(sql=ruled, result=None, error=str(exc))

        if self.offline:
            return SQLAnswer(
                sql="",
                result=None,
                error=(
                    "I don't have a built-in template for that question, and no "
                    "generative model is enabled. Set INSIGHTRAG_LLM_PROVIDER=ollama "
                    "(free/local) or openai, set INSIGHTRAG_OFFLINE=false, and restart "
                    "the UI — or try a common question like home-run leaders, ERA "
                    "leaders, or team records."
                ),
            )

        sql, result, err = self._generate_and_run(question)
        if result is not None:
            return SQLAnswer(sql=sql, result=result)
        return SQLAnswer(sql=sql, result=None, error=err or "Could not translate question to SQL.")
