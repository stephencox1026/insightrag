# Data Catalog

This catalog lists everything the 1998 MLB assistant can search or query.

## Reference Documents

| Document | Topics |
|----------|--------|
| data_catalog.md | This file — available sources and tables |
| mlb_glossary.md | Stat definitions (AVG, OBP, SLG, OPS, ERA, WAR, wOBA, FIP, wRC+) |
| season_1998_overview.md | 1998 season context (HR chase, standings, postseason) |
| rules_faq.md | Qualification rules (batting title, ERA title), common questions |

## Operational Tables (SQL) — 1998 Only

All SQL tables contain data for the **1998 MLB season**.

### Lahman (traditional stats, stable IDs)

| Table | Description |
|-------|-------------|
| players | Player bio and IDs (`player_id`, name, bats/throws) |
| teams | Team record and metadata (league/division, wins/losses, runs, attendance) |
| batting | Player batting lines by team stint (AB, H, HR, RBI, BB, SO, etc.) |
| pitching | Player pitching lines by team stint (W/L, ERA, IPouts, SO, BB, etc.) |
| fielding | Player fielding lines by position and team stint |
| salaries | Player salaries by team |
| awards | Player awards by league |
| all_stars | 1998 All-Star rosters |
| standings | End-of-season division standings |

### FanGraphs (advanced metrics, easier NLQ)

| Table | Description |
|-------|-------------|
| fangraphs_batting | Advanced batting metrics (wOBA, wRC+, WAR, OPS) |
| fangraphs_pitching | Advanced pitching metrics (FIP, WAR) |
| fangraphs_fielding | Advanced fielding metrics (DRS, UZR, innings) |

## Supported Question Types

- **Documents:** definitions and rules (how stats are computed, qualifications)
- **SQL:** leaderboards, player/team stats, standings, salaries, awards
- **Hybrid:** combine a definition or rule with a 1998 stat query (e.g. batting-title rules + 1998 AVG leader)
