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
    # Real-stat weight = GP / (GP + k_games): 2 GP -> 12%, 15 GP -> 50%.
    k_games: float = 15.0
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
    # Every team's totals are scaled to this roster size, so a 14th player
    # isn't a built-in counting-stat edge over 13-man teams. None = the
    # league's most common roster size.
    roster_size: int | None = None
    n_targets: int = 5
    max_swaps: int = 14
    # Swaps gaining less than this aren't worth suggesting (user: "if it's a
    # tiny swap, it's not worth sharing"); the search stops there.
    min_gain: float = 0.02


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
) -> pd.DataFrame:
    """One blended per-game line per player, indexed by PlayerId.

    stats: Ref/player_stats.csv rows (PlayerId, Player, {window}_* columns).
    projections: Ref/player_projections.csv rows (PlayerId, proj_*, last_*, last_GP).
    replacement_pool: PlayerIds whose projections define the replacement-level
      prior used for players with no projection and no last season (typically
      the free agents). Defaults to everyone with a projection.

    Returns COMPONENTS columns plus Player, GP, w_real, prior ("proj",
    "proj+last", "last", "replacement").
    """
    config = config or OptimizerConfig()
    stats = stats.set_index("PlayerId")
    proj = projections.set_index("PlayerId").reindex(stats.index)

    real, gp = _real_per_game(stats, window)
    proj_line = pd.DataFrame({c: pd.to_numeric(proj.get(f"proj_{c}"), errors="coerce") for c in COMPONENTS})
    last_line = pd.DataFrame({c: pd.to_numeric(proj.get(f"last_{c}"), errors="coerce") for c in COMPONENTS})
    has_proj = proj_line.notna().all(axis=1)
    has_last = last_line.notna().all(axis=1)

    last_gp = pd.to_numeric(proj.get("last_GP"), errors="coerce").fillna(0)
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

    w_real = (gp / (gp + config.k_games)).where(real.notna().all(axis=1), 0.0)
    blended = real.fillna(0).mul(w_real, axis=0) + prior.mul(1 - w_real, axis=0)

    out = blended[COMPONENTS].copy()
    out.insert(0, "Player", stats["Player"])
    out.insert(1, "NBATeam", stats["Team"].fillna("") if "Team" in stats else "")
    out["GP"] = gp
    out["w_real"] = w_real
    # Share of the season ESPN expects the player to play. No projection ->
    # the replacement pool's median availability.
    proj_gp = pd.to_numeric(proj["proj_GP"], errors="coerce") if "proj_GP" in proj else pd.Series(np.nan, index=proj.index)
    availability = (proj_gp / config.season_games).clip(0, 1)
    pool_avail = availability.reindex(pool).dropna()
    availability = availability.fillna(pool_avail.median() if len(pool_avail) else 1.0)
    out["availability"] = availability
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


def roster_scale(rosters: dict[str, list], roster_size: int | None = None) -> dict[str, float]:
    """Per-team multiplier that puts every team's totals on the same roster
    size (default: the league's most common size; ties -> the larger)."""
    sizes = [len(ids) for ids in rosters.values()]
    if roster_size is None:
        counts = pd.Series(sizes).value_counts()
        roster_size = int(max(counts[counts == counts.max()].index))
    return {team: roster_size / len(ids) for team, ids in rosters.items()}


def team_component_sums(players: pd.DataFrame, rosters: dict[str, list], roster_size: int | None = None) -> pd.DataFrame:
    """Each team's component totals, scaled to a common roster size."""
    scale = roster_scale(rosters, roster_size)
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


@dataclass
class OptimizerResult:
    team: str
    targets: list[str]
    other_weight: float
    start_ratings: dict[str, float]
    start_objective: float
    swaps: list[Swap] = field(default_factory=list)

    @property
    def end_ratings(self) -> dict[str, float]:
        return self.swaps[-1].ratings if self.swaps else self.start_ratings

    @property
    def end_objective(self) -> float:
        return self.swaps[-1].objective if self.swaps else self.start_objective


def _objective(ratings: np.ndarray, weights: np.ndarray) -> np.ndarray:
    return (ratings * weights).sum(axis=-1)


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
) -> OptimizerResult:
    """Greedy drop/add search for `team`. players = blend_players() output;
    rosters = every fantasy team -> PlayerIds; free_agents = PlayerIds
    available to add (anyone not on a roster)."""
    config = config or OptimizerConfig()
    out_now = pd.Series(False, index=players.index)
    if "InjuryStatus" in players:
        out_now = players["InjuryStatus"].isin(config.excluded_injury_statuses)
    if config.use_availability and "availability" in players:
        players = players.copy()
        players[COMPONENTS] = players[COMPONENTS].astype(float).mul(players["availability"], axis=0)
    comps = players[COMPONENTS].to_numpy(dtype=float)
    pos = {pid: i for i, pid in enumerate(players.index)}

    sums = team_component_sums(players, rosters, config.roster_size)
    values = pd.DataFrame(category_values(sums.to_numpy()), index=sums.index, columns=MAIN_CATS)
    start = league_ratings(values).loc[team]
    shown = considered_cats(config)
    targets = targets or pick_targets(start, config.n_targets, shown)
    if any(c in config.ignored_cats for c in targets):
        raise ValueError(f"targets include an ignored category: {targets}")
    weights = category_weights(targets, config)

    others = _oriented(values.drop(index=team).to_numpy())
    o_lo, o_hi = others.min(axis=0), others.max(axis=0)

    def rate(own_values: np.ndarray) -> np.ndarray:
        """Target team's ratings for candidate value rows (..., 9), against the
        fixed other teams -- its own value can extend the league min/max."""
        v = _oriented(own_values)
        lo, hi = np.minimum(o_lo, v), np.maximum(o_hi, v)
        span = hi - lo
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(span > 0, (v - lo) / span, 0.0)

    roster = list(rosters[team])
    original = set(roster)
    # Free agents who can't actually play right now: injured, or unsigned.
    injured = set(players.index[out_now])
    if config.exclude_unsigned and "NBATeam" in players:
        injured |= set(players.index[players["NBATeam"] == "FA"])
    pool = [pid for pid in free_agents if pid in pos and pid not in original and pid not in injured]
    scale = roster_scale(rosters, config.roster_size)[team]
    team_sum = sums.loc[team].to_numpy(dtype=float)
    current = float(_objective(rate(category_values(team_sum)), weights))
    result = OptimizerResult(
        team=team,
        targets=targets,
        other_weight=config.other_weight,
        start_ratings={c: float(start[c]) for c in shown},
        start_objective=current,
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
        scores = _objective(rate(category_values(cand)), weights)
        i, j = np.unravel_index(np.nanargmax(scores), scores.shape)
        best = float(scores[i, j])
        if best - current <= config.min_gain:
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
                ratings={c: v for c, v in zip(MAIN_CATS, rate(category_values(team_sum)).tolist()) if c in shown},
            )
        )
        current = best
    return result
