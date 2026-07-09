"""Lightweight query router: decide whether a question needs documents, the
SQL warehouse, or both.

This is intentionally rule-based for the MVP. The production tier replaces it
with a LangGraph planner agent that makes the same routing decision with an LLM.
"""

from __future__ import annotations

import re
from enum import StrEnum

# Terms that clearly belong to the documentation domain. If present, we route to
# docs even when a generic counting phrase ("how many") is also present, because
# those phrases otherwise pull policy questions toward the SQL path.
DOC_OVERRIDE = (
    "definition",
    "define",
    "how is",
    "how do you calculate",
    "calculated",
    "formula",
    "what does",
    "what is",
    "qualify",
    "qualification",
    "batting title",
    "rule",
)

SQL_SIGNALS = (
    "how many",
    "number of",
    "count",
    "total",
    "average",
    "top ",
    "leader",
    "leaders",
    "most",
    "least",
    "player",
    "pitcher",
    "batter",
    "team",
    "division",
    "standings",
    "record",
    "wins",
    "losses",
    "home run",
    "home runs",
    "hr",
    "rbi",
    "batting average",
    "avg",
    "obp",
    "slg",
    "ops",
    "era",
    "strikeout",
    "strikeouts",
    "so",
    "war",
    "woba",
    "wrc+",
    "fip",
    "salary",
    "all-star",
    "award",
    "mvp",
    "cy young",
    "gold glove",
    "rookie of the year",
    # Individual player lookups: "give me juan gonzalez stats"
    "stats",
    "stat line",
    "numbers",
    "season stats",
    "give me",
    "show me",
    # Broader stat phrasings
    "batted",
    "batting",
    "hitter",
    "hitters",
    "qualified",
    "compare",
    "versus",
    " vs ",
    "per game",
    "streak",
    "record",
    "runs per",
    "attendance",
    "payroll",
    "youngest",
    "oldest",
    "how much",
    "runs allowed",
    "runs scored",
    "on-base",
    "slugging",
    "whip",
    "saves",
    "innings",
)

# Specific (non-generic) doc signals used to detect HYBRID questions.
DOC_SIGNALS = (
    "definition",
    "define",
    "calculated",
    "formula",
    "qualify",
    "batting title",
    "rule",
)


class Route(StrEnum):
    DOCS = "docs"
    SQL = "sql"
    HYBRID = "hybrid"


def route_query(question: str) -> Route:
    q = question.lower()

    has_sql = any(s in q for s in SQL_SIGNALS)
    # Numeric stat cues, e.g. ".250", "under .3", "over 40", "at least 100".
    if re.search(r"\.\d{2,3}\b", q) or re.search(r"\b(under|over|above|below|at least|more than|fewer than)\s+[.\d]", q):
        has_sql = True
    has_doc = any(s in q for s in DOC_SIGNALS)
    wants_entity = any(t in q for t in ("who", "led", "highest", "most", "top ", "best", "rank"))

    # A strong documentation term wins unless the question also asks for a
    # concrete metric (revenue/count/etc.) -> then it's genuinely hybrid.
    if any(t in q for t in DOC_OVERRIDE):
        # "What is ERA?" should stay DOCS, but "What is WAR and who led..." is HYBRID.
        return Route.HYBRID if (has_sql and wants_entity) else Route.DOCS

    if has_sql and has_doc:
        return Route.HYBRID
    if has_sql:
        return Route.SQL
    return Route.DOCS
