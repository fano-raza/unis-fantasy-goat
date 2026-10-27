# Trade Recommender — scope

**Status (2026-10-27):** scoped, with a quick prototype run on live 2027 data. Nothing has been built and nothing is in the app. Open questions for the user are at the bottom.

Sister tool to the [Roster Optimizer](roster-optimizer.md). It uses the same player projections and the same team scoring, but searches trades with other managers instead of free-agent pickups.

---

## What it does

1. On the Roster page you pick the player(s) on your roster you'd trade away.
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

## Proposed design

### Acceptance rule (per candidate trade)

- **You:** gain ≥ +1 point (same bar as the optimizer's minimum swap).
- **Partner:** change ≥ −3 points (user's rule; adjustable).
- **Perceived value:** what the partner gives is not much more than what they receive in category-neutral value (threshold TBD; see questions).
- Each result gets a label: **Win-win** (partner ≥ +1), **Even** (−1 to +1), **Small ask** (−3 to −1).

**Default sort:** your gain. Alternatives: "fairest" (best result for the worse-off side) or "most likely accepted" (best partner change).

### Trade shapes (in build order)

| Mode | You pick | It searches | Size (per run) |
|---|---|---|---|
| 1-for-1 | 1 player | each single player on the 9 other rosters | ~120 trades — instant |
| 1-for-2 | 1 player | each pair on one other roster; you drop your least-valuable player | ~700 pairs × ~12 drops |
| 2-for-1 | 2 players | each single player; you add the best free agent, they drop their least-valuable | ~120 × ~12 drops × top-10–20 FAs |
| 2-for-2 | 2 players | each pair on one other roster | ~700 pairs |
| Later: sweetener | 1 player | also tries adding one more of your players to your side | ~12× the 1-for-X search |
| Later: reverse | a player on another team you want | what to give for him | same machinery, other direction |

Picking 1 or 2 players (and capping partner groups at 2, maybe 3) keeps every search to tens of thousands of candidates. That's well under a second vectorized, and it's light enough for the droplet (the prototype's slow 34 s run was a Python loop over all of Fano's possible pairs, not the per-pick search).

### Roster balancing for uneven trades

- The team receiving more players drops its least-valuable player, chosen by its own score.
- The team with an open spot adds the best healthy free agent, chosen by its own score from a top ~10–20 shortlist (same exclusions as the optimizer: injured OUT/IR/suspended, unsigned, inactive).
- Both moves are shown as part of the trade card ("Rohil drops Mikal Bridges · you add Ace Bailey").
- **Caveat:** part of a 2-for-1's gain is the free-agent pickup, which you might be able to make without the trade. The card should show the pickup's share separately (the optimizer can already score "pickup alone").

### Other rules carried over from the optimizer

- IR players: not tradeable in v1 (they're already out of active rosters).
- Roster-size scaling: same `roster_scale` as the optimizer; teams in an uneven trade keep their real roster count after balancing.
- Recent-form weighting: follows whatever the optimizer uses (currently off).

### Where it lives (proposal)

- **Roster page, premium-gated** (like the optimizer): a "Find trades" action. Tick one or two of your players, then hit Find trades.
- Results replace the roster table (same pattern as the optimizer). Each trade is a card:
  - you give / you get, with the partner team;
  - your win % before → after and theirs before → after;
  - the label;
  - which categories move;
  - roster-balancing moves, if any.
- Filters: partner team, trade shape, label. Each card links to **Trade Hub** for the side-by-side stat comparison.
- `POST /league/trade_finder {team, password, give: [names], shape?, partner_floor?}` → `LeagueStore.trade_finder`, sharing `_optimizer_inputs()` and its cache.

### Validation before shipping (same standard as the optimizer)

We can't test whether a manager would accept a trade, but we can test whether the trades the model likes actually help both teams. Using the existing backtest data (2019–2023, daily rosters + game logs, on the droplet at `/srv/unisfantasy/data/backtest/`):

1. At weekly checkpoints, generate each team's top recommended trades.
2. Apply each trade to both rosters and replay the rest of the season with the existing simulator.
3. Compare both teams' wins with and without the trade.
4. Compare against a "trade by projection value only" baseline.

This matters more here than it did for the optimizer: the optimizer's backtest showed most of its value came from the projections, not from category-aware scoring. Trades that help both sides are exactly the ones that rely on category fit. Tune on 2019–2021 and hold out 2022–2023, as before.

---

## Build plan (once the questions are answered)

1. `shared/trade_finder.py`: league-wide scoring, candidate generation per shape, roster balancing, acceptance rule, perceived-value check. Tests: brute-force checks against `optimize(max_swaps=0)` rescoring both rosters, as `tests/test_roster_optimizer.py` does.
2. Backtest script (`scripts/backtest_trade_finder.py`) on the existing data; write up results here.
3. Endpoint + `LeagueStore.trade_finder` + API tests.
4. Roster-page UI (frontend-design skill; desktop + mobile, both themes), premium-gated, Trade Hub link.
5. Measure on the droplet, then deploy.

## Questions for the user

1. **Perceived-value check:** hide lopsided trades, or show them with a warning? And how lopsided is too lopsided (e.g. the partner gives more than ~15–25% extra projection value)?
2. **Default sort:** your gain, or fairest/most-likely-accepted first?
3. **Uneven trades:** OK to auto-fill the open spot with the best free agent and auto-drop for the team that's over, shown on the card?
4. **Premium-gated** like the optimizer, and on the Roster page? Or its own spot (e.g. inside Trade Hub)?
5. **Backtest first** (recommended, ~1 session), or ship v1 1-for-1 behind premium and backtest after?
6. **Shapes for v1:** 1-for-1 + 2-for-1 + 1-for-2 first (2-for-2 next), with sweetener/reverse later?

## Prototype scripts

[`prototypes/trade_finder_proto.py`](prototypes/trade_finder_proto.py) — throwaway. Its core (the all-teams `scores()` function and the 1-for-1 / 2-for-1 loops) is the starting point for `shared/trade_finder.py`.
