# Trade Recommender

**Status (2026-10-27):** algorithm built ([`shared/trade_finder.py`](../shared/trade_finder.py)), tested, and backtested on 2019–2023. **Not in the app.** The backtest does **not** show that the recommended trades help the team that makes them (see [Backtest](#backtest-2026-10-27)), so the next step is the user's call: iterate on the algorithm, or ship it as a trade-idea tool without a claimed benefit. UI guidance (it'll live in Trade Hub) is still to come from the user.

Sister tool to the [Roster Optimizer](roster-optimizer.md). It uses the same player projections and the same team scoring, but searches trades with other managers instead of free-agent pickups.

---

## What it does

1. You pick the player(s) on your roster you'd trade away.
2. It tries every player (or group of players) on every other roster in return.
3. It scores **both teams** before and after the trade, then lists the trades that help you and that the other team would plausibly accept.

The "win %" is the optimizer's standings score: half the weekly matchup win chance (5 of 9 categories), half the share of categories won, averaged over every opponent. TO is a fixed coin flip. Everything is season-long, with no position limits ("any player for any player"), the same as the optimizer.

## The one real difference from the optimizer: both teams change

The optimizer scores one team against a frozen league. A trade changes two teams, and those two teams also play each other. So after every candidate trade, both teams are rescored against the updated league, including each other. The building blocks already exist in [`shared/roster_optimizer.py`](../shared/roster_optimizer.py) (`win_probabilities`, `at_least_k`, `category_sigma`). The new piece is a vectorized "score every team at once" function. The prototype built one and it scores the whole league's 1-for-1 trade space (14,744 trades) in 0.6 s locally.

---

## Prototype findings (live data, 2026-10-27, week 1, day 7)

Thresholds are in points of the standings score (1 point = 0.01).

**1-for-1 trades (14,744 possible in the league):**

| Rule for the partner team | Trades that pass (you gain ≥ +1) | Your players with at least one option |
|---|---|---|
| Must also gain ≥ +1 (strict win-win) | 6 | 5 / 128 |
| May lose up to 1 point | 358 | 101 / 128 |
| **May lose up to 3 points** (user's rule) | **2,467** | **125 / 128** |

- **Strict win-win 1-for-1 trades are almost nonexistent.** Trades are close to zero-sum: if you get better, the team you play gets relatively worse. The few that exist are real category swaps (e.g. Embiid ↔ LaMelo between Adam and Rohil, +1.2 / +1.4).
- **The user's "partner loses less than 3 points" rule makes the tool useful.** Almost every player has options. 3 points is small compared with how far a team's score moves over a season.

**2-for-1 trades (Fano gives 2, gets 1; 8,970 possible):**

- You have an open roster spot afterward, so the tool picks up the best free agent. The partner is one over, so it drops its least-valuable player.
- **545 are strict win-win**, and 2,085 pass the 3-point rule. Consolidation plus the free-agent pickup creates real value for both sides, so multi-player trades are where win-wins actually live.
- Examples: Tatum + Nembhard → Zahir's Jalen Johnson (Zahir drops Murray-Boyles, Fano adds Cedric Coward), +2.2 / +2.2. Clingan + Sarr → Rohil's LaMelo Ball (Rohil drops Mikal Bridges, Fano adds Ace Bailey), +2.1 / +3.1.

**The problem the prototype found: category fit ≠ what a manager will accept.**
The top 1-for-1 results under the 3-point rule are full of trades like *Hartenstein → LaMelo Ball* (Fano +4.6, Rohil −2.3) and *Day'Ron Sharpe → LaMelo Ball*. The players aren't injured (LaMelo is ACTIVE, 76% projected availability). The model sees LaMelo adding little in categories Rohil already wins, so losing him barely moves Rohil's score. Rohil's manager will judge the deal by player value, not by our model, and would never accept it.

**So a perceived-value check is needed alongside the win-% rule.** It compares what each side gives using a category-neutral player value, such as the optimizer's own projection-based value ranking (the "rank swap" baseline in the backtest) or ESPN/Yahoo rank, and flags or hides lopsided offers. Without it, the top of every list is a trade nobody will accept.

---

## Decisions (user, 2026-10-27)

- **Two modes:**
  - **Fair:** both teams' win % improve (you ≥ +1 point, partner ≥ +1 point).
  - **Fleece:** you ≥ +1 point, partner loses at most 1 point. Fleece includes trades where the partner also gains, so it's a superset of Fair; a win-win that's also your best trade is never hidden.
- **Shapes:** 1-for-1 and 2-for-1 (you give 2, get 1) in both modes. Pick one player and it tries him alone (1-for-1) plus paired with each of your other players (2-for-1). Pick two and it tries exactly that pair (2-for-1).
- **Lopsided trades:** not shown at all.
- **Sort:** your gain first.
- **Uneven trades:** the partner automatically drops its least-valuable player; you automatically add the best free agent. Both appear on the trade card.
- **Premium feature, in Trade Hub.** Exact look to be specified by the user later.
- **Backtest before shipping:** done, see below.

(The earlier "partner may lose up to 3 points" idea was replaced by the two modes.)

## How it works ([`shared/trade_finder.py`](../shared/trade_finder.py))

- `find_trades(team, give, players, rosters, free_agents, TradeConfig(mode=...))` returns a `TradeResult` with `Trade` cards: shape, partner, give/get, partner's drop, your free-agent add, both teams' gains and after-scores, both teams' weekly matchup win chance after the trade, and the value numbers.
- **Scoring:** `League` holds every team's totals and rescores any set of teams against the hypothetical league. It uses exactly the optimizer's `standings` objective, including category spreads recomputed per hypothetical league. Inputs are the same as the optimizer's (`_optimizer_inputs()`: blended players, active rosters, free agents).
- **2-for-1 balancing:** the partner first picks the drop that costs it least, among its remaining players. Then you pick, for your own score, the best of the top 15 healthy, signed free agents by player value. Same exclusions as the optimizer (OUT/IR/suspended, unsigned).
- **Lopsided filter:** `player_value` is the standard 9-category z-score value of per-game × availability against rostered players (the same formula as the optimizer backtest's "rank swap" baseline). A trade is dropped if the partner's received value, minus its drop, is less than what it gives up (`value_tolerance = 0`).
- **Speed:** ~0.23 s per search on live data (one picked player, both shapes, ~1,500 candidates).
- **Tests:** [`tests/test_trade_finder.py`](../tests/test_trade_finder.py), 18 tests. Every returned trade's scores are recomputed from scratch with `ro.optimize` for both teams; on small random leagues the finder's full result set matches a brute-force enumeration exactly (including the partner's drop and your free-agent choice). Also covered: thresholds, Fair ⊆ Fleece, the lopsided filter (incl. a star-for-scrub case), sorting, injured/unsigned free agents, input validation, and the backtest helpers.

## Backtest (2026-10-27)

[`scripts/backtest_trade_finder.py`](../scripts/backtest_trade_finder.py) reuses the optimizer's replay ([`backtest_roster_optimizer.py`](../scripts/backtest_roster_optimizer.py)): same data (2019–2023 daily rosters + game logs, on the droplet at `/srv/unisfantasy/data/backtest/`), same 10-active-slot lineup simulation, same "only what was known that day" inputs.

- **Setup:** checkpoints at weeks 4, 6, 8, 10, 12 and 14. For every team, the finder searched every active player, giving 276 team-checkpoints. Each team's top Fair and top Fleece trade (by its own gain) was applied on top of reality: both teams' real daily rosters from the checkpoint on, with the traded players substituted one for one. A substitution only happens on days the leaving player is really still there, so roster sizes never change. Every other team stayed real. The rest of the regular season was then replayed and compared with no trade.
- **Controls:** *pickup only* (no trade; just swap the less valuable of your two given players for the same free agent) and *random fair* (a random trade the partner wouldn't see as lopsided, with no win-% rule).
- **Result unit:** change in rest-of-season matchup wins per trade (95% bootstrap CI).

| Scenario | You | Partner | Model predicted (you / partner, pts) |
|---|---|---|---|
| **Fair, top trade** (always a 2-for-1) | −0.01 [−0.14, +0.14] | +0.31 [+0.14, +0.49] | +5.3 / +1.4 |
| **Fleece, top trade** (always a 2-for-1) | +0.10 [−0.07, +0.26] | +0.26 [+0.08, +0.43] | +6.9 / −0.6 |
| Best 1-for-1, Fleece (n = 265) | +0.08 [−0.04, +0.20] | +0.02 [−0.10, +0.14] | +1.8 / −0.5 |
| Best 1-for-1, Fair (only n = 32 had one) | −0.06 [−0.25, +0.12] | +0.20 [−0.05, +0.44] | +1.5 / +1.4 |
| Pickup only (Fair / Fleece free agent) | −0.01 / −0.04 | — | |
| Random value-fair trade | −0.49 [−0.64, −0.32] | +0.17 [+0.02, +0.33] | −3.8 / +6.6 |

By seasons: Fleece was +0.29 [+0.10, +0.50] on 2019–21 but −0.16 [−0.41, +0.08] on the 2022–23 hold-out. Fair was +0.09 then −0.13. By checkpoint, trades made in weeks 4–6 hurt the trading team (−0.3 to −0.5); weeks 8–14 were around 0 to +0.5.

**What it means:**

- **The recommended trades don't reliably help the team making them.** The model predicts about +5–7 points (roughly +0.5 wins over the rest of a season); reality is about zero for Fair and a non-significant +0.1 for Fleece, which turns negative on the hold-out seasons.
- **Partners consistently do better than predicted, and you do worse.** This is the winner's curse: picking the trade with the highest projected gain for you selects trades where your incoming player is over-projected or your outgoing players are under-projected. The lopsided filter uses the same projections, so "fair by value" trades tilt toward the partner in reality.
- **The model's choice is much better than a random value-fair trade** (about +0.5 wins better). Value-fair trades lose for you on average, and the model avoids most of that loss, but it doesn't turn trades into gains.
- **The 2-for-1 free-agent pickup contributes nothing** (pickup only ≈ 0).
- **Win-win trades do exist in reality:** the partner side gains +0.3. That's what Fair mode promises; it just isn't coming out of your share.

**Earlier run, discarded:** the first pass added incoming players even on days the outgoing one was already gone in real life, which gave teams extra players. It showed Fair +0.41 / Fleece +0.55 for you; that was the inflation, not the tool.

## Tuning round 1 (2026-10-27) — user: "keep tweaking until it's reliably good"

**Method.** [`scripts/trade_finder_tuning.py`](../scripts/trade_finder_tuning.py) builds a broad candidate set (every team × every active player × every checkpoint, loose thresholds: 910,000 trades over 2019–23) with the model's predictions and an **oracle score**: the same standings scoring using each player's *actual* rest-of-season production (rosters frozen at the checkpoint + the trade). The oracle removes matchup luck and lineup effects. It tracks the frozen-roster replay well (correlation ~0.55; ~0.1 wins per oracle point over ~10 remaining weeks), so policies can be compared without a 35-minute replay each. Tuning used 2019–21 only; 2022–23 was checked once at the end against criteria written down beforehand.

**Replay note.** The backtest's real-roster substitution (a trade only stands while the outgoing player is still on that team's real roster) dilutes every effect, because managers churn rosters. Frozen-roster replay (both teams frozen at the checkpoint, with vs without the trade; the optimizer's one-time-swap method) is the cleaner comparison. Both are reported.

**Diagnosis (2019–21).**
- The model's ranking has signal: candidates predicted at +4–7 points really gained +1–1.5; small predictions really lost.
- Predictions above +10 are mostly projection error (actual negative).
- Top picks are overconfident by 2–3× (Fair predicted +5.7, actual +2.5).
- Biggest single error: the free agent you add in a 2-for-1 is over-projected (≈ −1.3 value), as in the optimizer. The partner's drop is under-projected (+2).

**Levers tried (2019–21, oracle, top pick per team-checkpoint).** Of these, only the robustness checks (rank by the average gain across four views) went to the hold-out.

| Lever | Result |
|---|---|
| Cap on predicted gain, min games for incoming players, extra value margin, your own value net, 1-for-1 only | Noise-level changes (±0.5 pts on n = 156) |
| Calibrated ranking (regression of actual gain on prediction + features, leave-one-season-out) | Better at predicting the average candidate (corr 0.30 vs 0.11) but worse top picks (Fleece +1.9 vs +5.1) |
| Robustness checks: four views (blend, real stats for players with ≥ 8 GP, preseason prior only, free agents −15%); worst-view floors; rank by worst or average | Small; averaging the four views was the most consistent, lifting the weakest season in both modes |

**Pre-registered final candidate:** mode rules on the blend, rank by the average gain across the four views. Pass = on 2022–23 your oracle gain > 0 with its CI clear of 0, frozen-replay wins > 0, Fair partner ≥ 0.

| Top pick per team-checkpoint | 2019–21 oracle (you) | 2019–21 frozen wins | **2022–23 oracle (you)** | **2022–23 frozen wins** | 2022–23 partner oracle |
|---|---|---|---|---|---|
| Fair, current | +2.48 [+1.28, +3.65] | +0.33 [+0.12, +0.55] | +0.03 [−1.70, +1.72] | +0.08 [−0.20, +0.38] | +1.64 |
| Fair, final | +2.61 [+1.49, +3.80] | +0.29 [+0.06, +0.53] | −0.09 [−1.75, +1.54] | +0.02 [−0.25, +0.29] | +1.67 |
| Fleece, current | +5.08 [+3.89, +6.27] | +0.52 [+0.26, +0.78] | +0.29 [−1.31, +1.88] | +0.08 [−0.20, +0.35] | +1.39 |
| Fleece, final | +5.38 [+4.25, +6.55] | +0.65 [+0.41, +0.89] | −0.20 [−1.87, +1.43] | +0.12 [−0.14, +0.38] | +1.43 |

**Verdict: fails the hold-out.** It worked on the tuning seasons and not on 2022–23; the partner keeps the value. The category-fit edge the model finds is real but smaller than player-projection error, so **better projections are the lever**. 2022–23 is now spent as a hold-out; further tuning against it would be self-deception.

## Next phase (started 2026-10-27)

1. **Fresh hold-out: 2024–2026.** ESPN's public endpoint (`/apis/v3/games/fba/seasons/{year}/players?view=kona_player_info`, no league needed) still serves those seasons' game logs (split 5) and season projections (`statSourceId=1`, ~400–460 players). Still to check: whether those projections are preseason or later snapshots. Our league's rosters on checkpoint dates come from Yahoo (roster by date). The oracle evaluation needs only checkpoint rosters + projections + game logs (no daily replay).
2. **Over-performer / projection model** (user idea, 2026-10-27): find early-season signals of players beating their preseason projection (minutes, shot volume, role changes, age), trained on 2019–23. Plug into both the trade finder and the optimizer.
3. Re-run the trade finder with the new projections. Judge once on 2024–26 with criteria written down beforehand.

## Earlier options (superseded by the user's choice of option 1)

1. **Winner's-curse guards, then re-backtest (recommended).** This is the same kind of fix that worked for the optimizer, where flattering projections were the main problem. Candidates:
   - require a bigger predicted gain;
   - shrink incoming players' projections toward replacement level by sample size;
   - only trade for players with enough real games this season;
   - add a safety margin to the value check so trades aren't tilted toward the partner.

   Tune on 2019–21, check once on 2022–23.
2. **Ship as a trade-idea generator** in Trade Hub, showing win-% changes as model estimates, with no claim that it improves standings.
3. **Narrow it:** only show trades made from week 8 on (the later checkpoints were mildly positive). Not statistically solid, though.

## Build plan

1. ~~`shared/trade_finder.py` + tests~~ (done 2026-10-27)
2. ~~Backtest~~ (done 2026-10-27; result above)
3. User picks an option above; if option 1, iterate + re-backtest.
4. `POST /league/trade_finder {team, password, give: [names], mode}` → `LeagueStore.trade_finder` (reuses `_optimizer_inputs()` and its cache), plus API tests.
5. Trade Hub UI per the user's guidance (frontend-design skill; desktop + mobile, both themes), premium-gated.
6. Measure on the droplet, then deploy.

## Code map and how to run

| File | Purpose |
|---|---|
| [`shared/trade_finder.py`](../shared/trade_finder.py) | The algorithm (`find_trades`, `TradeConfig`, `League`, `player_value`) |
| [`tests/test_trade_finder.py`](../tests/test_trade_finder.py) | 18 tests incl. brute-force equivalence |
| [`scripts/backtest_trade_finder.py`](../scripts/backtest_trade_finder.py) | Backtest (≈ 35 min locally for 5 seasons × 6 checkpoints) |
| [`prototypes/trade_finder_proto.py`](prototypes/trade_finder_proto.py) | The original throwaway prototype |

```sh
.venv-dashboard/bin/python -m pytest tests/test_trade_finder.py -q
# data: scp 'root@134.209.168.108:/srv/unisfantasy/data/backtest/*' <dir>; CompStats from /srv/unisfantasy/data/ref
.venv-dashboard/bin/python -m scripts.backtest_trade_finder --data <dir> --ref <ref dir> --out trades.csv
.venv-dashboard/bin/python -m scripts.backtest_trade_finder --data <dir> --ref <ref dir> --out trades.csv --summary-only
```
