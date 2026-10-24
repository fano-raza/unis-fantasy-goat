"""Backtests the Roster Optimizer (shared/roster_optimizer.py) on past ESPN
seasons: at week 5, 10 and 15 checkpoints, run it for every team using only
what was known that day, then replay the rest of the regular season and see
whether its swaps would have improved the team's final standings.

Data: scripts/export_backtest_data.py output (<year>_games/projections/
rosters/weeks.csv) + Ref/<year>_CompStats.csv for the real schedule and the
real pre-checkpoint results.

Simulation (identical rules for every team and scenario):
  - weeks before the checkpoint: the real recorded results (CompStats);
  - weeks from the checkpoint on: each team's daily roster, and each day the
    real game lines of up to 10 players who played (the league's 10 active
    slots), preferring higher checkpoint projections when more than 10 played.
    Opponents use their real daily rosters; the target team uses one of:
      stand_pat   its checkpoint roster, frozen
      full_punt   checkpoint roster + Full punt swaps
      balanced    checkpoint roster + Balanced swaps
      actual      its real daily rosters (what the manager actually did)
  - matchups over all 9 real categories (TO included -- that's how the
    league's standings work, even though the optimizer ignores TO).

Information available at a checkpoint: game rows before that day, ESPN's
stored season projection (2020/2023's are mid-season snapshots -- see Phase 6
in the build plan; included per the user), the prior season's real per-game
averages, rosters that day. ESPN has no historical injury status, so free
agents with no games in the 14 days before the checkpoint are treated as
unavailable (past information only).

  python -m scripts.backtest_roster_optimizer --data <dir> --ref <ref dir> --years 2019 2020 ...
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared import roster_optimizer as ro  # noqa: E402

COMP = ro.COMPONENTS
STAT_CATS = ["FG%", "FT%", "3PTM", "REB", "AST", "STL", "BLK", "TO", "PTS"]
CHECKPOINTS = (5, 10, 15)
ACTIVE_SLOTS = 10
BENCH_SLOTS = {12, 13}  # bench, IR
RECENT_DAYS = 14


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

class Season:
    def __init__(self, year: int, data: Path, ref: Path):
        self.year = year
        self.games = pd.read_csv(data / f"{year}_games.csv")
        self.proj = pd.read_csv(data / f"{year}_projections.csv")
        self.rosters = pd.read_csv(data / f"{year}_rosters.csv")
        self.weeks = pd.read_csv(data / f"{year}_weeks.csv")
        comp = pd.read_csv(ref / f"{year}_CompStats.csv")
        self.comp = comp[(comp["Season"] == "RS") & (comp["Count"].astype(str) == "True")].copy()
        self.rs_weeks = sorted(self.comp["Week"].unique())
        prev = data / f"{year - 1}_games.csv"
        self.prev_games = pd.read_csv(prev) if prev.exists() else None
        self.day_week = {sp: int(w.Week) for w in self.weeks.itertuples() for sp in range(w.StartSP, w.EndSP + 1)}
        self.games["Week"] = self.games["ScoringPeriod"].map(self.day_week)
        self.week_start = dict(zip(self.weeks["Week"], self.weeks["StartSP"]))
        self.teams = sorted(self.comp["Team"].unique())
        self.names = dict(zip(self.proj["PlayerId"], self.proj["Player"]))

    def roster_on(self, sp: int) -> dict[str, list]:
        day = self.rosters[self.rosters["ScoringPeriod"] == sp]
        return {t: day.loc[day["Team"] == t, "PlayerId"].astype(int).tolist() for t in self.teams}


# ---------------------------------------------------------------------------
# Player lines as of a checkpoint
# ---------------------------------------------------------------------------

def _per_game(games: pd.DataFrame) -> pd.DataFrame:
    agg = games.groupby("PlayerId")[COMP].sum()
    gp = games.groupby("PlayerId").size()
    return agg, gp


def checkpoint_inputs(s: Season, cutoff_sp: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(stats, projections) frames in the shapes blend_players expects, using
    only information from before `cutoff_sp`."""
    universe = sorted(set(s.games["PlayerId"]) | set(s.proj["PlayerId"]) | set(s.rosters["PlayerId"]))
    before = s.games[s.games["ScoringPeriod"] < cutoff_sp]
    totals, gp = _per_game(before)
    stats = pd.DataFrame({"PlayerId": universe})
    stats["Player"] = stats["PlayerId"].map(s.names).fillna(stats["PlayerId"].astype(str))
    stats["Team"] = ""  # no historical NBA team; recent-games proxy covers unsigned players
    g = gp.reindex(universe).fillna(0).to_numpy()
    t = totals.reindex(universe).fillna(0)
    stats["season_GP"] = g
    stats["d30_GP"] = before[before["ScoringPeriod"] >= cutoff_sp - 30].groupby("PlayerId").size().reindex(universe).fillna(0).to_numpy()
    stats["season_FG%_made"], stats["season_FG%_att"] = t["FGM"].to_numpy(), t["FGA"].to_numpy()
    stats["season_FT%_made"], stats["season_FT%_att"] = t["FTM"].to_numpy(), t["FTA"].to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        for cat in ["3PTM", "REB", "AST", "STL", "BLK", "TO", "PTS"]:
            stats[f"season_{cat}_avg"] = np.where(g > 0, t[cat].to_numpy() / np.where(g > 0, g, 1), np.nan)

    proj = s.proj.set_index("PlayerId").reindex(universe)
    projections = pd.DataFrame({"PlayerId": universe})
    for c in COMP:
        projections[f"proj_{c}"] = proj[f"proj_{c}"].to_numpy()
    projections["proj_GP"] = proj["proj_GP"].to_numpy()
    if s.prev_games is not None:
        ptot, pgp = _per_game(s.prev_games)
        pg = pgp.reindex(universe)
        for c in COMP:
            projections[f"last_{c}"] = (ptot[c].reindex(universe) / pg).to_numpy()
        projections["last_GP"] = pg.fillna(0).to_numpy()
    else:
        for c in COMP:
            projections[f"last_{c}"] = np.nan
        projections["last_GP"] = 0

    # Historical injury proxy: no games in the last RECENT_DAYS -> treated as
    # unavailable (never suggested as a pickup).
    recent = set(before.loc[before["ScoringPeriod"] >= cutoff_sp - RECENT_DAYS, "PlayerId"])
    projections["InjuryStatus"] = np.where(np.isin(universe, list(recent)), "ACTIVE", "OUT")
    return stats, projections


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def weekly_totals(s: Season, from_week: int, daily_roster: dict[int, list], priority: dict) -> pd.DataFrame:
    """One team's simulated totals for every RS week >= from_week.
    daily_roster: scoring period -> PlayerIds eligible that day."""
    g = s.games[s.games["Week"].isin([w for w in s.rs_weeks if w >= from_week])]
    rows = []
    for sp, day_games in g.groupby("ScoringPeriod"):
        eligible = day_games[day_games["PlayerId"].isin(daily_roster.get(sp, ()))]
        if len(eligible) > ACTIVE_SLOTS:
            order = eligible["PlayerId"].map(priority).fillna(-np.inf).sort_values(ascending=False)
            eligible = eligible.loc[order.index[:ACTIVE_SLOTS]]
        rows.append(eligible[COMP].sum().rename(s.day_week[sp]))
    if not rows:
        return pd.DataFrame(columns=COMP)
    return pd.DataFrame(rows).groupby(level=0).sum()


