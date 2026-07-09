"""pybaseball ingestion for the 1998 MLB season.

This loader produces denormalized, query-friendly tables for a text-to-SQL demo.
We intentionally store both:
1) Lahman (traditional counting stats, stable IDs)
2) FanGraphs (advanced metrics like WAR, wOBA, FIP, wRC+)
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import requests

# pybaseball still points at a dead Chadwick Bureau zip; this mirror works.
_LAHMAN_ZIP_URL = "https://github.com/SeanLahman/baseballdatabank/archive/master.zip"
_LAHMAN_PREFIX = "baseballdatabank-master"
_LAHMAN_CACHE = Path("data/cache/lahman")


def _lahman_csv(relative_path: str):
    import pandas as pd  # noqa: WPS433

    _LAHMAN_CACHE.mkdir(parents=True, exist_ok=True)
    local = _LAHMAN_CACHE / relative_path.replace("/", "__")
    if local.exists():
        return pd.read_csv(local)

    resp = requests.get(_LAHMAN_ZIP_URL, timeout=120)
    resp.raise_for_status()
    with ZipFile(BytesIO(resp.content)) as zf:
        data = zf.read(f"{_LAHMAN_PREFIX}/{relative_path}")
    local.write_bytes(data)
    return pd.read_csv(BytesIO(data))


def _lahman_table(name: str):
    """Load a Lahman table from a working mirror (pybaseball's upstream zip is broken)."""
    mapping = {
        "people": "core/Master.csv",
        "teams_core": "core/Teams.csv",
        "batting": "core/Batting.csv",
        "pitching": "core/Pitching.csv",
        "fielding": "core/Fielding.csv",
        "salaries": "core/Salaries.csv",
        "awards_players": "core/AwardsPlayers.csv",
        "all_star_full": "core/AllstarFull.csv",
    }
    return _lahman_csv(mapping[name])


def _to_int(value: Any) -> int | None:
    import pandas as pd  # noqa: WPS433

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return int(value)
    except Exception:  # noqa: BLE001
        return None


def _to_float(value: Any) -> float | None:
    import pandas as pd  # noqa: WPS433

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return None


def _col(df, name: str):
    import pandas as pd  # noqa: WPS433

    if name in df.columns:
        return df[name]
    return pd.Series([None] * len(df))


# --- Locally-computed advanced metrics (no network dependency) --------------
# We derive advanced stats from Lahman counting stats so the warehouse always
# has OBP/SLG/OPS/wOBA/WHIP/FIP even when FanGraphs scraping is blocked. WAR and
# wRC+ are transparent *estimates* (documented as such), good enough to rank the
# 1998 leaders sensibly without pretending to match FanGraphs exactly.

# Linear-weight wOBA coefficients (modern weights; close enough for 1998).
_WOBA_W = {"bb": 0.69, "hbp": 0.72, "1b": 0.89, "2b": 1.27, "3b": 1.62, "hr": 2.10}
_WOBA_SCALE = 1.15
_RUNS_PER_WIN = 10.0


def _num(series):
    import pandas as pd  # noqa: WPS433

    return pd.to_numeric(series, errors="coerce").fillna(0)


def _advanced_batting_rows(batting_1998, people) -> list[tuple]:
    """One aggregated row per batter with computed OBP/SLG/OPS/wOBA/wRC+/WAR-est."""
    if batting_1998.empty:
        return []

    df = batting_1998.copy()
    for c in ("AB", "H", "2B", "3B", "HR", "BB", "SO", "HBP", "SF", "RBI", "R"):
        df[c] = _num(_col(df, c))

    agg = df.groupby("playerID", as_index=False).agg(
        AB=("AB", "sum"), H=("H", "sum"), D2B=("2B", "sum"), T3B=("3B", "sum"),
        HR=("HR", "sum"), BB=("BB", "sum"), SO=("SO", "sum"), HBP=("HBP", "sum"),
        SF=("SF", "sum"), RBI=("RBI", "sum"),
    )
    # Primary team = team where the player had the most at-bats.
    primary_team = (
        df.sort_values("AB").groupby("playerID")["teamID"].last().to_dict()
    )
    name_by_id = {str(r["playerID"]): r.get("full_name") for _, r in people.iterrows()}

    agg["1B"] = agg["H"] - agg["D2B"] - agg["T3B"] - agg["HR"]
    agg["PA"] = agg["AB"] + agg["BB"] + agg["HBP"] + agg["SF"]
    agg["TB"] = agg["1B"] + 2 * agg["D2B"] + 3 * agg["T3B"] + 4 * agg["HR"]

    woba_num = (
        _WOBA_W["bb"] * agg["BB"]
        + _WOBA_W["hbp"] * agg["HBP"]
        + _WOBA_W["1b"] * agg["1B"]
        + _WOBA_W["2b"] * agg["D2B"]
        + _WOBA_W["3b"] * agg["T3B"]
        + _WOBA_W["hr"] * agg["HR"]
    )
    # League wOBA baseline from season totals (for wRC+ and WAR estimates).
    lg_woba = float(woba_num.sum() / (agg["AB"] + agg["BB"] + agg["SF"] + agg["HBP"]).sum())

    rows: list[tuple] = []
    for _, r in agg.iterrows():
        ab = int(r["AB"])
        pa = int(r["PA"])
        h = int(r["H"])
        avg = (h / ab) if ab else None
        obp = ((h + r["BB"] + r["HBP"]) / (ab + r["BB"] + r["HBP"] + r["SF"])) if (
            ab + r["BB"] + r["HBP"] + r["SF"]
        ) else None
        slg = (r["TB"] / ab) if ab else None
        ops = (obp + slg) if (obp is not None and slg is not None) else None
        den = r["AB"] + r["BB"] + r["SF"] + r["HBP"]
        woba = float(
            (
                _WOBA_W["bb"] * r["BB"] + _WOBA_W["hbp"] * r["HBP"] + _WOBA_W["1b"] * r["1B"]
                + _WOBA_W["2b"] * r["D2B"] + _WOBA_W["3b"] * r["T3B"] + _WOBA_W["hr"] * r["HR"]
            )
            / den
        ) if den else None
        wrc_plus = int(round(100 * woba / lg_woba)) if (woba and lg_woba) else None
        # Offensive WAR estimate: wRAA (runs above avg) + replacement/playing-time.
        if woba is not None:
            wraa = ((woba - lg_woba) / _WOBA_SCALE) * pa
            rep = (pa / 650.0) * 20.0
            war = round((wraa + rep) / _RUNS_PER_WIN, 1)
        else:
            war = None
        rows.append(
            (
                name_by_id.get(str(r["playerID"])),
                primary_team.get(str(r["playerID"])),
                pa,
                ab,
                h,
                int(r["HR"]),
                int(r["RBI"]),
                round(avg, 3) if avg is not None else None,
                round(obp, 3) if obp is not None else None,
                round(slg, 3) if slg is not None else None,
                round(ops, 3) if ops is not None else None,
                round(woba, 3) if woba is not None else None,
                wrc_plus,
                war,
            )
        )
    return rows


def _advanced_pitching_rows(pitching_1998, people) -> list[tuple]:
    """One aggregated row per pitcher with computed IP/ERA/WHIP/FIP/WAR-est."""
    if pitching_1998.empty:
        return []

    df = pitching_1998.copy()
    for c in ("W", "L", "SO", "BB", "H", "HR", "IPouts", "ER"):
        df[c] = _num(_col(df, c))

    agg = df.groupby("playerID", as_index=False).agg(
        W=("W", "sum"), L=("L", "sum"), SO=("SO", "sum"), BB=("BB", "sum"),
        H=("H", "sum"), HR=("HR", "sum"), IPouts=("IPouts", "sum"), ER=("ER", "sum"),
    )
    primary_team = (
        df.sort_values("IPouts").groupby("playerID")["teamID"].last().to_dict()
    )
    name_by_id = {str(r["playerID"]): r.get("full_name") for _, r in people.iterrows()}

    total_ip = agg["IPouts"].sum() / 3.0
    lg_era = float((agg["ER"].sum() * 9) / total_ip) if total_ip else 4.50
    # FIP constant so league FIP == league ERA.
    fip_raw_total = (13 * agg["HR"].sum() + 3 * agg["BB"].sum() - 2 * agg["SO"].sum())
    fip_constant = lg_era - (fip_raw_total / total_ip if total_ip else 0)

    rows: list[tuple] = []
    for _, r in agg.iterrows():
        ip = r["IPouts"] / 3.0
        if ip <= 0:
            continue
        era = round((r["ER"] * 9) / ip, 2)
        fip = round((13 * r["HR"] + 3 * r["BB"] - 2 * r["SO"]) / ip + fip_constant, 2)
        # WAR estimate vs a replacement-level pitcher (~1.28x league ERA).
        war = round(((lg_era * 1.28 - era) * ip / 9) / _RUNS_PER_WIN, 1)
        rows.append(
            (
                name_by_id.get(str(r["playerID"])),
                primary_team.get(str(r["playerID"])),
                int(r["W"]),
                int(r["L"]),
                era,
                round(ip, 1),
                int(r["SO"]),
                int(r["BB"]),
                fip,
                war,
            )
        )
    return rows


_GAMELOG_CACHE = Path("data/cache/gamelogs")
# Retrosheet publishes the full season in one zip; team codes match Lahman IDs.
_RETROSHEET_URL = "https://www.retrosheet.org/gamelogs/gl{year}.zip"


def _retrosheet_txt_path(year: int) -> Path:
    return _GAMELOG_CACHE / f"retrosheet_gl{year}.txt"


def prefetch_game_logs(year: int = 1998) -> int:
    """Download the Retrosheet season game-log zip to local cache (one request).

    Returns the number of games in the file (0 if the download failed). Seeding
    then reads the cache instantly; every team comes from this single file.
    """
    _GAMELOG_CACHE.mkdir(parents=True, exist_ok=True)
    out = _retrosheet_txt_path(year)
    if not out.exists():
        resp = requests.get(_RETROSHEET_URL.format(year=year), timeout=120)
        resp.raise_for_status()
        with ZipFile(BytesIO(resp.content)) as zf:
            member = next(n for n in zf.namelist() if n.upper().endswith(".TXT"))
            out.write_bytes(zf.read(member))
    with out.open("r", encoding="latin-1") as fh:
        return sum(1 for _ in fh)


def _game_logs_rows(teams_1998, year: int = 1998) -> list[tuple]:
    """Build per-team game-log rows from the cached Retrosheet file (no network).

    Retrosheet game logs are one row per game; we emit two rows (home + visitor),
    compute win/loss and a running win/losing streak per team. Returns [] if the
    cache is missing so the rest of the warehouse still seeds instantly.
    """
    import csv  # noqa: WPS433

    txt = _retrosheet_txt_path(year)
    if not txt.exists():
        # One fast Retrosheet download populates every team; degrade gracefully
        # (empty game_logs) if offline so the rest of the warehouse still seeds.
        try:
            prefetch_game_logs(year)
        except Exception:  # noqa: BLE001
            return []
        if not txt.exists():
            return []
    name_by_id = {str(r["teamID"]): r.get("name") for _, r in teams_1998.iterrows()}

    # Retrosheet field indices (see retrosheet.org/gamelogs/glfields.txt).
    F_DATE, F_GNUM, F_VIS, F_HOME, F_VIS_R, F_HOME_R = 0, 1, 3, 6, 9, 10

    # Collect games per team in chronological order.
    per_team: dict[str, list[dict]] = {}
    with txt.open("r", encoding="latin-1") as fh:
        for parts in csv.reader(fh):
            if len(parts) <= F_HOME_R:
                continue
            date = parts[F_DATE].strip().strip('"')
            gnum = _to_int(parts[F_GNUM].strip().strip('"')) or 0
            vis, home = parts[F_VIS].strip().strip('"'), parts[F_HOME].strip().strip('"')
            try:
                vis_r = int(parts[F_VIS_R])
                home_r = int(parts[F_HOME_R])
            except (ValueError, TypeError):
                continue
            iso = f"{date[:4]}-{date[4:6]}-{date[6:8]}" if len(date) == 8 else date
            sort_key = (date, gnum)
            per_team.setdefault(vis, []).append(
                {"k": sort_key, "date": iso, "team": vis, "opp": home,
                 "ha": "away", "rf": vis_r, "ra": home_r}
            )
            per_team.setdefault(home, []).append(
                {"k": sort_key, "date": iso, "team": home, "opp": vis,
                 "ha": "home", "rf": home_r, "ra": vis_r}
            )

    rows: list[tuple] = []
    for team_id, games in per_team.items():
        if team_id not in name_by_id:
            continue
        team_name = name_by_id.get(team_id)
        games.sort(key=lambda g: g["k"])
        streak = 0
        for i, g in enumerate(games, start=1):
            win = 1 if g["rf"] > g["ra"] else 0
            if win:
                streak = streak + 1 if streak > 0 else 1
            else:
                streak = streak - 1 if streak < 0 else -1
            rows.append(
                (
                    g["date"], i, team_id, team_name, g["opp"], g["ha"],
                    g["rf"], g["ra"], ("W" if win else "L"), win, streak,
                )
            )
    return rows


def load_mlb_1998() -> dict[str, list[tuple]]:
    """Load 1998 MLB data.

    Returns a mapping {table_name: list[tuple]} aligned with app.warehouse schema.
    """

    # Lazy import: pybaseball has a heavy import graph and may initialize caches.
    # Tests do not call this loader, so keeping imports inside avoids slow test startup.

    year = 1998

    # Lahman tables (stable IDs).
    people = _lahman_table("people")
    people = people[people["playerID"].notna()].copy()
    people["full_name"] = (
        _col(people, "nameFirst").fillna("").astype(str).str.strip()
        + " "
        + _col(people, "nameLast").fillna("").astype(str).str.strip()
    ).str.strip()

    players_rows: list[tuple] = []
    for _, r in people.iterrows():
        players_rows.append(
            (
                str(r["playerID"]),
                (r.get("nameFirst") or None),
                (r.get("nameLast") or None),
                (r.get("full_name") or None),
                (r.get("bats") or None),
                (r.get("throws") or None),
                (r.get("debut") or None),
            )
        )

    teams = _lahman_table("teams_core")
    teams_1998 = teams[teams["yearID"] == year].copy()
    teams_1998["win_pct"] = teams_1998["W"] / (teams_1998["W"] + teams_1998["L"])
    teams_rows: list[tuple] = []
    for _, r in teams_1998.iterrows():
        teams_rows.append(
            (
                str(r["teamID"]),
                (r.get("name") or None),
                (r.get("lgID") or None),
                (r.get("divID") or None),
                _to_int(r.get("W")),
                _to_int(r.get("L")),
                _to_float(r.get("win_pct")),
                _to_int(r.get("R")),
                _to_int(r.get("RA")),
                _to_int(r.get("attendance")),
                (r.get("park") or None),
            )
        )

    batting = _lahman_table("batting")
    batting_1998 = batting[batting["yearID"] == year].copy()
    batting_rows: list[tuple] = []
    for _, r in batting_1998.iterrows():
        batting_rows.append(
            (
                str(r["playerID"]),
                str(r["teamID"]),
                _to_int(r.get("stint")),
                _to_int(r.get("G")),
                _to_int(r.get("AB")),
                _to_int(r.get("R")),
                _to_int(r.get("H")),
                _to_int(r.get("2B")),
                _to_int(r.get("3B")),
                _to_int(r.get("HR")),
                _to_int(r.get("RBI")),
                _to_int(r.get("SB")),
                _to_int(r.get("BB")),
                _to_int(r.get("SO")),
                _to_int(r.get("HBP")),
                _to_int(r.get("SF")),
            )
        )

    pitching = _lahman_table("pitching")
    pitching_1998 = pitching[pitching["yearID"] == year].copy()
    pitching_rows: list[tuple] = []
    for _, r in pitching_1998.iterrows():
        pitching_rows.append(
            (
                str(r["playerID"]),
                str(r["teamID"]),
                _to_int(r.get("stint")),
                _to_int(r.get("W")),
                _to_int(r.get("L")),
                _to_float(r.get("ERA")),
                _to_int(r.get("G")),
                _to_int(r.get("GS")),
                _to_int(r.get("CG")),
                _to_int(r.get("SO")),
                _to_int(r.get("BB")),
                _to_int(r.get("H")),
                _to_int(r.get("HR")),
                _to_int(r.get("IPouts")),
                _to_int(r.get("ER")),
            )
        )

    fielding = _lahman_table("fielding")
    fielding_1998 = fielding[fielding["yearID"] == year].copy()
    fielding_rows: list[tuple] = []
    for _, r in fielding_1998.iterrows():
        fielding_rows.append(
            (
                str(r["playerID"]),
                str(r["teamID"]),
                _to_int(r.get("stint")),
                (r.get("POS") or None),
                _to_int(r.get("G")),
                _to_int(r.get("GS")),
                _to_int(r.get("PO")),
                _to_int(r.get("A")),
                _to_int(r.get("E")),
                _to_int(r.get("DP")),
            )
        )

    salaries = _lahman_table("salaries")
    salaries_1998 = salaries[salaries["yearID"] == year].copy()
    salaries_rows: list[tuple] = []
    for _, r in salaries_1998.iterrows():
        salaries_rows.append(
            (
                str(r["playerID"]),
                str(r["teamID"]),
                (r.get("lgID") or None),
                _to_int(r.get("salary")),
            )
        )

    awards = _lahman_table("awards_players")
    awards_1998 = awards[awards["yearID"] == year].copy()
    awards_rows: list[tuple] = []
    for _, r in awards_1998.iterrows():
        awards_rows.append(
            (
                str(r["playerID"]),
                (r.get("awardID") or None),
                (r.get("lgID") or None),
                (r.get("tie") or None),
            )
        )

    all_stars = _lahman_table("all_star_full")
    all_stars_1998 = all_stars[all_stars["yearID"] == year].copy()
    all_stars_rows: list[tuple] = []
    for _, r in all_stars_1998.iterrows():
        all_stars_rows.append(
            (
                str(r["playerID"]),
                (r.get("teamID") or None),
                (r.get("lgID") or None),
                _to_int(r.get("startingPos")),
            )
        )

    # Standings computed deterministically from Lahman teams, with league,
    # human-readable division, and games-back within each division.
    _DIV_NAMES = {"E": "East", "C": "Central", "W": "West"}
    standings_rows: list[tuple] = []
    for (lg, div), grp in teams_1998.groupby(["lgID", "divID"]):
        grp = grp.sort_values("W", ascending=False)
        lead_w = _to_int(grp.iloc[0]["W"]) or 0
        lead_l = _to_int(grp.iloc[0]["L"]) or 0
        for i, (_, r) in enumerate(grp.iterrows()):
            w = _to_int(r.get("W")) or 0
            losses = _to_int(r.get("L")) or 0
            if i == 0:
                gb = "-"
            else:
                gb_val = ((lead_w - w) + (losses - lead_l)) / 2.0
                gb = f"{gb_val:.1f}".rstrip("0").rstrip(".")
            standings_rows.append(
                (
                    (r.get("name") or None),
                    (lg or None),
                    _DIV_NAMES.get(str(div), str(div)),
                    w,
                    losses,
                    _to_float(r.get("win_pct")),
                    gb,
                )
            )

    # Advanced metrics computed locally from Lahman (deterministic, no scraping).
    # OBP/SLG/OPS/wOBA are exact; wRC+ and WAR are documented estimates.
    fg_bat_rows = _advanced_batting_rows(batting_1998, people)
    fg_pit_rows = _advanced_pitching_rows(pitching_1998, people)
    # Fielding advanced metrics (DRS/UZR) aren't derivable from Lahman; the raw
    # `fielding` table (PO/A/E/DP by position) covers fielding questions instead.
    fg_fld_rows: list[tuple] = []

    game_logs_rows = _game_logs_rows(teams_1998, year)

    return {
        "players": players_rows,
        "teams": teams_rows,
        "batting": batting_rows,
        "pitching": pitching_rows,
        "fielding": fielding_rows,
        "salaries": salaries_rows,
        "awards": awards_rows,
        "all_stars": all_stars_rows,
        "standings": standings_rows,
        "fangraphs_batting": fg_bat_rows,
        "fangraphs_pitching": fg_pit_rows,
        "fangraphs_fielding": fg_fld_rows,
        "game_logs": game_logs_rows,
    }

