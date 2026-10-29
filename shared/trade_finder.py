"""Trade Finder -- trade recommendations scored like the Roster Optimizer
(_planning/trade-recommender.md; Phase 7 in _planning/web-app-build-plan.md).

For a team and the player(s) it's willing to trade away:
  1. Try every 1-for-1 (your player for one player on another roster) and
     every 2-for-1 (two of yours for one of theirs). In a 2-for-1 the partner
     is one over, so it drops the player whose loss hurts it least; you have
     an open spot, so you add the best healthy free agent for your team.
  2. Rescore BOTH teams with the optimizer's `standings` objective (half
     weekly matchup-win probability, half expected category share, averaged over
     every opponent, TO a fixed coin flip) against the league as it would be
     after the trade -- the two teams play each other too.
  3. Keep the trades that pass the mode's rule (user decisions, 2026-10-27):
       fair    you gain >= 1 point and the partner gains >= 1 point
       fleece  you gain >= 1 point and the partner loses at most 1 point
     (1 point = 0.01 of the score), and that don't look lopsided to the
     partner: what it receives (minus any player it has to drop) must be worth
     at least what it gives up, by a standard category-neutral 9-cat value --
     the model alone happily proposes trades no manager would accept (e.g.
     Hartenstein for LaMelo Ball, because LaMelo adds little in categories
     his team already wins). The user doesn't want those shown at all.
  4. Sort by your gain (user: the target team's benefit first).

Backtested configuration (2026-10-27, _planning/trade-recommender.md): the
defaults here plus projections corrected with shared/projection_adjust
(minutes/starts/recent-form correction on top of blend_players). On the
pre-registered 2024-26 hold-out the top recommendation gained the trading
team +0.29 matchup wins over the rest of the season (95% CI +0.08 to +0.52)
in both modes.

Pure pandas/numpy, like shared/roster_optimizer.py, so the backend's light
venv can run it.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from shared import roster_optimizer as ro

MODES = {
    # mode -> (your minimum gain, partner's minimum change)
    "fair": (0.01, 0.01),
    "fleece": (0.01, -0.01),
}


@dataclass
class TradeConfig:
    mode: str = "fair"
    shapes: tuple[str, ...] = ("1-for-1", "2-for-1")
    # The partner's net value received may fall short of what it gives up by
    # at most this much (9-cat z-score units; one rostered player's spread is
    # ~2.5-3 units). 0 = it must break even.
    value_tolerance: float = 0.0
    # Free agents considered to fill your open spot in a 2-for-1: the top N
    # healthy, signed free agents by player value, then the one best for your
    # team by the score.
    fa_shortlist: int = 15
    # Your score counts the free agent who fills your open spot in a 2-for-1
    # at this share of his projection. Backtest (2026-10-27): those pickups
    # came in 2-4 value points below projection in 4 of 5 seasons -- most
    # 2-for-1 "gains" were that phantom pickup. 0.7 passed the pre-registered
    # 2024-26 hold-out; 1.0 = take the projection at face value.
    fa_weight: float = 0.7
    max_results: int | None = 25
    # Override the mode's thresholds (score units; None = the mode's). Used by
    # the backtest's "any value-fair trade" control.
    min_gain: float | None = None
    partner_min_gain: float | None = None
    # Only search trades with these teams (None = every other team).
    partners: tuple[str, ...] | None = None
    optimizer: ro.OptimizerConfig = field(default_factory=ro.recommended_config)

    @property
    def thresholds(self) -> tuple[float, float]:
        if self.mode not in MODES:
            raise ValueError(f"unknown mode {self.mode!r}")
        you, partner = MODES[self.mode]
        return (you if self.min_gain is None else self.min_gain,
                partner if self.partner_min_gain is None else self.partner_min_gain)


@dataclass
class Trade:
    shape: str
    partner: str
    give: list            # your PlayerIds
    get: list             # partner's PlayerIds
    partner_drop: object | None  # 2-for-1: the partner's player released to make room
    fa_add: object | None        # 2-for-1: the free agent you add to fill your open spot
    gain: float           # your score change
    partner_gain: float
    score_after: float
    partner_score_after: float
    matchup_win_after: float
    partner_matchup_win_after: float
    value_give: float     # your side's player value (what the partner receives, before its drop)
    value_get: float      # the partner's side (what it gives up)
    partner_value_net: float  # partner's received value - its drop - what it gives up


@dataclass
class TradeResult:
    team: str
    mode: str
    give: list
    score: dict[str, float]          # every team's current score
    matchup_win: dict[str, float]
    trades: list[Trade]
    n_considered: int = 0
    n_rejected_lopsided: int = 0


# ---------------------------------------------------------------------------
# Player value (category-neutral, what a manager sees)
# ---------------------------------------------------------------------------

def player_value(lines: pd.DataFrame, reference: pd.Index) -> pd.Series:
    """Standard 9-cat fantasy value: sum of z-scores (TO negative; FG%/FT% as
    volume-weighted impact), means/SDs over `reference` (the rostered
    players). Same formula as scripts/backtest_weekly_strategies.zvalue (the
    "rank swap" baseline in the optimizer's backtest). `lines` should be the
    per-game lines x availability."""
    L = lines[ro.COMPONENTS].astype(float)
    ref = L.loc[L.index.intersection(reference)]
    fg = ref.FGM.sum() / ref.FGA.sum()
    ft = ref.FTM.sum() / ref.FTA.sum()
    cols = {"FGimp": L.FGM - fg * L.FGA, "FTimp": L.FTM - ft * L.FTA}
    rcols = {"FGimp": ref.FGM - fg * ref.FGA, "FTimp": ref.FTM - ft * ref.FTA}
    for c in ["3PTM", "REB", "AST", "STL", "BLK", "PTS"]:
        cols[c] = L[c]
        rcols[c] = ref[c]
    cols["TO"] = -L.TO
    rcols["TO"] = -ref.TO
    return sum((cols[c] - rcols[c].mean()) / rcols[c].std() for c in cols)


# ---------------------------------------------------------------------------
# League scoring with any number of teams changed at once
# ---------------------------------------------------------------------------

class League:
    """Every team's component totals plus a scorer that rescores chosen teams
    against the whole (hypothetical) league. Matches ro.optimize's
    `standings` objective exactly, including the category spreads, which are
    recomputed from each hypothetical league (as optimize would)."""

    def __init__(self, players: pd.DataFrame, rosters: dict[str, list], config: ro.OptimizerConfig):
        if config.objective not in ("standings", "categories"):
            raise ValueError("the trade finder scores with the `standings` or `categories` objective")
        self.config = config
        players = players.copy()
        if config.use_availability and "availability" in players:
            players[ro.COMPONENTS] = players[ro.COMPONENTS].astype(float).mul(players["availability"], axis=0)
        self.players = players
        self.comps = players[ro.COMPONENTS].astype(float)
        self.rosters = {t: list(ids) for t, ids in rosters.items()}
        self.teams = list(self.rosters)
        self.idx = {t: i for i, t in enumerate(self.teams)}
        scale = ro.roster_scale(self.rosters, config.roster_size)
        self.scale = np.array([scale[t] for t in self.teams])
        self.sums = np.stack([self.comps.loc[self.rosters[t]].sum().to_numpy() * scale[t] for t in self.teams])
        self.sign = np.array([-1.0 if c in ro.NEG_CATS else 1.0 for c in ro.MAIN_CATS])
        self.ignored = np.array([c in config.ignored_cats for c in ro.MAIN_CATS])
        self.is_pct = np.array([c in config.weekly_pct_sd for c in ro.MAIN_CATS])
        self.pct_sd = np.array([config.weekly_pct_sd.get(c, 0.0) for c in ro.MAIN_CATS])
        self.cv = np.array([config.weekly_cv.get(c, 0.0) for c in ro.MAIN_CATS])

    def line(self, pids) -> np.ndarray:
        return self.comps.loc[list(pids)].to_numpy().sum(axis=0)

    def score(self, S: np.ndarray, rows: list[int]) -> tuple[np.ndarray, np.ndarray]:
        """S (..., n_teams, 11) component sums -> (score, matchup_win), each
        (..., len(rows)), for the teams at `rows`, each vs every other team."""
        V = ro.category_values(S)                                     # (..., n, 9)
        sigma = np.where(self.is_pct, self.pct_sd, self.cv * V.mean(axis=-2))[..., None, :]  # (..., 1, 9)
        n = V.shape[-2]
        scores, matchups = [], []
        for r in rows:
            others = [j for j in range(n) if j != r]
            diff = (V[..., r:r + 1, :] - V[..., others, :]) * self.sign  # (..., n-1, 9)
            with np.errstate(invalid="ignore", divide="ignore"):
                p = ro.normal_cdf(diff / (sigma * np.sqrt(2.0)))
            step = np.where(diff > 0, 1.0, np.where(diff < 0, 0.0, 0.5))
            p = np.where(sigma > 0, p, step)
            p = np.where(self.ignored, 0.5, p)
            m = ro.at_least_k(p, self.config.cats_to_win).mean(axis=-1)
            share = p.mean(axis=(-1, -2))
            scores.append(share if self.config.objective == "categories" else 0.5 * m + 0.5 * share)
            matchups.append(m)
        return np.stack(scores, axis=-1), np.stack(matchups, axis=-1)

    def category_probs(self, S: np.ndarray, row: int) -> np.ndarray:
        """(..., 9) the team at `row`'s chance of winning each category in a
        typical week, averaged over every other team (ignored categories:
        0.5) -- the per-category numbers the app shows."""
        V = ro.category_values(S)
        sigma = np.where(self.is_pct, self.pct_sd, self.cv * V.mean(axis=-2))[..., None, :]
        others = [j for j in range(V.shape[-2]) if j != row]
        diff = (V[..., row:row + 1, :] - V[..., others, :]) * self.sign
        with np.errstate(invalid="ignore", divide="ignore"):
            p = ro.normal_cdf(diff / (sigma * np.sqrt(2.0)))
        p = np.where(sigma > 0, p, np.where(diff > 0, 1.0, np.where(diff < 0, 0.0, 0.5)))
        return np.where(self.ignored, 0.5, p).mean(axis=-2)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def _fa_shortlist(league: League, free_agents: list, values: pd.Series, n: int) -> list:
    cfg = league.config
    p = league.players
    ok = []
    for pid in free_agents:
        if pid not in p.index or pid not in values.index:
            continue
        if "InjuryStatus" in p and p.at[pid, "InjuryStatus"] in cfg.excluded_injury_statuses:
            continue
        if cfg.exclude_unsigned and "NBATeam" in p and p.at[pid, "NBATeam"] == "FA":
            continue
        ok.append(pid)
    return sorted(ok, key=lambda q: -values[q])[:n]


def find_trades(
    team: str,
    give: list,
    players: pd.DataFrame,
    rosters: dict[str, list],
    free_agents: list,
    config: TradeConfig | None = None,
) -> TradeResult:
    """Trades for `team` that send away `give` (1 or 2 of its PlayerIds).
    One player picked -> 1-for-1 trades for him, plus 2-for-1s pairing him
    with each of your other players. Two picked -> 2-for-1s for exactly
    that pair. None picked (empty list) -> any of your players: every
    1-for-1 and every 2-for-1 pair, in one pass (the Trade Hub's
    "recommend" without picks). players = ro.blend_players() output; rosters = ACTIVE rosters
    (PlayerIds) for every team; free_agents = PlayerIds on no roster."""
    config = config or TradeConfig()
    min_you, min_partner = config.thresholds
    give = list(give)
    if team not in rosters:
        raise KeyError(f"unknown team {team!r}")
    if len(give) > 2 or any(p not in rosters[team] for p in give):
        raise ValueError("give must be 0-2 players on the team's active roster")

    league = League(players, rosters, config.optimizer)
    a = league.idx[team]
    base_score, base_match = league.score(league.sums, list(range(len(league.teams))))
    rostered = pd.Index([p for ids in rosters.values() for p in ids])
    values = player_value(league.comps, rostered)
    val = lambda pids: float(sum(values.get(p, 0.0) for p in pids))  # noqa: E731

    result = TradeResult(
        team=team, mode=config.mode, give=give,
        score={t: float(base_score[league.idx[t]]) for t in league.teams},
        matchup_win={t: float(base_match[league.idx[t]]) for t in league.teams},
        trades=[],
    )
    trades: list[Trade] = []

    def consider(shape, B, gv, gt, drop, fa, sc, mw):
        b = league.idx[B]
        result.n_considered += 1
        gain, pgain = float(sc[0] - base_score[a]), float(sc[1] - base_score[b])
        if gain < min_you or pgain < min_partner:
            return
        v_give, v_get = val(gv), val(gt)
        net = v_give - (values.get(drop, 0.0) if drop is not None else 0.0) - v_get
        if net < -config.value_tolerance:
            result.n_rejected_lopsided += 1
            return
        trades.append(Trade(shape, B, list(gv), list(gt), drop, fa, gain, pgain, float(sc[0]), float(sc[1]),
                            float(mw[0]), float(mw[1]), v_give, v_get, net))

    sa = league.scale[a]
    partners = [t for t in league.teams if t != team and (config.partners is None or t in config.partners)]

    singles = list(give) if len(give) == 1 else list(league.rosters[team]) if not give else []
    if "1-for-1" in config.shapes:
        for xid in singles:
            x = league.line([xid])
            for B in partners:
                b, sb = league.idx[B], league.scale[league.idx[B]]
                ys = league.rosters[B]
                Y = league.comps.loc[ys].to_numpy()                     # (k, 11)
                S = np.repeat(league.sums[None], len(ys), axis=0)
                S[:, a] += sa * (Y - x)
                S[:, b] += sb * (x - Y)
                sc, mw = league.score(S, [a, b])
                for k, y in enumerate(ys):
                    consider("1-for-1", B, [xid], [y], None, None, sc[k], mw[k])

    if "2-for-1" in config.shapes:
        if len(give) == 2:
            pairs = [tuple(give)]
        elif len(give) == 1:
            pairs = [(give[0], t) for t in league.rosters[team] if t != give[0]]
        else:
            pairs = list(itertools.combinations(league.rosters[team], 2))
        fas = _fa_shortlist(league, free_agents, values, config.fa_shortlist)
        if fas and pairs:
            F = league.comps.loc[fas].to_numpy()                     # (f, 11)
            # Chunks of pairs keep the (pairs x partner players x drops x
            # teams x stats) arrays small -- "any player" searches all ~78
            # pairs of a 13-man roster on a memory-tight server.
            all_pairs = pairs
            for c0 in range(0, len(all_pairs), 16):
                pairs = all_pairs[c0:c0 + 16]
                X = np.stack([league.line(pair) for pair in pairs])      # (P, 11)
                for B in partners:
                    b, sb = league.idx[B], league.scale[league.idx[B]]
                    ys = league.rosters[B]
                    Y = league.comps.loc[ys].to_numpy()                  # (k, 11)
                    # S0[p, k]: league after pair p goes to B for B's player k
                    S0 = np.broadcast_to(league.sums, (len(pairs), len(ys)) + league.sums.shape).copy()
                    S0[:, :, a] += sa * (Y[None] - X[:, None])
                    S0[:, :, b] += sb * (X[:, None] - Y[None])
                    # 1) the partner releases whoever costs it least (any of its
                    #    remaining players; drop d == k is "dropping" the traded one -> masked)
                    SD = np.repeat(S0[:, :, None], len(ys), axis=2)       # (P, k, d, n, 11)
                    SD[:, :, :, b] -= sb * Y[None, None]
                    bsc, _ = league.score(SD, [b])
                    bsc = bsc[..., 0]
                    bsc[:, np.arange(len(ys)), np.arange(len(ys))] = -np.inf
                    drop_i = np.argmax(bsc, axis=2)                       # (P, k)
                    S1 = S0.copy()
                    S1[:, :, b] -= sb * Y[drop_i]
                    # 2) you fill the open spot with the free agent best for you,
                    #    counted at fa_weight of his projection for YOUR score
                    #    only; the partner is scored against your team with the
                    #    pickup at face value (what the backtest validated)
                    SF = np.repeat(S1[:, :, None], len(fas), axis=2)      # (P, k, f, n, 11)
                    SF[:, :, :, a] += sa * F[None, None] * config.fa_weight
                    sc, mw = league.score(SF, [a])                       # (P, k, f, 1)
                    fa_j = np.argmax(sc[..., 0], axis=2)                  # (P, k)
                    S2 = S1.copy()
                    S2[:, :, a] += sa * F[fa_j]
                    psc, pmw = league.score(S2, [b])                     # (P, k, 1)
                    for pi, pair in enumerate(pairs):
                        for k, y in enumerate(ys):
                            j = fa_j[pi, k]
                            consider("2-for-1", B, list(pair), [y], ys[drop_i[pi, k]], fas[j],
                                     (sc[pi, k, j, 0], psc[pi, k, 0]), (mw[pi, k, j, 0], pmw[pi, k, 0]))

    trades.sort(key=lambda t: (-t.gain, -t.partner_gain))
    # One card per (what you give, what you get): already unique by construction.
    result.trades = trades[: config.max_results] if config.max_results else trades
    return result