def real_daily(s: Season, team: str, from_sp: int) -> dict[int, list]:
    r = s.rosters[(s.rosters["Team"] == team) & (s.rosters["ScoringPeriod"] >= from_sp)
                  & ~s.rosters["LineupSlotId"].isin([13])]
    return {sp: grp["PlayerId"].astype(int).tolist() for sp, grp in r.groupby("ScoringPeriod")}


def frozen_daily(s: Season, roster: list, from_sp: int) -> dict[int, list]:
    last = int(s.weeks.loc[s.weeks["Week"] == max(s.rs_weeks), "EndSP"].iloc[0])
    return {sp: roster for sp in range(from_sp, last + 1)}


def cat_values(t: pd.Series) -> dict:
    out = {c: t[c] for c in ["3PTM", "REB", "AST", "STL", "BLK", "TO", "PTS"]}
    out["FG%"] = t["FGM"] / t["FGA"] if t["FGA"] else 0.0
    out["FT%"] = t["FTM"] / t["FTA"] if t["FTA"] else 0.0
    return out


def matchup(a: dict, b: dict) -> tuple[int, int, int]:
    w = l = d = 0
    for c in STAT_CATS:
        if np.isclose(a[c], b[c]):
            d += 1
        elif (a[c] < b[c]) if c == "TO" else (a[c] > b[c]):
            w += 1
        else:
            l += 1
    return w, l, d


