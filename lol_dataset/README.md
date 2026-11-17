# 🏆 League of Legends World Championship — Complete Dataset (2011–2025)

> **A large, structured dataset covering all 15 editions of the League of Legends World Championship ("Worlds")**, from the inaugural 2011 event in Jönköping, Sweden to the 2025 event in Chengdu, China. 9 interlinked CSV files — **417 total data rows** — spanning group-stage standings, knockout bracket results, prize distribution, placements, venues, and match statistics.

---

## 📌 About the Dataset

The **League of Legends World Championship** is Riot Games' annual season-ending tournament and the most-watched event in League of Legends esports, crowning a global champion each year since 2011.

This dataset was compiled to support deep, year-over-year and team-level analysis of the tournament: who made groups, who won which bracket match, how prize money was split down to the last-place team, and how regions have traded dominance over 15 years.

---

## 📁 Files Overview

| # | File | Rows | Cols | Description |
|---|------|------|------|-------------|
| 01 | `01_Worlds_Event_Tournament_Summary.csv` | 15 | 14 | One row per year — dates, prize pool, winner, runner-up, format, MVP |
| 02 | `02_Worlds_Group_Stage_Standings.csv` | 142 | 10 | Every team's group/play-in standing (W-L, region, advanced Y/N), 2011–2014 & 2016–2019 |
| 03 | `03_Worlds_Knockout_Bracket_Results.csv` | 72 | 7 | Every quarterfinal/semifinal/final match, all 15 years, with scores |
| 04 | `04_Worlds_Final_Placements.csv` | 60 | 4 | Top-4 finishers (1st/2nd/3rd–4th) per year, with region |
| 05 | `05_Worlds_Grand_Final_Results.csv` | 15 | 9 | Grand Final matchup, score, venue, and MVP per year |
| 06 | `06_Worlds_Prize_Pool_Distribution_By_Tier.csv` | 84 | 5 | Full placement-by-placement prize breakdown (1st through last place) for 2011, 2012, 2016, 2017, 2019 |
| 07 | `07_Worlds_Calendar_Venues.csv` | 15 | 7 | Tournament dates, duration, host country, and final venue |
| 08 | `08_Worlds_Region_Championship_Summary.csv` | 5 | 6 | Titles, runner-ups, and top-4s aggregated by region (2011–2025) |
| 09 | `09_Worlds_Match_Statistics_golgg.csv` | 9 | 10 | Per-tournament match stats (KDA/GPM/CSM leaders, game lengths), 2013–2018 & 2023–2025 |

**Total: 417 data rows across 9 files.**

---

## 🔑 Column Dictionary

### 01 — Event & Tournament Summary
`Year` · `Event_Name` · `Start_Date` · `End_Date` · `Host_Country` · `Prize_Pool_USD` · `Num_Participants` · `Winner` / `Winner_Region` · `Runner_Up` / `Runner_Up_Region` · `Format` · `Finals_Score` · `Finals_MVP`

### 02 — Group Stage Standings
| Column | Description |
|--------|-------------|
| `Year` | Tournament year |
| `Stage` | "Play-In" or "Group Stage" |
| `Group` | Group letter (A–D) |
| `Position` | Final standing within the group |
| `Team` | Team name |
| `Region` | Competitive region |
| `Wins` / `Losses` | Group-stage record |
| `Win_Pct` | Win percentage |
| `Advanced` | Whether the team advanced to the next stage |

### 03 — Knockout Bracket Results
`Year` · `Round` (Quarterfinal/Semifinal/Upper Final/Lower Bracket Final/Grand Final) · `Team_1` · `Team_2` · `Score` · `Winner` · `Notes`

### 04 — Final Placements
`Year` · `Placement` (1st/2nd/3rd–4th) · `Team` · `Region`

### 05 — Grand Final Results
`Year` · `Match_Type` · `Team_1` / `Team_2` · `Winner` · `Score` · `Best_Of` · `Venue` · `MVP`

### 06 — Prize Pool Distribution by Tier
`Year` · `Placement_Tier` (e.g. "5th–8th") · `Team(s)` · `Prize_USD` · `Prize_Pct_of_Total`

