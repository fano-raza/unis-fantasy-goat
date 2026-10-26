# Roster Optimizer

The single reference for the Roster Optimizer: what it does, how it decides, the evidence that it works, every decision made along the way, and the plan for putting it in the app. The build-plan doc ([web-app-build-plan.md](web-app-build-plan.md), Phase 6) holds the dated session history; this file holds the current state.

**Status (2026-10-25):** built, backtested on five past seasons, and **live in the app**: an "Optimize roster" button on the Roster page (current season), password-protected. See [In the app](#in-the-app).

---

## What it is

A tool for one fantasy team at a time. Given that team's roster and the current free-agent pool, it recommends which players to drop and which available players to pick up so the team does better in the standings — both win–loss and category standings. It's meant to be run every week of the season.

## Bottom line

Used weekly from the start of the season (up to 2–3 swaps a week), it adds about **+2.4 wins over an 18-week regular season** compared with never changing the drafted roster (95% CI +1.9 to +3.0), and the team ends up better off in **87% of team-seasons**. That's about the same as what the league's real managers gained from all of their own moves (+2.5).

Swapping players by ESPN-style season-to-date rankings gains **nothing** (−0.03 wins). A simple "best available by value" ranking built on the optimizer's own projections does about as well as the optimizer (+2.6), but needs roughly twice as many moves (29 a season vs 15). Almost all of the value comes from the projections, not from the category-aware scoring.

---

## How it works (plain-language version)

Every time it runs, it goes through six steps:

1. **Project every player.** For each player it estimates:
   - **Production per game:** a blend of his real stats so far this season and ESPN's preseason projection. The more games he's played, the more it trusts the real stats. Points become trustworthy fastest (about 3 games); steals and blocks are noisy and take 10–15 games.
   - **Games he'll actually play:** ESPN's projected games blended with how often he's actually played in the last 30 days, then pulled a little toward realistic levels, since nobody plays every game.

   Production × games = each player's expected contribution.
2. **Add up every team.** Totals each fantasy team's expected production in all 9 categories.
3. **Turn the gaps into win chances.** For each category against each opponent: how often would you win it in a typical week? A big lead wins it most weeks; a small lead is close to a coin flip, because categories swing week to week (blocks a lot, points less).
4. **Give your team one score:** half is your chance of winning a weekly matchup (5 of 9 categories), half is the share of categories you'd win, averaged across every team in the league. Turnovers are always a 50/50 coin flip, so it never chases them.
5. **Try every possible swap:** each of your players out, each available free agent in. It skips free agents who are injured, unsigned, or haven't played in two weeks, and rescores your team for every combination.
6. **Make the best swap, then repeat.** It takes the swap that raises your score the most, as long as it improves your weekly win chances by at least 1 percentage point, then looks for the next-best one, up to the weekly limit. If nothing clears the bar, it recommends no move.

**In one sentence:** it estimates what every player will realistically produce, works out how often your team would beat each team in the league, and makes the one or two swaps that raise that most, skipping any move too small to be worth it.

**It is not opponent-specific.** It averages over every team in the league, so it improves the team for the rest of the season rather than targeting one week's opponent. Two opponent-aware variants are listed under [Ideas not yet tested](#ideas-not-yet-tested).

---

## Technical details

Everything lives in [`shared/roster_optimizer.py`](../shared/roster_optimizer.py) (pure pandas/numpy, so the backend's light venv can run it). Use `recommended_config()`; the defaults in `OptimizerConfig` are the calibrated values below.

### Player projection (`blend_players`)

- **Real stats:** season-to-date per-game, from `Ref/player_stats.csv` (FG/FT as makes and attempts so percentages re-aggregate correctly).
- **Prior:** ESPN's season projection, with a small weight on last season's actual averages (20%, scaled down when last season's sample is under 20 games). Players with only last season get it shrunk toward replacement level by sample size. Players with neither get replacement level (median projection of the free-agent pool).
- **Blend per stat:** real weight = `GP / (GP + k)`, with k fitted per stat on player-level prediction error (2019–2021): PTS 3, REB/AST/3PTM/FGM/FGA 5, FTM/FTA/TO 7, BLK 10, STL 15. The original flat k = 15 trusted the preseason projection too long; those projections flatter free agents (they're usually free agents because they've fallen short of them).
- **Availability** (share of the remaining season a player will play): average of ESPN projected games ÷ 82 (or 0.60 for players ESPN doesn't project — the measured average) and the last-30-days playing rate, the rate's weight ramping from 0 to 50% over the first 28 days, then calibrated as `0.065 + 0.816 × availability` (players rated 94–97% available actually played ~80–82%).
- **Excluded from pickups:** ESPN injury status OUT / INJURY_RESERVE / SUSPENSION, and players on no NBA roster (NBA team "FA").

### Team values and scoring (`optimize`)

- Team totals = sum of each player's per-game line × availability, scaled to the league's most common roster size (so a 14th player isn't a built-in edge).
- Per category vs each opponent: `P(win) = Φ(gap / (σ·√2))`, where σ is the category's week-to-week variability, measured from every recorded season's CompStats (2019–2026): coefficient of variation PTS 12.3%, REB 13.6%, AST 14.9%, 3PTM 18.3%, STL 20.1%, BLK 24.7%, TO 16.0%; absolute SD FG% 2.4 points, FT% 3.65 points.
- **Objective `standings`:** 0.5 × P(win ≥ 5 of 9 categories) (Poisson-binomial over the 9) + 0.5 × expected share of categories won, averaged over opponents. TO is fixed at 0.5 (user decision: never optimize turnovers — historically they run inversely to team strength).
- **Search:** greedy. Only the team's original players can be dropped (each swap is one real move), an added player can't be added twice, and the search stops when the best remaining swap gains less than 0.01 (1 percentage point of weekly win probability).
- Other objectives kept for comparison: `ratings` (the original min-max design), `category_wins` (target-5 framework), `matchup_wins`.

---

## Evidence

### Backtest setup

- **Seasons:** 2019–2023, our league's ESPN years (2024–2026 were on Yahoo, which has no NBA projections via API — checked against Yahoo's docs and live).
- **Data** ([`scripts/export_backtest_data.py`](../scripts/export_backtest_data.py), run in the stat-updater container): every player's game log, ESPN's stored projections, **every team's roster and lineup slots for every day of the season** (ESPN keeps day-by-day history), and exact week boundaries probed from ESPN.
- **Data check:** rebuilding each team's real weekly totals from daily lineups + game logs matches the league's recorded points exactly for 100% of team-weeks, all stats exactly for 96–98% (the rest are ±1 in the final week — later stat corrections).
- **Replay** ([`scripts/backtest_roster_optimizer.py`](../scripts/backtest_roster_optimizer.py)): real results before the checkpoint; after it, every team simulated identically from daily rosters + real game lines with a 10-active-slot cap. Given real rosters, the simulation picks the same matchup winner as reality 87–95% of the time.
- **No hindsight:** at each checkpoint the optimizer only sees games before that day, stored projections, the prior season, and that day's rosters. ESPN has no historical injury status, so "no games in the prior 14 days" stands in for it.
- **Overfitting guard:** all iteration on 2019–2021; 2022–2023 held out and run once, against a test written down beforehand. 95% bootstrap confidence intervals on every result.
- **Known projection caveat:** 2020 and 2023's stored projections are mid-season snapshots (they partly "know" the outcome); 2019, 2021 and 2022 look truly preseason. Results in 2020/2023 looked similar to the clean years.

### What didn't work

| Version | Result |
|---|---|
| Original design: target 5 categories, min-max ratings | No standings gain (+0.07 matchup wins/case vs standing pat). The min-max rating stops counting a category once you lead the league in it, so it traded away production margins. |
| One-time swaps (any objective), then standing pat | Not significant on the hold-out seasons (+0.07 to +0.12). |
| Forcing a 5-category punt with the new scoring | Positive but weaker than letting the standings objective decide. |

Diagnosis that led to the fixes: the original's pickups were projected at 11.6 points per game vs 13.6 for the players dropped, and over the rest of the season the pickups scored 278 points each vs 369 for drops. Then: a winner's curse (pickups over-projected ~7%), and pickups playing far fewer games than projected (14% never played again).

### Weekly use from week 1 (the realistic case)

Each strategy rerun every week from the post-draft rosters, all 46 team-seasons, vs never changing the drafted roster:

| Strategy | Wins over 18 weeks (95% CI) | Category wins | Swaps / season |
|---|---|---|---|
| Optimizer, up to 2 / week | +2.43 [+1.87, +2.99] | +10.1 | 15.0 |
| **Optimizer, up to 3 / week** | **+2.60 [+2.06, +3.14]** | +10.3 | 15.6 |
| Rank swap on the optimizer's projections, 2 / week | +2.61 [+2.00, +3.28] | +10.3 | 29.1 |
| Rank swap on the optimizer's projections, 3 / week | +2.16 [+1.60, +2.76] | +9.7 | 34.7 |
| Rank swap on season-to-date stats (ESPN-style) | −0.03 [−0.63, +0.63] | +1.2 | 26.0 |
| Managers' real moves | +2.50 [+1.82, +3.20] | +9.1 | — |

- The optimizer vs the season-stat ranking: **+2.47 wins a season** [+1.99, +2.95], better in 89% of team-seasons.
- The optimizer vs the projection-based ranking: a tie (−0.17 [−0.66, +0.33]), with half the moves. With more room the ranking overtrades and gets worse; the optimizer barely uses a third slot.
- By season (2 / week): 2019 +3.56, 2020 +1.28, 2021 +3.67, 2022 +1.45, 2023 +2.45.

**Week by week** (optimizer, 2 / week; wins added vs standing pat): weeks 1–2 ≈ 0 (no real stats yet), weeks 3–6 about +0.15 a week, weeks 7–18 a steady +0.12 to +0.30 (about +0.15 on average). Cumulative: +0.5 by week 5, +1.4 by week 10, +2.1 by week 15, +2.5 by week 18. Standing pat wins about 35% of weeks as the drafted roster ages; weekly use keeps the team near 50%. Individual weeks are noisy (44 matchups per week in the data) — trust the season totals.

### Checkpoint backtest (weeks 5/10/15 starts, 138 cases)

Weekly use with the standings objective: +0.73 matchup wins per case [+0.46, +1.01], +3.2 category wins [+2.3, +4.1], W/L rank up 35% / down 13%, category rank up 42% / down 12%. Hold-out (2022–23) alone: +0.50 [+0.18, +0.84]. Gains are largest when started early; from week 10 or 15 the gain is small (fewer weeks left).

### Caveats

- The simulation lets a player the optimizer picked up also appear on another team's real roster later (no exclusivity).
- The lineup model matches real matchup winners 87–95% of the time, not 100%.
- 2019 has no last-season prior (no 2018 league ID configured).
- Effects shrank from development to hold-out seasons (normal; 2019 is an unusually strong season).
- It doesn't model trades, waiver priority, or acquisition limits.

---

## Decisions made with the user

- Pool = free agents only (not on any fantasy roster). Any player for any player; no position constraints.
- No games-per-week factor — it's a season-long tool.
- Ignore turnovers entirely (never a target; zero weight; hidden from results).
- Injured players: excluded from pickups; rostered injured players weighted by season-long availability (not a flat penalty, which made it cut injured stars like LeBron and Curry).
- Don't show tiny swaps.
- Same best free agents for every team is fine — it's a single-team tool.
- Backtest: 2019–2023 including 2020/2023, checkpoints weeks 5/10/15, success = W/L and category standings.
- Projections: ESPN only (Yahoo has none via API), small weight on last season.
- **Password-protected, server-side, password chosen by the user.**
- User asked about 3 changes a week: backtested — harmless, slightly positive (+0.16 wins [−0.01, +0.35]); recommended default is up to 3.

## Recent form (tested 2026-10-25)

Question: is there an advantage to weighting players' last week or two instead of (or alongside) season averages?

- **Player predictions** ([`scripts/analysis_recent_form.py`](../scripts/analysis_recent_form.py); every weekly checkpoint weeks 3–18, ~5,000 player-checkpoints per season and horizon; tuned on 2019–2021, confirmed on 2022–2023): blending a little recent form in helps; leaning on it hurts.

  | Weight on recent form | Error, next 2 weeks | Error, rest of season |
  |---|---|---|
  | Last 14 days at 20% (best) | −1.2% (hold-out −1.3%) | −0.5% |
  | Last 7 days at 10% | −1.0% | −0.6% |
  | Last 7 days at 50% | +8.6% worse | +18% worse |
  | Last 7 days at 70% | +21% worse | +40% worse |

  Gains are concentrated in role-driven stats (shot attempts −4.5 to −6%, points/rebounds/assists/makes −2 to −2.5%); steals and blocks gain nothing (short stretches are noise).
- **Standings** (weekly from week 1, up to 3 swaps, 46 team-seasons): season-only +2.60 wins vs standing pat; with last-14-day form (per-category weights 0.3 PTS/FG, 0.2 most, 0.1 STL/BLK) **+2.78**. Difference **+0.18 wins/season [−0.12, +0.50]** — positive in all 5 seasons (2019 +0.06, 2020 +0.11, 2021 +0.11, 2022 +0.40, 2023 +0.20) but not statistically significant.
- **Status:** available as `OptimizerConfig(recent_form_window="d14")` (weights in `recent_form_weight`), **off by default** pending the user's call. The live `player_stats.csv` already has the `d14_*` columns it needs.

## Ideas not yet tested

- **Remaining-schedule weighting:** weight opponents by how often you still face them. Still season-long; probably the more promising variant.
- **This-week streaming:** maximize the chance of beating this week's opponent. Could win individual weeks but churns more.
- **Team-aware ranking hybrid:** the plain projection ranking ties the optimizer; a ranking with category-need weights might beat both.

Any of these should go through the same backtest (and only be judged on seasons not used to tune it).

## Code map and how to run

| File | Purpose |
|---|---|
| [`shared/roster_optimizer.py`](../shared/roster_optimizer.py) | The algorithm (`blend_players`, `optimize`, `recommended_config`) |
| [`scripts/export_player_projections.py`](../scripts/export_player_projections.py) | ESPN projection + last season + injury status → `Ref/player_projections.csv` (not yet in the daily loop) |
| [`scripts/roster_optimizer_report.py`](../scripts/roster_optimizer_report.py) | Recommendations for one or all teams on live data |
| [`scripts/export_backtest_data.py`](../scripts/export_backtest_data.py) | Historical season export for the backtest (stat-updater container) |
| [`scripts/backtest_roster_optimizer.py`](../scripts/backtest_roster_optimizer.py) | Checkpoint + weekly backtest, calibration, summaries with CIs |
| [`scripts/backtest_weekly_strategies.py`](../scripts/backtest_weekly_strategies.py) | Weekly-from-week-1 comparison: optimizer (2/3 per week), rank swaps, stand pat, managers |
| [`scripts/analysis_recent_form.py`](../scripts/analysis_recent_form.py) | Recent-form (last 7/14 days) weighting vs player prediction error |
| [`tests/test_roster_optimizer.py`](../tests/test_roster_optimizer.py), [`tests/test_backtest.py`](../tests/test_backtest.py) | 53 tests, including brute-force checks of every objective |

```sh
# tests
.venv-dashboard/bin/python -m pytest tests/ -q

# live recommendations (stats/rosters from the API, projections from the export)
.venv-dashboard/bin/python -m scripts.roster_optimizer_report \
  --stats player_stats.json --rosters roster_ranks.json --projections player_projections.csv \
  --team Fano --days-elapsed 5 --max-swaps 3

# backtest (data from export_backtest_data.py)
.venv-dashboard/bin/python -m scripts.backtest_roster_optimizer --data <dir> --ref <ref dir> \
  --years 2019 2020 2021 2022 2023 --variants standings --rolling standings
```

---

## In the app

Shipped 2026-10-25 (user decisions: a button on the Roster page; swaps per run a user setting up to roster size, default 3; anyone with the password can use it).

- **Where:** Team → Roster, "Optimize" button in the controls row (shown only for the current season). Flow (redesigned 2026-10-25 at the user's request):
  1. **Premium mode** (since 2026-10-25): the optimizer is a premium feature. Locked → clicking Optimize opens the shared premium login (see [Premium mode](#premium-mode)) and continues straight into step 2 once unlocked; already unlocked → straight to step 2.
  2. **Swaps**: "How many players are you willing to swap out?" (1 to roster size, default 3), then "Optimize".
  3. **Loading**: the dialog closes; a translucent veil covers the roster card with rotating optimization-jargon phrases (`OPTIMIZER_PHRASES` in [`loading-phrases.ts`](../web/src/lib/loading-phrases.ts), every 1.5 s). Held for at least 3 s (`MIN_RUN_MS`) so the phrases are readable; the optimizer itself answers in under a second.
  4. **Result**: replaces the roster table until "Back to roster". Header: weekly matchup win chance before → after. **Desktop (≥1024px)**: current roster on the left (players leaving tinted red, − icon) beside the roster after the swaps on the right (players joining tinted green, + icon), both with the page's columns (NBA Team, Rank, Games Left) and an Average Rank row with league placement. **Narrower screens**: one table edited in place, each player leaving followed directly by their replacement; shorter headers (Team / Rank / Left) and an Average Rank "before → after" row. Below: collapsible "Win chance by category". Incoming players' Rank/NBA team come from `roster_ranks` (free agents are in it, same names the optimizer joins on).
  - The Roster Rankings card below uses the optimized roster's average while a result is showing (team name in yellow, "was X" and a green up / red down arrow beside it), the same way manual what-if swaps already did; "Back to roster" restores the real ranking.
  - While a result is showing, the Full Week Grid toggle is disabled (the comparison always shows Games Left); manual "what-if" swaps are cleared; switching team/season clears the result (and an answer arriving after a team switch is discarded).
  - Component: [`web/src/components/roster-optimizer.tsx`](../web/src/components/roster-optimizer.tsx) (`RosterOptimizerButton`, `OptimizerResults`), wired in [`roster-view.tsx`](../web/src/components/roster-view.tsx).
- **Endpoints:** `POST /league/roster_optimizer/check_password` `{password}` → `{ok: true}` / 401 / 503 (no optimizer run). `POST /league/roster_optimizer` `{team, password, max_swaps}` → `LeagueStore.roster_optimizer` ([`league_store.py`](../dashboard_site/api/league_store.py)). Wrong password 401; no password configured 503 (feature off); unknown team 404; `max_swaps` clamped to the roster size. Runs in ~0.15 s.
- **Data:** `export_player_projections` now runs in the stat-updater's daily loop (`Ref/player_projections.csv`); `days_elapsed` comes from week 1's start date in `Ref/week_calendar.csv` (US Eastern date).
- **Password:** lives **only on the droplet** in `/opt/unisFantasyGOAT/infra/docker/env/dashboard-api.env` (`ROSTER_OPTIMIZER_PASSWORD=...`, mode 600, git-ignored; [`dashboard-api.env.example`](../infra/docker/env/dashboard-api.env.example) documents it). The compose file loads it as an optional `env_file` for `dashboard-api`. **To read it:** `ssh root@134.209.168.108 "grep ROSTER_OPTIMIZER_PASSWORD /opt/unisFantasyGOAT/infra/docker/env/dashboard-api.env"`. **To change it:** edit that line, then `cd /opt/unisFantasyGOAT && docker compose -f infra/docker/docker-compose.yml up -d dashboard-api && docker compose -f infra/docker/docker-compose.yml restart caddy`. The user can just ask Claude to do either.
- **Tests:** [`tests/test_roster_optimizer_api.py`](../tests/test_roster_optimizer_api.py) (password handling, 404/422, response shape, clamping) — 62 tests total. `httpx` is installed in the local `.venv-dashboard` only (test dependency).

## Premium mode

Added 2026-10-25 (user request): one password unlocks every premium feature for the browser session. Features stay visible to everyone; using one while locked opens the premium login.

- **Password:** the same `ROSTER_OPTIMIZER_PASSWORD` on the droplet (see In the app above; env var name kept to avoid touching the droplet config). Checked server-side by every premium endpoint; `POST /premium/check_password` is the login (`/league/roster_optimizer/check_password` kept as an alias).
- **Frontend:** [`web/src/components/premium.tsx`](../web/src/components/premium.tsx) — `PremiumProvider` (in `app/layout.tsx`), `usePremium()` (`unlocked`, `password`, `requireUnlock(cb)`, `openDialog()`, `lock()`), the login/"Premium is on" dialog (lists `PREMIUM_FEATURES`), and `PremiumNavButton` (gold, crown fills when unlocked): desktop = rightmost nav tab after Champions Lounge; mobile = bottom of the menu drawer, above the light-mode setting. Password kept in `sessionStorage` (`premium-password`; migrates the old `roster-optimizer-password`). A 401 from any premium call → `lock()` (password changed server-side).
- **Features:** (1) the Roster Optimizer; (2) **Win chance by category** on the Roster page ([`roster-category-odds.tsx`](../web/src/components/roster-category-odds.tsx)): current season, between the roster and Roster Rankings, hidden while an optimizer result is up. Locked = blurred preview + "Unlock with Premium". Unlocked = weekly matchup win chance and per-category bars for the real roster, updating (300 ms debounce) with the page's manual swaps via `POST /league/roster_category_odds {team, password, swaps:[{drop, add}]}` → `LeagueStore.roster_category_odds` (scores real vs swapped roster with `ro.optimize(max_swaps=0)`, so it matches the optimizer's numbers; one-sided like the manual simulation; unknown players → `skipped`). ~0.2–0.3 s on the droplet; blended players cached per instance in `_optimizer_inputs`.
- **Adding a premium feature:** gate the UI with `usePremium().requireUnlock(...)`, send `premium.password` to an endpoint that calls `_check_roster_optimizer_password`, `lock()` on 401, and add a line to `PREMIUM_FEATURES`.

## Performance on the droplet (measured 2026-10-25)

| | Result |
|---|---|
| Server-side time per run | 0.7–0.9 s warm, ~1.1 s on the first request after a restart (loads CSVs). Projection blend 0.04 s; the search over ~960 free agents is the rest. |
| End-to-end, as the user sees it | 1–3 s (varies with the droplet's memory pressure) |
| Extra memory per run | ~50 MB, released after |
| Swaps set to roster size | Not heavier in practice — the search stops when no swap clears the 0.01 bar (usually 2–4 swaps) |

The constraint is the droplet itself: 961 MB RAM, ~97 MB available and ~1.9 GB of swap in use **before** the optimizer runs. One run at a time is fine; several simultaneous runs (~50 MB each) would slow things and could risk out-of-memory. Options if needed (none done yet): (1) only search the top ~200–250 free agents (best overall + best few per category) — ~4–5x lighter, verify on the backtest data that picks don't change first; (2) cache each team's result for the day (inputs change daily); (3) upgrade the droplet to 2 GB RAM (helps everything on it).

## Open items (as of 2026-10-25)

1. **Recent form** — tested; recommended to switch on (`recent_form_window="d14"`, +0.18 wins/season, positive in all 5 seasons, not significant). Awaiting the user's go-ahead; it's off in the live tool.
2. **Performance hardening** — see options above; recommended option (1) if the user wants it.
3. **Opponent-aware variants** — untested (see Ideas not yet tested).
4. **`Ref/week_calendar.csv` is wrong around the All-Star break for 2019–2023** (ESPN seasons) — likely breaks the Roster page's week picker for those seasons. Not fixed.
5. **Each new season:** make sure `Ref/week_calendar.csv` has week 1's `StartDate` for the new year (drives `days_elapsed`), `espnLeagueIDs`/`espnTeamIDs` in `constants.py` include the year, and the projections export runs (it uses `currentYear`).
6. **Backtest data isn't in the repo.** A persistent copy (2019–2023, 20 files, 8.6 MB) is on the droplet at **`/srv/unisfantasy/data/backtest/`** — fetch it with `scp 'root@134.209.168.108:/srv/unisfantasy/data/backtest/*' <local dir>` and pass that dir as `--data`. To rebuild from scratch: for each year, `ssh root@134.209.168.108 "cd /opt/unisFantasyGOAT && docker compose -f infra/docker/docker-compose.yml exec -T stat-updater python3 -m scripts.export_backtest_data --year <year> --out /tmp/backtest"` (~5 min/season; mostly the day-by-day roster pulls), then `docker compose ... cp stat-updater:/tmp/backtest /tmp/bt_host` and `scp 'root@134.209.168.108:/tmp/bt_host/*' <local dir>`. The scripts also need `Ref/<year>_CompStats.csv` (the local ref dir or the droplet's `/srv/unisfantasy/data/ref`). No 2018 league ID is configured, so 2019 runs without a last-season prior.
7. **Pre-existing lint errors** in `web/src/components/roster-view.tsx` (4, unrelated to the optimizer button).

## App integration plan (as planned, before shipping)

Goal: a password-protected screen where you pick a team and get this week's recommended swaps, with a plain-language reason for each.

### Phase A — Daily data (backend)

1. Add `export_player_projections()` to the stat-updater daily loop ([`stat_updater.py`](../stat_updater.py)), right after `export_player_stats()`, same try/except pattern. Output: `Ref/player_projections.csv`.
2. `LeagueStore` ([`dashboard_site/api/league_store.py`](../dashboard_site/api/league_store.py)): lazy loaders for `player_projections.csv` (same pattern as `roster_ranks`).
3. Season start date for `days_elapsed`: week 1's `StartDate` for the current year from `Ref/week_calendar.csv` (2027: 2026-10-20). Verify it each new season.

### Phase B — Optimizer endpoint

1. `LeagueStore.roster_optimizer(team, max_swaps=3)`: player stats + projections + current-year rosters (name → ESPN id, as the report script does) → free-agent list → `blend_players(..., days_elapsed=...)` → `optimize(team, ..., recommended_config(max_swaps=3))`.
2. Response: the team's per-category win chances before and after (TO hidden), the ordered swaps (drop/add names, NBA teams, games played, how each changes each category's win chance), the score change, and the data's last-updated times. "No moves recommended" is a normal result.
3. `POST /league/roster_optimizer` with `{team, password, max_swaps?}` in [`app.py`](../dashboard_site/api/app.py). Password checked server-side with a constant-time compare against `ROSTER_OPTIMIZER_PASSWORD`; wrong password → 401; variable unset → 503 (feature off). No caching (results are computed per request in well under a second).
4. Password config: a new `infra/docker/env/dashboard-api.env` on the droplet only (plus a committed `.env.example`), wired into the `dashboard-api` service's `env_file` in [`docker-compose.yml`](../infra/docker/docker-compose.yml). **The user sets the value** — never committed, never invented.
5. Tests: endpoint tests with FastAPI's test client (wrong password, missing password, valid request shape) — needs `httpx` in the local dev venv only.

### Phase C — Screen (frontend)

1. Location (user to decide): a new **Optimizer** tab in the Team/Players tab group (`/team/optimizer`, alongside Profile, Roster, Trade Hub) is the natural fit, since it's team-specific. Alternative: its own locked nav item like Champions Lounge.
2. Password gate: same look as Champions Lounge, but verified by the backend. Keep the password in `sessionStorage` for the visit so it isn't retyped.
3. Content: team picker (defaults to the remembered team), then:
   - the team's win chances per category (8 categories, TO hidden), with its strongest categories called out;
   - the recommended swaps in order, each as "Drop X → Add Y" with a one-line reason ("raises your weekly win chances by 4 points; helps 3PTM and STL, costs a little REB");
   - before/after win chances;
   - a clear empty state when no move clears the bar, and a "data as of" note.
4. Types + fetcher in [`web/src/lib/api.ts`](../web/src/lib/api.ts). Built with the frontend-design skill, both light and dark mode.

### Phase D — Verify and ship

1. Local: backend + frontend against real data; check a couple of teams against the report script's output; Playwright pass on desktop and mobile in both themes.
2. Deploy per the standing pre-authorization: commit, push (Vercel auto-deploys), droplet deploy. Set the password env var on the droplet first (needs the user's value).

### Phase E — Later

- Opponent-aware variants (backtest first).
- Weekly reminder or Discord command.
- Fix `Ref/week_calendar.csv` around the All-Star break for 2019–2023 (it also affects the Roster page's week picker).

### Questions for the user before building

1. **Password value** (needed before deploy).
2. **Screen location:** Team tab (`/team/optimizer`) or its own nav item?
3. **Swaps per run:** up to 3 (backtest-supported)?
4. **Who can see it:** anyone with the password, or should it be limited further?