def standings(s: Season, checkpoint: int, sim: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Final RS standings: real results before the checkpoint, simulated
    totals (sim[team] indexed by week) from it on."""
    rec = {t: dict(W=0, L=0, T=0, cW=0, cL=0, cT=0) for t in s.teams}
    real = s.comp.set_index(["Week", "Team"])
    for row in s.comp.itertuples():
        week, team, opp = row.Week, row.Team, row.Opp
        if week < checkpoint:
            a = cat_values(real.loc[(week, team)])
            b = cat_values(real.loc[(week, opp)])
        else:
            a = cat_values(sim[team].loc[week]) if week in sim[team].index else cat_values(pd.Series(0.0, index=COMP))
            b = cat_values(sim[opp].loc[week]) if week in sim[opp].index else cat_values(pd.Series(0.0, index=COMP))
        w, l, d = matchup(a, b)
        r = rec[team]
        r["cW"] += w; r["cL"] += l; r["cT"] += d
        r["W" if w > l else "L" if l > w else "T"] += 1
    df = pd.DataFrame(rec).T
    df["win_pct"] = (df["W"] + 0.5 * df["T"]) / (df["W"] + df["L"] + df["T"])
    df["cat_pct"] = (df["cW"] + 0.5 * df["cT"]) / (df["cW"] + df["cL"] + df["cT"])
    df["wl_rank"] = df["win_pct"].rank(ascending=False, method="min")
    df["cat_rank"] = df["cat_pct"].rank(ascending=False, method="min")
    return df


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------

def run_season(s: Season, variants: dict[str, ro.OptimizerConfig],
               blend_config: ro.OptimizerConfig | None = None,
               rolling: dict[str, ro.OptimizerConfig] | None = None,
               weekly_cap: int = 2) -> tuple[list[dict], list[dict]]:
    """variants: scenario label -> optimizer config (each is run and replayed
    against stand_pat and actual). blend_config: projection settings."""
    config = blend_config or ro.OptimizerConfig()
    results, calibration = [], []
    for cp in CHECKPOINTS:
        if cp not in s.week_start or cp > max(s.rs_weeks):
            continue
        sp0 = int(s.week_start[cp])
        stats, projections = checkpoint_inputs(s, sp0)
        rosters = s.roster_on(sp0)
        rostered = {p for ids in rosters.values() for p in ids}
        fas = [p for p in stats["PlayerId"] if p not in rostered]
        players = ro.blend_players(stats, projections, config, replacement_pool=pd.Index(fas), days_elapsed=sp0 - 1)
        priority = (players["PTS"] + 1.2 * players["REB"] + 1.5 * players["AST"]).to_dict()

        base = {t: weekly_totals(s, cp, real_daily(s, t, sp0), priority) for t in s.teams}
        if cp == CHECKPOINTS[0]:
            calibration.append(calibrate(s, cp, base))
        base_table = standings(s, cp, base)

        for team in s.teams:
            scenario_rosters = {"stand_pat": rosters[team]}
            swaps = {}
            for label, cfg in variants.items():
                res = ro.optimize(team, players, rosters, fas, cfg)
                roster = list(rosters[team])
                for sw in res.swaps:
                    roster[roster.index(sw.drop)] = sw.add
                scenario_rosters[label] = roster
                swaps[label] = res
            tables = {"actual": base_table}
            post = {"actual": base[team].sum()}
            rolling_swaps = {}
            for label, cfg in (rolling or {}).items():
                daily, n = rolling_roster(s, team, cp, cfg, config, weekly_cap)
                sim = dict(base)
                sim[team] = weekly_totals(s, cp, daily, priority)
                tables[label] = standings(s, cp, sim)
                post[label] = sim[team].sum()
                rolling_swaps[label] = n
            for label, roster in scenario_rosters.items():
                sim = dict(base)
                sim[team] = weekly_totals(s, cp, frozen_daily(s, roster, sp0), priority)
                tables[label] = standings(s, cp, sim)
                post[label] = sim[team].sum()
            for label, table in tables.items():
                r = table.loc[team]
                # Diagnostic: the team's real rest-of-season category production
                # in this scenario (did the targeted categories actually move?).
                pv = cat_values(post[label])
                results.append({
                    "year": s.year, "checkpoint": cp, "team": team, "scenario": label,
                    "targets": ",".join(swaps[label].targets) if label in swaps else "",
                    "n_swaps": len(swaps[label].swaps) if label in swaps else rolling_swaps.get(label, 0),
                    "swaps": "; ".join(f"{x.drop_name} -> {x.add_name}" for x in swaps[label].swaps) if label in swaps else "",
                    "W": r["W"], "L": r["L"], "T": r["T"], "win_pct": r["win_pct"], "wl_rank": r["wl_rank"],
                    "cW": r["cW"], "cL": r["cL"], "cT": r["cT"], "cat_pct": r["cat_pct"], "cat_rank": r["cat_rank"],
                    "n_teams": len(s.teams),
                    **{f"post_{c}": pv[c] for c in STAT_CATS},
                })
    return results, calibration


def rolling_roster(s: Season, team: str, cp: int, cfg: ro.OptimizerConfig, base_config: ro.OptimizerConfig,
                   weekly_cap: int) -> tuple[dict[int, list], int]:
    """Weekly re-optimization from checkpoint `cp` to the end of the regular
    season: at each week's first day, rerun the optimizer on that day's
    information (other teams' real rosters, the target's current roster) and
    apply at most `weekly_cap` swaps. Returns (day -> roster, total swaps).
    Approximation: a player the target picks up can still appear on another
    team's real roster later (no exclusivity across hypothetical moves)."""
    roster = list(s.roster_on(int(s.week_start[cp]))[team])
    daily: dict[int, list] = {}
    n_swaps = 0
    weeks = [w for w in s.rs_weeks if w >= cp]
    for w in weeks:
        sp = int(s.week_start[w])
        rosters = s.roster_on(sp)
        rosters[team] = list(roster)
        rostered = {p for ids in rosters.values() for p in ids}
        stats, projections = checkpoint_inputs(s, sp)
        fas = [p for p in stats["PlayerId"] if p not in rostered]
        players = ro.blend_players(stats, projections, base_config, replacement_pool=pd.Index(fas), days_elapsed=sp - 1)
        week_cfg = ro.OptimizerConfig(**{**cfg.__dict__, "max_swaps": weekly_cap})
        res = ro.optimize(team, players, rosters, fas, week_cfg)
        for sw in res.swaps:
            roster[roster.index(sw.drop)] = sw.add
        n_swaps += len(res.swaps)
        end = int(s.weeks.loc[s.weeks["Week"] == w, "EndSP"].iloc[0])
        for day in range(sp, end + 1):
            daily[day] = list(roster)
    return daily, n_swaps


def calibrate(s: Season, cp: int, sim: dict[str, pd.DataFrame]) -> dict:
    """How closely the lineup model reproduces real weekly totals when given
    the teams' real rosters (weeks >= cp)."""
    real = s.comp[s.comp["Week"] >= cp].set_index(["Week", "Team"])
    diffs, agree, n = [], 0, 0
    for row in s.comp[s.comp["Week"] >= cp].itertuples():
        if row.Week not in sim[row.Team].index or row.Week not in sim[row.Opp].index:
            continue
        real_pts = real.loc[(row.Week, row.Team), "PTS"]
        if real_pts <= 0 or real.loc[(row.Week, row.Opp), "PTS"] <= 0:
            continue  # blank rows in CompStats (e.g. 2019 week 20 Zahir is all zeros)
        diffs.append(sim[row.Team].loc[row.Week, "PTS"] / real_pts - 1)
        real_res = matchup(cat_values(real.loc[(row.Week, row.Team)]), cat_values(real.loc[(row.Week, row.Opp)]))
        sim_res = matchup(cat_values(sim[row.Team].loc[row.Week]), cat_values(sim[row.Opp].loc[row.Week]))
        agree += np.sign(real_res[0] - real_res[1]) == np.sign(sim_res[0] - sim_res[1])
        n += 1
    return {"year": s.year, "from_week": cp, "pts_bias_median": round(float(np.median(diffs)), 4), "matchup_agreement": agree / n if n else np.nan, "n": n}


def validate(s: Season) -> dict:
    """Data check: rebuild every team's REAL weekly totals from daily lineups
    (active slots only) + game rows + probed weeks, and compare with CompStats.
    2019 first run: points exact for 100% of team-weeks."""
    active = s.rosters[~s.rosters["LineupSlotId"].isin(BENCH_SLOTS)]
    m = s.games.merge(active[["Team", "ScoringPeriod", "PlayerId"]], on=["ScoringPeriod", "PlayerId"])
    tot = m.groupby(["Week", "Team"])[COMP].sum().reset_index()
    j = s.comp.merge(tot, on=["Week", "Team"], suffixes=("_real", "_ours"))
    j = j[j["PTS_real"] > 0]
    exact_pts = np.isclose(j["PTS_real"], j["PTS_ours"]).mean()
    exact_all = np.all([np.isclose(j[f"{c}_real"], j[f"{c}_ours"]) for c in COMP], axis=0).mean()
    return {"team_weeks": len(j), "pts_exact": round(float(exact_pts), 4), "all_stats_exact": round(float(exact_all), 4)}


# Named optimizer variants the backtest can run side by side.
VARIANTS = {
    "ratings_punt": lambda: ro.OptimizerConfig(objective="ratings", other_weight=0.0),
    "ratings_bal": lambda: ro.OptimizerConfig(objective="ratings", other_weight=0.25),
    "catwins_punt": lambda: ro.OptimizerConfig(objective="category_wins", other_weight=0.0),
    "catwins_bal": lambda: ro.OptimizerConfig(objective="category_wins", other_weight=0.25),
    "matchup": lambda: ro.OptimizerConfig(objective="matchup_wins"),
    "standings": lambda: ro.OptimizerConfig(objective="standings"),
    "standings_g02": lambda: ro.OptimizerConfig(objective="standings", min_gain_share=0.02),
    "standings_g03": lambda: ro.OptimizerConfig(objective="standings", min_gain_share=0.03),
    "matchup_g02": lambda: ro.OptimizerConfig(objective="matchup_wins", min_gain_share=0.02),
}

CLEAN_YEARS = {2019, 2021, 2022}  # preseason projections; 2020/2023 are mid-season snapshots


def bootstrap_ci(values: np.ndarray, n: int = 4000, seed: int = 0) -> tuple[float, float]:
    """95% percentile bootstrap CI of the mean."""
    rng = np.random.default_rng(seed)
    v = np.asarray(values, dtype=float)
    means = rng.choice(v, size=(n, len(v)), replace=True).mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def deltas(df: pd.DataFrame, scen: str) -> pd.DataFrame:
    key = ["year", "checkpoint", "team"]
    base = df[df["scenario"] == "stand_pat"].set_index(key)
    x = df[df["scenario"] == scen].set_index(key)
    return pd.DataFrame({
        "dW": x["W"] + 0.5 * x["T"] - (base["W"] + 0.5 * base["T"]),
        "dcW": x["cW"] + 0.5 * x["cT"] - (base["cW"] + 0.5 * base["cT"]),
        "d_wl_rank": base["wl_rank"] - x["wl_rank"],
        "d_cat_rank": base["cat_rank"] - x["cat_rank"],
        "n_swaps": x["n_swaps"],
    }).reset_index()


def headline(df: pd.DataFrame) -> str:
    """One line per scenario: mean change in matchup and category wins per
    case vs stand_pat, with 95% bootstrap CIs, and rank up/down shares."""
    out = []
    for scen in [s for s in df["scenario"].unique() if s != "stand_pat"]:
        d = deltas(df, scen)
        lo, hi = bootstrap_ci(d.dW.to_numpy())
        clo, chi = bootstrap_ci(d.dcW.to_numpy())
        out.append(f"  {scen:<26} n={len(d):3}  matchup wins {d.dW.mean():+.2f} [{lo:+.2f},{hi:+.2f}]"
                   f"  cat wins {d.dcW.mean():+.1f} [{clo:+.1f},{chi:+.1f}]"
                   f"  W/L rank up/down {(d.d_wl_rank > 0).mean():.0%}/{(d.d_wl_rank < 0).mean():.0%}"
                   f"  cat rank up/down {(d.d_cat_rank > 0).mean():.0%}/{(d.d_cat_rank < 0).mean():.0%}"
                   f"  swaps/case {d.n_swaps.mean():.1f}")
    return "\n".join(out)


def summarize(df: pd.DataFrame) -> str:
    """Each scenario vs stand_pat, per (year, checkpoint, team) case."""
    key = ["year", "checkpoint", "team"]
    base = df[df["scenario"] == "stand_pat"].set_index(key)
    lines = ["headline (95% bootstrap CIs):", headline(df)]
    for scen in [s for s in df["scenario"].unique() if s != "stand_pat"]:
        x = df[df["scenario"] == scen].set_index(key)
        d = pd.DataFrame({
            "dW": x["W"] + 0.5 * x["T"] - (base["W"] + 0.5 * base["T"]),
            "dcW": x["cW"] + 0.5 * x["cT"] - (base["cW"] + 0.5 * base["cT"]),
            "d_wl_rank": base["wl_rank"] - x["wl_rank"],    # + = moved up
            "d_cat_rank": base["cat_rank"] - x["cat_rank"],
        }).reset_index()
        d["clean"] = d["year"].isin(CLEAN_YEARS)

        def block(sub: pd.DataFrame, label: str) -> str:
            return (f"  {label:<22} n={len(sub):3}  matchup wins {sub.dW.mean():+.2f}/case  cat wins {sub.dcW.mean():+.1f}/case"
                    f"  | W/L rank up {(sub.d_wl_rank > 0).mean():4.0%} down {(sub.d_wl_rank < 0).mean():4.0%}"
                    f"  | cat rank up {(sub.d_cat_rank > 0).mean():4.0%} down {(sub.d_cat_rank < 0).mean():4.0%}")

        lines.append(f"\n{scen} vs stand_pat:")
        lines.append(block(d, "all"))
        for cp in sorted(d["checkpoint"].unique()):
            lines.append(block(d[d["checkpoint"] == cp], f"week {cp}"))
        lines.append(block(d[d["clean"]], "clean years 19/21/22"))
        lines.append(block(d[~d["clean"]], "snapshot years 20/23"))
        for y in sorted(d["year"].unique()):
            lines.append(block(d[d["year"] == y], str(y)))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--ref", type=Path, required=True)
    parser.add_argument("--years", type=int, nargs="+", required=True)
    parser.add_argument("--variants", nargs="+", default=["ratings_punt", "ratings_bal"],
                        help=f"named variants from VARIANTS: {', '.join(VARIANTS)}")
    parser.add_argument("--rolling", nargs="*", default=[],
                        help="variants to also run as weekly re-optimization (scenario 'rolling_<name>')")
    parser.add_argument("--weekly-cap", type=int, default=2)
    parser.add_argument("--out", type=Path, default=Path("backtest_results.csv"))
    args = parser.parse_args()

    variants = {name: VARIANTS[name]() for name in args.variants}
    rolling = {f"rolling_{name}": VARIANTS[name]() for name in args.rolling}
    all_results, all_cal = [], []
    for year in args.years:
        s = Season(year, args.data, args.ref)
        print(f"{year}: data validation {validate(s)}")
        res, cal = run_season(s, variants, rolling=rolling, weekly_cap=args.weekly_cap)
        all_results += res
        all_cal += cal
        print(f"{year}: {len(s.teams)} teams, {len(res)} rows; calibration {cal}")
    df = pd.DataFrame(all_results)
    df.to_csv(args.out, index=False)
    print(f"wrote {len(df)} rows to {args.out}")
    print(summarize(df))


if __name__ == "__main__":
    main()