### 07 — Calendar & Venues
`Year` · `Start_Date` / `End_Date` · `Duration_Days` · `Host_Country` · `Final_City` / `Final_Venue`

### 08 — Region Championship Summary
`Region` · `Championships_Won` · `Runner_Up_Finishes` · `Third_Fourth_Finishes` · `Total_Top4_Appearances` · `Championship_Years`

### 09 — Match Statistics (gol.gg)
`Year` · `Games_Played` · `Avg_Game_Duration` · `Avg_Kills_Per_Game` · `Shortest_Game` / `Longest_Game` · `Most_Kills_Single_Game` · `Top_KDA_Leader` · `Top_Team_GPM_Leader` · `Top_CSM_Leader`

---

## 🔗 Entity Relationships

```
Event_Tournament_Summary ──┬──> Group_Stage_Standings        (via Year)
                            ├──> Knockout_Bracket_Results     (via Year)
                            ├──> Final_Placements             (via Year)
                            ├──> Grand_Final_Results           (via Year)
                            ├──> Prize_Pool_Distribution        (via Year)
                            ├──> Calendar_Venues                (via Year)
                            └──> Match_Statistics_golgg          (via Year)

Group_Stage_Standings ──> Knockout_Bracket_Results     (teams that "Advanced" feed the bracket)
Knockout_Bracket_Results ──> Final_Placements          (bracket losers map to placement tiers)
Final_Placements ──> Region_Championship_Summary        (via Region, aggregated)
```

---

## ⚠️ Coverage Notes & Sourcing

- **Sources**: Liquipedia League of Legends Wiki, Wikipedia's per-year World Championship articles (infobox group tables, knockout brackets, and prize tables), and Games of Legends (gol.gg) for match-level statistics.
- **Access note**: direct fetches to `liquipedia.net` were rate-limited (HTTP 429) throughout compilation, so data was gathered via Wikipedia and gol.gg page fetches plus web search instead.
- **File 02 (Group Stage Standings)** covers 2011–2014 and 2016–2019 (8 of 15 years) — the years where Wikipedia's infobox group tables were captured in full. 2015, 2020–2025 group standings were not compiled at this level of detail.
- **File 03 (Knockout Bracket)** has full quarterfinal-through-final detail for 2011–2014 and 2016–2019. For 2020–2025, only semifinal and Grand Final matches are included (quarterfinal-round detail for those years wasn't compiled); this is noted per-row.
- **File 06 (Prize Distribution by Tier)** only covers 5 years (2011, 2012, 2016, 2017, 2019) where Wikipedia published the complete placement-money table. Every other year still has its overall prize pool total in File 01.
- **File 09 (Match Statistics)** covers 9 of 15 years (2013–2018, 2023–2025); gol.gg's stat pages for 2011, 2012, 2019–2022 could not be located.
- **2017 prize pool**: sources differ slightly; the Esports Earnings/Wikipedia total of $4,946,970 is used.
- **2012 Finals MVP**: no Finals MVP award existed yet in Season 2.
- This is still not a full player-level dataset (individual rosters, per-game champion picks/bans, and KDA are not included) — flag if you'd like that added as a further expansion.

---

## 💡 Suggested Analyses

- 🌏 **Regional dominance over time** — Korea vs. China vs. Europe title counts by era, using files 04 + 08
- 🎯 **Group-stage → knockout conversion** — which regions/seeds most reliably advance, using files 02 + 03
- 💰 **Prize pool growth & distribution shape** — Riot's base contribution vs. crowdfunded spikes (2016–2018), and how steeply money drops off by placement tier (file 06)
- ⚔️ **Grand Final closeness** — sweeps (3-0) vs. full 5-game classics, using file 05
- 🏟️ **Host rotation** — how often Worlds returns to Korea/China/US vs. touring Europe, using file 07
- 📈 **Team dynasties** — T1/SKT's six titles across three separate three-peats, traceable end-to-end through files 02→03→04

---

## 📜 License

Compiled from publicly available League of Legends World Championship results (Liquipedia, Wikipedia, gol.gg). Not officially affiliated with Riot Games or Riot's esports properties. Released for research/analysis purposes with attribution to original sources.
