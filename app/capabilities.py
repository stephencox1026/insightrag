"""Meta / capabilities answers — what the assistant knows and can do."""

from __future__ import annotations

import re

from .config import Settings
from .db import index_ready, warehouse_ready
from .warehouse import run_query

_META_PATTERNS = (
    r"\bwhat (data|information) (do you|can you) (have|access)\b",
    r"\bwhat can you (help|do)\b",
    r"\bwhat (documents|docs|files) (do you|are)\b",
    r"\bwhat tables\b",
    r"\bwhat do you know\b",
    r"\bwhat sources\b",
    r"\bcapabilities\b",
    r"\bwhat is (this|insightrag|mlb)\b",
    r"\bwhat level(s)? of data\b",
    r"\bwhat (level|grain|granularity)\b",
    r"\bdata (coverage|granularity|levels?|grain)\b",
    r"\bgame[- ]level\b",
    r"\bhow (deep|detailed) (is|are)\b",
)


def _count(settings: Settings, table: str) -> int:
    try:
        return int(run_query(settings, f"SELECT COUNT(*) FROM {table}").rows[0][0])
    except Exception:  # noqa: BLE001
        return 0


def data_coverage(settings: Settings) -> str:
    """Human-readable breakdown of available data organized by grain/level."""
    c = {
        t: _count(settings, t)
        for t in (
            "teams", "standings", "batting", "pitching", "fielding",
            "salaries", "awards", "all_stars", "fangraphs_batting",
            "fangraphs_pitching", "game_logs", "players_1998",
        )
    }
    lines = ["**1998 MLB data — available by level:**", ""]

    lines.append("**League / season level**")
    lines.append(f"- Final standings by league & division, with games-back ({c['standings']} team rows)")
    lines.append("")

    lines.append("**Team-season level**")
    lines.append(f"- Win-loss records, runs scored/allowed, attendance, ballpark ({c['teams']} teams)")
    lines.append("")

    lines.append("**Player-season level**")
    lines.append(f"- Batting ({c['batting']} stint rows, {c['players_1998']} players)")
    lines.append(f"- Pitching ({c['pitching']} rows) · Fielding ({c['fielding']} rows)")
    lines.append(f"- Salaries ({c['salaries']}) · Awards ({c['awards']}) · All-Stars ({c['all_stars']})")
    lines.append(
        f"- Advanced metrics — OBP/SLG/OPS/wOBA + WAR/wRC+ estimates "
        f"({c['fangraphs_batting']} batters, {c['fangraphs_pitching']} pitchers)"
    )
    lines.append("")

    lines.append("**Game level**")
    if c["game_logs"]:
        lines.append(
            f"- Game-by-game results ({c['game_logs']} team-games): dates, scores, "
            "home/away, win/loss streaks"
        )
    else:
        lines.append("- Game-by-game results: not loaded yet (season/aggregate data only)")
    lines.append("")

    lines.append("**Reference docs**")
    lines.append("- Stat definitions, qualification rules, 1998 season overview")
    lines.append("")

    lines.append(
        "_Not available: pitch-by-pitch/Statcast, minor leagues, in-season transactions._"
    )
    return "\n".join(lines)


def match_meta_intent(question: str) -> bool:
    q = question.lower().strip()
    return any(re.search(p, q) for p in _META_PATTERNS)


_COVERAGE_PATTERNS = (
    r"\blevel(s)? of data\b",
    r"\b(level|grain|granularity)\b",
    r"\bdata (coverage|granularity|levels?|grain)\b",
    r"\bgame[- ]level\b",
    r"\bhow (deep|detailed)\b",
    r"\bwhat (data|information) (do you|can you) (have|access)\b",
)


def capabilities_answer(question: str, settings: Settings) -> str:
    index_ok = index_ready(settings)
    warehouse_ok = warehouse_ready(settings)

    if not index_ok and not warehouse_ok:
        return (
            "No data is loaded yet. Run `make demo` or `make demo-docker` "
            "from the project folder, then try again."
        )

    # Detailed data-coverage breakdown when the user asks about levels/grain.
    q = question.lower()
    if warehouse_ok and any(re.search(p, q) for p in _COVERAGE_PATTERNS):
        return data_coverage(settings)

    parts = [
        "I'm a 1998 MLB season assistant. I can answer baseball questions from reference documents "
        "and run read-only SQL over 1998 player and team statistics."
    ]

    if index_ok:
        parts.append(
            "Documents cover stat definitions (ERA/OPS/WAR), 1998 season context, and data catalog notes."
        )
    if warehouse_ok:
        parts.append(
            "SQL queries cover batting, pitching, fielding, standings, salaries, awards, and FanGraphs metrics."
        )

    parts.append(
        'Example: "Who hit the most home runs in 1998?" or '
        '"What was Pedro Martínez\'s ERA in 1998?"'
    )
    return "\n\n".join(parts)
