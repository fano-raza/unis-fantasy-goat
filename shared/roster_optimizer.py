"""Roster Optimizer -- the "punt" free-agent optimizer (Phase 6 in
_planning/web-app-build-plan.md, where the design was agreed with the user).

For a target team:
  1. Project every player's per-game line by blending real season-to-date
     stats with a prior (ESPN's season projection + a little of last season),
     real stats weighted by games played: GP / (GP + k_games).
  2. Project every fantasy team's category values from its roster (counting
     stats summed; FG%/FT% as total makes / total attempts).
  3. Rate each category 0-1 across the league with the app's own min-max
     formula (shared/weighted_rank, TO inverted).
  4. Targets = the target team's 5 highest-rated categories, out of the 8
     it considers -- TO is ignored entirely by default (config.ignored_cats).
  5. Greedily apply the single drop/add (rostered player -> free agent) that
     most raises: sum(target ratings) + other_weight * sum(other considered
     ratings), until nothing helps or max_swaps is reached.

Pure pandas/numpy (no Models/ dependency) so dashboard_site's lightweight
venv can run it server-side once it reaches the app.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

MAIN_CATS = ["FG%", "FT%", "3PTM", "REB", "AST", "STL", "BLK", "TO", "PTS"]
NEG_CATS = {"TO"}
# Per-game components a player contributes. FG%/FT% are carried as makes and
# attempts so a roster's percentage is re-aggregated correctly.
COMPONENTS = ["FGM", "FGA", "FTM", "FTA", "3PTM", "REB", "AST", "STL", "BLK", "TO", "PTS"]
_COUNTING = ["3PTM", "REB", "AST", "STL", "BLK", "TO", "PTS"]
_IDX = {c: i for i, c in enumerate(COMPONENTS)}


@dataclass
class OptimizerConfig:
    # Recent form: the "real" part of the blend becomes (1 - w) x season-to-date
    # + w x the player's average over `recent_form_window` (when he played in
    # it). Fitted 2026-10-25 on player-level prediction error (dev 2019-2021,
    # confirmed on 2022-2023): ~20% of the last 14 days cuts next-2-weeks error
    # ~1.2% (role stats -- shot attempts, points -- most; steals/blocks are
    # noise); heavier weights hurt fast (last 7 days at 50% = +9% error).
    # None disables it.
    recent_form_window: str | None = None
    recent_form_weight: dict = field(default_factory=lambda: {
        "PTS": 0.3, "FGM": 0.3, "FGA": 0.3, "FTM": 0.2, "FTA": 0.2, "3PTM": 0.2,
        "REB": 0.2, "AST": 0.2, "STL": 0.1, "BLK": 0.1, "TO": 0.2})
    # Real-stat weight = GP / (GP + k), per component. Fitted 2026-10-24 by
    # player-level prediction error (blend vs actual rest-of-season per-game,
    # dev seasons 2019-2021, checkpoints weeks 5/10/15, players with >= 10
    # later games): stats stabilize at different rates -- PTS after ~3 games,
    # steals only after ~15. The original flat k=15 trusted ESPN's preseason
    # projection too long, and that projection systematically flatters free
    # agents (they're usually free agents because they've fallen short of it):
    # the top 40 FAs were over-projected by +0.47 PTS+REB+AST/g at k=15 vs
    # +0.11 at k=5. Makes/attempts share a k so percentages stay coherent. A
    # float applies one k to every component.
    k_games: float | dict = field(default_factory=lambda: {
        "PTS": 3.0, "FGM": 5.0, "FGA": 5.0, "FTM": 7.0, "FTA": 7.0, "3PTM": 5.0,
        "REB": 5.0, "AST": 5.0, "STL": 15.0, "BLK": 10.0, "TO": 7.0})
    # Share of the prior taken from last season's actuals (rest = ESPN
    # projection), scaled down further when last season's sample was small.
    last_season_weight: float = 0.2
    last_season_full_gp: float = 20.0
    # Categories the optimizer never sees: not a target, zero weight in both
    # variants, left out of results. TO by default -- the user has seen it
    # run inversely to overall team strength historically (more usage, more
    # turnovers), so optimizing for it would push the wrong way.
    ignored_cats: tuple[str, ...] = ("TO",)
    # Weight on the non-target (non-ignored) categories: 0 = full punt.
    other_weight: float = 0.0
    # Free agents with these ESPN injury statuses are never suggested: their
    # projections assume a healthy player (found in the first real-data run:
    # three of one team's six pickups were OUT).
    excluded_injury_statuses: tuple[str, ...] = ("OUT", "INJURY_RESERVE", "SUSPENSION")
    # Free agents not on any NBA roster (NBA team "FA") can't play at all --
    # the first real-data run kept suggesting unsigned players off last
    # season's stats.
    exclude_unsigned: bool = True
    # Season-long availability: every player's per-game line is scaled by
    # ESPN's projected games / season_games (Kyrie at 59 projected GP counts
    # ~72%). Replaced a flat 10% weight on rostered OUT players, which made
    # the optimizer cut injured stars (LeBron, Curry, ...) -- wrong for a
    # season-long tool when the injury is short (user decision, 2026-10-24).
    # Makes and attempts scale together, so FG%/FT% just carry less weight.
    use_availability: bool = True
    season_games: float = 82.0
    # Availability = blend of a prior (ESPN projected games / season_games, or
    # no_projection_availability for players ESPN doesn't project) and the
    # player's recent playing rate (games in the last `recent_window` divided
    # by the NBA games played in that span), the rate's weight ramping up to
    # recent_rate_weight once recent_full_days of the season have passed.
    # Fitted 2026-10-24 on dev seasons 2019-2021 (actual share of remaining
    # games played): FAs without a projection played 59% of remaining games
    # but were credited the pool median (82%) -- 14% of the optimizer's
    # pickups then never played again. Squared error vs the old availability:
    # rostered 0.054 -> 0.046, FAs with a projection 0.081 -> 0.065, FAs
    # without 0.137 -> 0.060.
    no_projection_availability: float = 0.60
    recent_window: str = "d30"
    recent_window_days: float = 30.0
    recent_rate_weight: float = 0.5
    recent_full_days: float = 28.0
    nba_games_per_day: float = 82.0 / 177.0
    # Final linear calibration (a + b x availability), fitted on the same dev
    # data: high estimates regress -- players rated 94-97% available actually
    # played ~80-82% of remaining games (injuries, rest), and the optimizer
    # was systematically picking those extremes (its adds played 13% fewer
    # games than projected; drops were on target). MSE 0.062 -> 0.055.
    # (0.0, 1.0) disables it.
    availability_calibration: tuple[float, float] = (0.065, 0.816)
    # Every team's totals are scaled to this roster size, so a 14th player
    # isn't a built-in counting-stat edge over 13-man teams. None = the
    # league's most common roster size.
    roster_size: int | None = None
    n_targets: int = 5
    # What the search maximizes:
    #   "ratings"        sum of target min-max ratings (+ other_weight x the
    #                    rest) -- the original design. Backtest 2026-10-24: no
    #                    standings gain; the rating saturates at 1.0 for the
    #                    league leader, so it trades away production margins.
    #   "category_wins"  same target/other weights, but each category scored as
    #                    the expected share of weekly matchups won in it vs each
    #                    opponent (margins count, with diminishing returns).
    #   "matchup_wins"   expected share of weekly matchups won (>= 5 of 9
    #                    categories), averaged over opponents. No targets needed.
    #   "standings"      0.5 x matchup_wins + 0.5 x expected share of the 9
    #                    categories won -- the league's W/L and category
    #                    standings, equally weighted (fixed a priori).
    #   "categories"     expected share of the 9 categories won only -- what
    #                    a Cats-format season's standings count (backtest:
    #                    _planning/roster-optimizer.md, 2026-10-28).
    # Ignored categories (TO) are a fixed 50/50 coin flip in every
    # probabilistic objective: they still count toward "5 of 9", but no swap
    # can change them.
    objective: str = "ratings"
    # Team week-to-week variability, measured from every recorded season's
    # CompStats (2019-2026 RS, median across seasons, 2026-10-24): coefficient
    # of variation for counting stats, absolute SD for percentages.
    weekly_cv: dict = field(default_factory=lambda: {
        "3PTM": 0.183, "REB": 0.136, "AST": 0.149, "STL": 0.201, "BLK": 0.247, "TO": 0.160, "PTS": 0.123})
    weekly_pct_sd: dict = field(default_factory=lambda: {"FG%": 0.0241, "FT%": 0.0365})
    cats_to_win: int = 5
    max_swaps: int = 14
    # Swaps gaining less than this aren't worth suggesting (user: "if it's a
    # tiny swap, it's not worth sharing"); the search stops there. Units are
    # the objective's own: "ratings"/"category_wins" sum up to 5 categories
    # (0.02 of one category), "matchup_wins"/"standings" are a 0-1 share
    # (min_gain_share = 1 percentage point of weekly win probability).
    min_gain: float = 0.02
    min_gain_share: float = 0.01


def recommended_config(**overrides) -> "OptimizerConfig":
    """The configuration the backtest supports (Phase 6, 2026-10-24): the
    `standings` objective (equal parts weekly matchup-win probability and
    expected category share), calibrated projections/availability (the
    defaults), re-run weekly with at most 2 swaps per week. Over 138 cases
    (2019-2023, checkpoints weeks 5/10/15, every team), weekly use vs standing
    pat: +0.73 matchup wins [95% CI +0.46, +1.01] and +3.2 category wins
    [+2.3, +4.1] per case, positive in all 5 seasons, and on the untouched
    2022-23 hold-out on par with the league's real managers. One-time swaps
    and the original min-max `ratings` objective showed no reliable gain."""
    return OptimizerConfig(**{"objective": "standings", "max_swaps": 2, **overrides})


# ---------------------------------------------------------------------------
# 1. Player projections
# ---------------------------------------------------------------------------

def _real_per_game(stats: pd.DataFrame, window: str) -> pd.DataFrame:
    """Real per-game components from Ref/player_stats.csv rows."""
    gp = pd.to_numeric(stats[f"{window}_GP"], errors="coerce").fillna(0)
    out = pd.DataFrame(index=stats.index)
    safe_gp = gp.where(gp > 0)
    out["FGM"] = pd.to_numeric(stats[f"{window}_FG%_made"], errors="coerce") / safe_gp
    out["FGA"] = pd.to_numeric(stats[f"{window}_FG%_att"], errors="coerce") / safe_gp
    out["FTM"] = pd.to_numeric(stats[f"{window}_FT%_made"], errors="coerce") / safe_gp
    out["FTA"] = pd.to_numeric(stats[f"{window}_FT%_att"], errors="coerce") / safe_gp
    for cat in _COUNTING:
        out[cat] = pd.to_numeric(stats[f"{window}_{cat}_avg"], errors="coerce")
    out.loc[gp <= 0] = np.nan
    return out[COMPONENTS], gp


def blend_players(
    stats: pd.DataFrame,
    projections: pd.DataFrame,
    config: OptimizerConfig | None = None,
    window: str = "season",
    replacement_pool: pd.Index | None = None,
    days_elapsed: float | None = None,
) -> pd.DataFrame:
    """One blended per-game line per player, indexed by PlayerId.

    stats: Ref/player_stats.csv rows (PlayerId, Player, {window}_* columns).
    projections: Ref/player_projections.csv rows (PlayerId, proj_*, last_*, last_GP).
    replacement_pool: PlayerIds whose projections define the replacement-level
      prior used for players with no projection and no last season (typically
      the free agents). Defaults to everyone with a projection.
    days_elapsed: days since the season started -- enables the recent
      playing-rate part of availability (needs a {recent_window}_GP column).

    Returns COMPONENTS columns plus Player, GP, w_real, prior ("proj",
    "proj+last", "last", "replacement").
    """
    config = config or OptimizerConfig()
    stats = stats.set_index("PlayerId")
    proj = projections.set_index("PlayerId").reindex(stats.index)

    real, gp = _real_per_game(stats, window)
    rw = config.recent_form_window
    if rw and f"{rw}_GP" in stats:
        recent, rgp = _real_per_game(stats, rw)
        played = (rgp > 0) & real.notna().all(axis=1) & recent.notna().all(axis=1)
        for c in COMPONENTS:
            a = config.recent_form_weight.get(c, 0.0)
            real.loc[played, c] = (1 - a) * real.loc[played, c] + a * recent.loc[played, c]

    def col(name: str) -> pd.Series:
        """A projections column as numbers; all-NaN if the export lacks it."""
        if name in proj:
            return pd.to_numeric(proj[name], errors="coerce")
        return pd.Series(np.nan, index=proj.index)

    proj_line = pd.DataFrame({c: col(f"proj_{c}") for c in COMPONENTS})
    last_line = pd.DataFrame({c: col(f"last_{c}") for c in COMPONENTS})
    has_proj = proj_line.notna().all(axis=1)
    has_last = last_line.notna().all(axis=1)

    last_gp = col("last_GP").fillna(0)
    w_last = config.last_season_weight * np.minimum(1.0, last_gp / config.last_season_full_gp)
    w_last = w_last.where(has_proj & has_last, 0.0)

    prior = proj_line.mul(1 - w_last, axis=0) + last_line.fillna(0).mul(w_last, axis=0)

    # Replacement level: the median projected line of the replacement pool.
    # Players with no prior at all get it outright -- otherwise a free agent's
    # single 30-point game would read as a star.
    pool = replacement_pool if replacement_pool is not None else proj_line.index[has_proj]
    pool = pool.intersection(proj_line.index[has_proj])
    replacement = proj_line.loc[pool].median() if len(pool) else proj_line[has_proj].median()
    no_prior = ~has_proj & ~has_last
    prior.loc[no_prior] = replacement.fillna(0).to_numpy()

    # No projection but a last season: trust last season in proportion to its
    # sample, shrinking the rest toward replacement level (a 6-game cameo
    # shouldn't count like a full season).
    last_only = ~has_proj & has_last
    # (If the pool had no projections at all, replacement is undefined: keep
    # last season unshrunk rather than turning the line into NaN.)
    trust = np.minimum(1.0, last_gp / config.last_season_full_gp)[last_only].to_numpy()[:, None]
    last_vals = last_line.loc[last_only].to_numpy()
    rep = np.where(np.isnan(replacement.to_numpy())[None, :], last_vals, replacement.to_numpy()[None, :])
    prior.loc[last_only] = trust * last_vals + (1 - trust) * rep

    k = config.k_games if isinstance(config.k_games, dict) else {c: config.k_games for c in COMPONENTS}
    has_real = real.notna().all(axis=1)
    w = pd.DataFrame({c: (gp / (gp + k[c])).where(has_real, 0.0) for c in COMPONENTS})
    blended = real.fillna(0) * w + prior * (1 - w)
    # Reported single number: the PTS weight (fastest-stabilizing stat).
    w_real = w["PTS"]

    out = blended[COMPONENTS].copy()
    out.insert(0, "Player", stats["Player"])
    out.insert(1, "NBATeam", stats["Team"].fillna("") if "Team" in stats else "")
    out["GP"] = gp
    out["w_real"] = w_real
    # Share of the season ESPN expects the player to play. No projection ->
    # the replacement pool's median availability.
    proj_gp = pd.to_numeric(proj["proj_GP"], errors="coerce") if "proj_GP" in proj else pd.Series(np.nan, index=proj.index)
    availability = (proj_gp / config.season_games).clip(0, 1).fillna(config.no_projection_availability)
    recent_col = f"{config.recent_window}_GP"
    if days_elapsed and days_elapsed > 0 and recent_col in stats:
        span = min(config.recent_window_days, days_elapsed)
        rate = (pd.to_numeric(stats[recent_col], errors="coerce").fillna(0) / (span * config.nba_games_per_day)).clip(0, 1)
        w_rate = config.recent_rate_weight * min(1.0, days_elapsed / config.recent_full_days)
        availability = (1 - w_rate) * availability + w_rate * rate
    a, b = config.availability_calibration
    out["availability"] = (a + b * availability).clip(0, 1)
    out["InjuryStatus"] = proj["InjuryStatus"].fillna("") if "InjuryStatus" in proj else ""
    out["prior"] = np.select(
        [has_proj & (w_last > 0), has_proj, has_last],
        ["proj+last", "proj", "last"],
        default="replacement",
    )
    return out


# ---------------------------------------------------------------------------
# 2-3. Team values and ratings
# ---------------------------------------------------------------------------

def category_values(component_sums: np.ndarray) -> np.ndarray:
    """(..., len(COMPONENTS)) component sums -> (..., 9) category values in
    MAIN_CATS order."""
    s = component_sums
    with np.errstate(invalid="ignore", divide="ignore"):
        fg = s[..., _IDX["FGM"]] / s[..., _IDX["FGA"]]
        ft = s[..., _IDX["FTM"]] / s[..., _IDX["FTA"]]
    cols = {"FG%": fg, "FT%": ft}
    for cat in _COUNTING:
        cols[cat] = s[..., _IDX[cat]]
    return np.stack([cols[c] for c in MAIN_CATS], axis=-1)


def _oriented(values: np.ndarray) -> np.ndarray:
    """Flip TO so higher is always better (matches weighted_rank's -x)."""
    sign = np.array([-1.0 if c in NEG_CATS else 1.0 for c in MAIN_CATS])
    return values * sign


def league_ratings(team_values: pd.DataFrame) -> pd.DataFrame:
    """Teams x MAIN_CATS values -> 0-1 ratings, same formula as
    weighted_rank.aggregate_rating (zero-variance category -> 0)."""
    v = _oriented(team_values[MAIN_CATS].to_numpy(dtype=float))
    lo, hi = v.min(axis=0), v.max(axis=0)
    span = hi - lo
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where(span > 0, (v - lo) / span, 0.0)
    return pd.DataFrame(r, index=team_values.index, columns=MAIN_CATS)


def roster_scale(
    rosters: dict[str, list], roster_size: int | None = None, unscaled: frozenset | set = frozenset()
) -> dict[str, float]:
    """Per-team multiplier that puts every team's totals on the same roster
    size (default: the league's most common size; ties -> the larger).
    Teams in `unscaled` keep their real totals (1.0) -- a hypothetical
    roster with a player removed must actually lose his stats."""
    sizes = [len(ids) for team, ids in rosters.items() if team not in unscaled]
    if roster_size is None:
        counts = pd.Series(sizes).value_counts()
        roster_size = int(max(counts[counts == counts.max()].index))
    return {team: 1.0 if team in unscaled else roster_size / len(ids) for team, ids in rosters.items()}


def team_component_sums(
    players: pd.DataFrame, rosters: dict[str, list], roster_size: int | None = None, unscaled: frozenset | set = frozenset()
) -> pd.DataFrame:
    """Each team's component totals, scaled to a common roster size."""
    scale = roster_scale(rosters, roster_size, unscaled)
    return pd.DataFrame(
        {team: players.loc[ids, COMPONENTS].sum().to_numpy() * scale[team] for team, ids in rosters.items()},
        index=COMPONENTS,
    ).T


# ---------------------------------------------------------------------------
# 4-5. Targets and greedy search
# ---------------------------------------------------------------------------

def considered_cats(config: OptimizerConfig) -> list[str]:
    return [c for c in MAIN_CATS if c not in config.ignored_cats]


def pick_targets(ratings: pd.Series, n: int = 5, candidates: list[str] | None = None) -> list[str]:
    """Top-n of `candidates` (default all MAIN_CATS) by rating; ties keep
    MAIN_CATS order."""
    candidates = candidates or MAIN_CATS
    order = sorted(candidates, key=lambda c: (-ratings[c], MAIN_CATS.index(c)))
    return order[:n]


@dataclass
class Swap:
    drop: object
    drop_name: str
    add: object
    add_name: str
    gain: float
    objective: float
    ratings: dict[str, float]
    # Weekly matchup-win probability (>= cats_to_win of 9, averaged over
    # opponents) after this swap; None under the "ratings" objective.
    matchup_win: float | None = None


@dataclass
class OptimizerResult:
    team: str
    targets: list[str]
    other_weight: float
    start_ratings: dict[str, float]
    start_objective: float
    swaps: list[Swap] = field(default_factory=list)
    start_matchup_win: float | None = None

    @property
    def end_ratings(self) -> dict[str, float]:
        return self.swaps[-1].ratings if self.swaps else self.start_ratings

    @property
    def end_objective(self) -> float:
        return self.swaps[-1].objective if self.swaps else self.start_objective


def _objective(ratings: np.ndarray, weights: np.ndarray) -> np.ndarray:
    return (ratings * weights).sum(axis=-1)


def normal_cdf(z: np.ndarray) -> np.ndarray:
    """Standard normal CDF via Abramowitz & Stegun 7.1.26 (|error| < 1.5e-7),
    vectorized -- keeps this module scipy-free."""
    x = np.asarray(z, dtype=float) / np.sqrt(2.0)
    t = 1.0 / (1.0 + 0.3275911 * np.abs(x))
    poly = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))))
    erf = np.sign(x) * (1.0 - poly * np.exp(-x * x))
    return 0.5 * (1.0 + erf)


