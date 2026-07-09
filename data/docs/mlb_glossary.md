# MLB Stat Glossary (Quick Reference)

This assistant uses 1998 season data, primarily from the Lahman database (traditional counting stats) and FanGraphs (advanced metrics). The definitions below are included so you can ask “What is X?” questions directly in the chat.

## Common batting stats

- **AB (At Bats):** Plate appearances excluding walks, hit-by-pitch, sacrifices, catcher interference, and some other cases.
- **H (Hits):** Singles + doubles + triples + home runs.
- **HR (Home Runs):** Hits that score the batter automatically.
- **RBI (Runs Batted In):** Runs that score on a batter’s action, with some exceptions.
- **BB (Walks):** Base on balls.
- **SO (Strikeouts):** Times a batter strikes out.

### Rate stats

- **AVG (Batting Average):** `H / AB`
- **OBP (On-Base Percentage):** Roughly `(H + BB + HBP) / (AB + BB + HBP + SF)`
- **SLG (Slugging Percentage):** `Total_Bases / AB` where `Total_Bases = 1B + 2*2B + 3*3B + 4*HR`
- **OPS:** `OBP + SLG`

## Common pitching stats

Innings pitched (IP) is the number of innings a pitcher records. One inning equals 3 outs.

ERA (Earned Run Average) is the standard pitching rate stat. ERA is calculated as `ER * 9 / IP`, where ER is earned runs allowed and IP is innings pitched. Lower ERA is better.

Strikeouts (SO) count batters struck out. Walks (BB) count batters walked.

## Advanced metrics (FanGraphs)

- **WAR (Wins Above Replacement):** An estimate of a player’s total value compared to a “replacement-level” player, measured in wins.
- **wOBA (Weighted On-Base Average):** A rate stat that weights different offensive outcomes by run value.
- **wRC+ (Weighted Runs Created Plus):** Offensive value adjusted for ballpark and league; `100` is league average. Higher is better.
- **FIP (Fielding Independent Pitching):** A pitching metric focused on outcomes a pitcher controls (HR, BB, HBP, SO), scaled to an ERA-like number.

