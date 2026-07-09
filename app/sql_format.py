"""Natural-language formatting for SQL result sets."""

from __future__ import annotations

import re


def _fmt_int(value) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_rate(value, decimals: int = 3) -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{num:.{decimals}f}"


def _fmt_era(value) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_ip(value) -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(num - round(num)) < 1e-6:
        return f"{int(round(num))}"
    return f"{num:.1f}"


def verbalize_sql(columns: list[str], rows: list[list]) -> str:
    if not rows:
        return "The query returned no rows."

    cols = [c.lower() for c in columns]

    # Full batting line(s): player + g/ab/h/hr/rbi/...
    batting_keys = {"g", "ab", "h", "hr", "rbi"}
    if (
        len(rows) >= 1
        and re.search(r"(name|player|batter)", cols[0])
        and batting_keys.issubset(set(cols))
        and len(columns) >= 6
    ):
        def _line(row) -> str:
            by = {c: row[i] for i, c in enumerate(cols)}
            parts: list[str] = []
            for key, label in (
                ("g", "G"), ("ab", "AB"), ("r", "R"), ("h", "H"),
                ("hr", "HR"), ("rbi", "RBI"), ("sb", "SB"), ("bb", "BB"), ("so", "SO"),
            ):
                val = by.get(key)
                if val is not None:
                    parts.append(f"{_fmt_int(val)} {label}")
            avg = by.get("avg")
            if avg is not None:
                try:
                    avg_f = float(avg)
                    avg_disp = f"{avg_f:.3f}".lstrip("0") if avg_f < 1 else _fmt_rate(avg)
                except (TypeError, ValueError):
                    avg_disp = str(avg)
                parts.append(f"{avg_disp} AVG")
            return ", ".join(parts)

        # Single match -> one sentence. Multiple matches -> show up to 3 lines
        # (covers comparisons like "compare A and B" and multi-name lookups).
        if len(rows) == 1:
            return f"{str(rows[0][0])}'s 1998 season: {_line(rows[0])}."
        shown = rows[:3]
        out = [f"{str(r[0])}: {_line(r)}" for r in shown]
        text = "\n".join(out)
        if len(rows) > 3:
            text += f"\n(+{len(rows) - 3} more matched)"
        return text

    # Single-player / single-team fact: player + one metric
    if len(rows) == 1 and len(columns) == 2 and re.search(
        r"(name|player|batter|pitcher|team)", cols[0]
    ):
        who = str(rows[0][0])
        val = rows[0][1]
        metric = cols[1]
        if re.search(r"\b(hr|home[_ ]?runs)\b", metric):
            return f"{who} hit {_fmt_int(val)} home runs in 1998."
        if re.search(r"\b(era)\b", metric):
            return f"{who}'s ERA in 1998 was {_fmt_era(val)}."
        if re.search(r"\b(rbi)\b", metric):
            return f"{who} had {_fmt_int(val)} RBIs in 1998."
        if re.search(r"\b(wins?)\b", metric) and len(columns) == 2:
            return f"{who} had {_fmt_int(val)} wins in 1998."
        if re.search(r"\b(avg|obp|slg|ops|woba)\b", metric):
            return f"{who}'s {columns[1].upper()} in 1998 was {_fmt_rate(val)}."
        if re.search(r"\b(war)\b", metric):
            return f"{who}'s WAR in 1998 was {_fmt_rate(val, decimals=1)}."
        if "win_streak" in metric or "winning_streak" in metric:
            return f"The {who}'s longest winning streak in 1998 was {_fmt_int(val)} games."
        if "losing_streak" in metric or "loss_streak" in metric:
            return f"The {who}'s longest losing streak in 1998 was {_fmt_int(val)} games."
        return f"{who}: {columns[1].replace('_', ' ')} = {val}."

    # Team record: team, wins, losses [, win_pct]
    if len(rows) == 1 and {"team", "wins", "losses"}.issubset(set(cols)):
        row = rows[0]
        team = row[cols.index("team")]
        w = _fmt_int(row[cols.index("wins")])
        ls = _fmt_int(row[cols.index("losses")])
        if "win_pct" in cols:
            pct = _fmt_rate(row[cols.index("win_pct")], decimals=3)
            return f"The {team} went {w}-{ls} ({pct}) in 1998."
        return f"The {team} went {w}-{ls} in 1998."

    # Win-loss record: exactly a wins + losses pair (e.g., one-run/home splits).
    if len(rows) == 1 and len(columns) == 2 and any("win" in c for c in cols) and any(
        "loss" in c or "lose" in c for c in cols
    ):
        wi = next(i for i, c in enumerate(cols) if "win" in c)
        li = next(i for i, c in enumerate(cols) if "loss" in c or "lose" in c)
        w = _fmt_int(rows[0][wi])
        ls = _fmt_int(rows[0][li])
        return f"{w}-{ls}."

    if len(rows) == 1 and len(columns) == 1:
        val = rows[0][0]
        col = cols[0]
        if re.search(r"\b(hr|home[_ ]?runs)\b", col):
            return f"{_fmt_int(val)} home runs."
        if re.search(r"\b(rbi)\b", col):
            return f"{_fmt_int(val)} RBIs."
        if re.search(r"\b(so|strikeouts?)\b", col):
            return f"{_fmt_int(val)} strikeouts."
        if re.search(r"\b(wins?|losses?)\b", col):
            label = "wins" if "win" in col else "losses"
            return f"{_fmt_int(val)} {label}."
        if re.search(r"\b(era)\b", col):
            return f"ERA is {_fmt_era(val)}."
        if re.search(r"\b(avg|obp|slg|ops|woba)\b", col):
            return f"{columns[0].upper()} is {_fmt_rate(val)}."
        if re.search(r"\b(war)\b", col):
            return f"WAR is {_fmt_rate(val, decimals=1)}."
        return f"{columns[0].replace('_', ' ')} is {val}."

    # Standings: (team, wins, losses, win_pct) — check before generic leaderboard.
    if {"team", "wins", "losses"}.issubset(set(cols)):
        idx_team = cols.index("team")
        idx_w = cols.index("wins")
        idx_l = cols.index("losses")
        idx_pct = cols.index("win_pct") if "win_pct" in cols else None
        idx_gb = cols.index("games_back") if "games_back" in cols else None
        lines = ["Standings:"]
        for row in rows[:15]:
            team = row[idx_team]
            w = _fmt_int(row[idx_w])
            l = _fmt_int(row[idx_l])
            piece = f"• {team}: {w}-{l}"
            if idx_pct is not None:
                piece += f" ({_fmt_rate(row[idx_pct], decimals=3)})"
            if idx_gb is not None and str(row[idx_gb]) not in ("", "-", "None"):
                piece += f", {row[idx_gb]} GB"
            lines.append(piece)
        return "\n".join(lines)

    # Leaderboards: (player/team, metric)
    if len(cols) >= 2 and re.search(r"(name|player|batter|pitcher|team)", cols[0]):
        metric = columns[1]
        metric_l = cols[1]
        title_metric = metric.replace("_", " ").upper() if metric.islower() else metric
        lines = [f"Top results by {title_metric}:"]
        for i, row in enumerate(rows[:10], start=1):
            who = str(row[0])
            val = row[1]
            if re.search(r"\b(era)\b", metric_l):
                lines.append(f"{i}. {who} — {_fmt_era(val)}")
            elif re.search(r"\b(avg|obp|slg|ops|woba)\b", metric_l):
                lines.append(f"{i}. {who} — {_fmt_rate(val)}")
            elif re.search(r"\b(war)\b", metric_l):
                lines.append(f"{i}. {who} — {_fmt_rate(val, decimals=1)} WAR")
            elif re.search(r"\b(salary)\b", metric_l):
                lines.append(f"{i}. {who} — ${_fmt_int(val)}")
            else:
                lines.append(f"{i}. {who} — {val}")
        return "\n".join(lines)

    lines = ["Results:"]
    for row in rows[:5]:
        parts = []
        for col, val in zip(columns, row, strict=False):
            col_l = col.lower()
            if re.search(r"\b(era)\b", col_l):
                parts.append(f"{col}={_fmt_era(val)}")
            elif re.search(r"\b(avg|obp|slg|ops|woba)\b", col_l):
                parts.append(f"{col}={_fmt_rate(val)}")
            elif re.search(r"\b(war)\b", col_l):
                parts.append(f"{col}={_fmt_rate(val, decimals=1)}")
            elif re.search(r"\b(ip)\b", col_l):
                parts.append(f"{col}={_fmt_ip(val)}")
            elif isinstance(val, (int, float)) and re.search(r"\b(count|wins|losses|hr|rbi|so)\b", col_l):
                parts.append(f"{col}={_fmt_int(val)}")
            else:
                parts.append(f"{col}={val}")
        lines.append(f"• {', '.join(parts)}")
    return "\n".join(lines)