def at_least_k(p: np.ndarray, k: int) -> np.ndarray:
    """P(at least k successes) for independent categories with win
    probabilities p (..., n_cats) -- Poisson-binomial DP."""
    # In place, and after c categories only counts 0..c can be non-zero --
    # same recurrence as before, without a fresh array per step (this was
    # half of a league-wide Trade Hub recommendation's run time).
    n = p.shape[-1]
    dist = np.zeros(p.shape[:-1] + (n + 1,))
    dist[..., 0] = 1.0
    for c in range(n):
        pc = p[..., c:c + 1]
        dist[..., 1:c + 2] = dist[..., 1:c + 2] * (1 - pc) + dist[..., 0:c + 1] * pc
        dist[..., 0:1] *= 1 - pc
    return dist[..., k:].sum(axis=-1)


def category_sigma(values: pd.DataFrame, config: "OptimizerConfig") -> np.ndarray:
    """Per-category weekly SD in the same units as the team values: CV x the
    league-average level for counting stats, absolute SD for percentages."""
    out = []
    for c in MAIN_CATS:
        if c in config.weekly_pct_sd:
            out.append(config.weekly_pct_sd[c])
        else:
            out.append(config.weekly_cv[c] * float(values[c].mean()))
    return np.array(out)


def win_probabilities(own: np.ndarray, others: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    """P(team beats each opponent in each category in a given week).
    own (..., 9), others (k, 9) -> (..., k, 9). The difference of two teams'
    weekly totals has SD sigma * sqrt(2)."""
    sign = np.array([-1.0 if c in NEG_CATS else 1.0 for c in MAIN_CATS])
    diff = (own[..., None, :] - others) * sign
    with np.errstate(invalid="ignore", divide="ignore"):
        p = normal_cdf(diff / (sigma * np.sqrt(2.0)))
    # Zero spread (e.g. a category nobody records): a plain win/loss/tie.
    step = np.where(diff > 0, 1.0, np.where(diff < 0, 0.0, 0.5))
    return np.where(sigma > 0, p, step)


def category_weights(targets: list[str], config: OptimizerConfig) -> np.ndarray:
    """Per-MAIN_CATS objective weight: 1 for targets, other_weight for the
    remaining considered categories, 0 for ignored ones."""
    return np.array(
        [1.0 if c in targets else 0.0 if c in config.ignored_cats else config.other_weight for c in MAIN_CATS]
    )


def optimize(
    team: str,
    players: pd.DataFrame,
    rosters: dict[str, list],
    free_agents: list,
    config: OptimizerConfig | None = None,
    targets: list[str] | None = None,
    unscaled_teams: frozenset | set = frozenset(),
    ignore_opponents: frozenset | set = frozenset(),
) -> OptimizerResult:
    """Greedy drop/add search for `team`. players = blend_players() output;
    rosters = every fantasy team -> PlayerIds; free_agents = PlayerIds
    available to add (anyone not on a roster). ignore_opponents = teams left
    out of the opponent average (e.g. ones the manager expects to beat
    anyway); category variability is still measured on the whole league."""
    config = config or OptimizerConfig()
    out_now = pd.Series(False, index=players.index)
    if "InjuryStatus" in players:
        out_now = players["InjuryStatus"].isin(config.excluded_injury_statuses)
    if config.use_availability and "availability" in players:
        players = players.copy()
        players[COMPONENTS] = players[COMPONENTS].astype(float).mul(players["availability"], axis=0)
    comps = players[COMPONENTS].to_numpy(dtype=float)
    pos = {pid: i for i, pid in enumerate(players.index)}

    sums = team_component_sums(players, rosters, config.roster_size, unscaled_teams)
    values = pd.DataFrame(category_values(sums.to_numpy()), index=sums.index, columns=MAIN_CATS)
    shown = considered_cats(config)
    mode = config.objective
    if mode not in ("ratings", "category_wins", "matchup_wins", "standings", "categories"):
        raise ValueError(f"unknown objective {mode!r}")

    others_raw = values.drop(index=[team, *(t for t in ignore_opponents if t in values.index and t != team)]).to_numpy()
    others = _oriented(others_raw)
    o_lo, o_hi = others.min(axis=0), others.max(axis=0)
    sigma = category_sigma(values, config)
    ignored = np.array([c in config.ignored_cats for c in MAIN_CATS])

    def rate(own_values: np.ndarray) -> np.ndarray:
        """Target team's ratings for candidate value rows (..., 9), against the
        fixed other teams -- its own value can extend the league min/max."""
        v = _oriented(own_values)
        lo, hi = np.minimum(o_lo, v), np.maximum(o_hi, v)
        span = hi - lo
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(span > 0, (v - lo) / span, 0.0)

    def probs(own_values: np.ndarray) -> np.ndarray:
        p = win_probabilities(own_values, others_raw, sigma)
        return np.where(ignored, 0.5, p)  # ignored cats: fixed coin flip

    def metric(own_values: np.ndarray) -> np.ndarray:
        """Per-category number reported to the user (..., 9): the min-max
        rating, or the expected share of weekly matchups won in it."""
        return rate(own_values) if mode == "ratings" else probs(own_values).mean(axis=-2)

    start_metric = pd.Series(metric(values.loc[team].to_numpy()), index=MAIN_CATS)
    targets = targets or pick_targets(start_metric, config.n_targets, shown)
    if any(c in config.ignored_cats for c in targets):
        raise ValueError(f"targets include an ignored category: {targets}")
    weights = category_weights(targets, config)
    min_gain = config.min_gain_share if mode in ("matchup_wins", "standings", "categories") else config.min_gain

    def matchup_win(own_values: np.ndarray) -> float | None:
        if mode == "ratings":
            return None
        return float(at_least_k(probs(own_values), config.cats_to_win).mean(axis=-1))

    def score(own_values: np.ndarray) -> np.ndarray:
        if mode in ("ratings", "category_wins"):
            return _objective(metric(own_values), weights)
        p = probs(own_values)                                   # (..., k, 9)
        matchup = at_least_k(p, config.cats_to_win).mean(axis=-1)
        if mode == "matchup_wins":
            return matchup
        if mode == "categories":
            return p.mean(axis=(-1, -2))
        return 0.5 * matchup + 0.5 * p.mean(axis=(-1, -2))

    roster = list(rosters[team])
    original = set(roster)
    # Free agents who can't actually play right now: injured, or unsigned.
    injured = set(players.index[out_now])
    if config.exclude_unsigned and "NBATeam" in players:
        injured |= set(players.index[players["NBATeam"] == "FA"])
    pool = [pid for pid in free_agents if pid in pos and pid not in original and pid not in injured]
    scale = roster_scale(rosters, config.roster_size, unscaled_teams)[team]
    team_sum = sums.loc[team].to_numpy(dtype=float)
    current = float(score(category_values(team_sum)))
    result = OptimizerResult(
        team=team,
        targets=targets,
        other_weight=config.other_weight,
        start_ratings={c: float(start_metric[c]) for c in shown},
        start_objective=current,
        start_matchup_win=matchup_win(category_values(team_sum)),
    )

    for _ in range(config.max_swaps):
        if not pool:
            break
        # Only the team's original players can be dropped: each swap is one
        # real move ("replace X with Y"), never "add Y" then later "drop Y".
        droppable = [p for p in roster if p in original]
        if not droppable:
            break
        drop_rows = comps[[pos[p] for p in droppable]]        # (r, 11)
        add_rows = comps[[pos[q] for q in pool]]               # (n, 11)
        cand = team_sum + scale * (add_rows[None, :, :] - drop_rows[:, None, :])  # (r, n, 11)
        scores = score(category_values(cand))
        i, j = np.unravel_index(np.nanargmax(scores), scores.shape)
        best = float(scores[i, j])
        if best - current <= min_gain:
            break
        drop, add = droppable[i], pool[j]
        team_sum = cand[i, j]
        roster[roster.index(drop)] = add
        pool.pop(j)  # an added player can't be added twice; dropped players never re-enter
        result.swaps.append(
            Swap(
                drop=drop,
                drop_name=str(players.at[drop, "Player"]),
                add=add,
                add_name=str(players.at[add, "Player"]),
                gain=best - current,
                objective=best,
                ratings={c: v for c, v in zip(MAIN_CATS, metric(category_values(team_sum)).tolist()) if c in shown},
                matchup_win=matchup_win(category_values(team_sum)),
            )
        )
        current = best
    return result
