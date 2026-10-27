"""Projection adjustments on top of shared/roster_optimizer.blend_players
(research for the Trade Finder, _planning/trade-recommender.md):

1. `correct`: a per-stat linear correction of the blend's per-game line from
   role signals the blend doesn't use -- minutes and starts, season vs last
   14/30 days, season vs the preseason minutes expectation. Fitted on the
   clean-projection seasons (2018, 2019, 2021, 2022) by player-level
   rest-of-season error; leave-one-season-out it cuts per-game squared
   error 2-10% per stat (largest: STL, BLK, TO, PTS).
2. `uncertainty`: each player's per-game projection error SD per stat, as a
   function of games played so far -- what the trade finder needs to be
   conservative about players it acquires (the winner's curse: the best of
   ~1,500 noisy trades is usually one whose incoming player is
   over-projected).

Pure pandas/numpy.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

PARAMS_PATH = Path(__file__).with_name("projection_adjust_params.json")

COMP = ["FGM", "FGA", "FTM", "FTA", "3PTM", "REB", "AST", "STL", "BLK", "TO", "PTS"]
FEATURES = ["szn_minus_blend", "r14_minus_szn", "r30_minus_szn", "dmin_recent_x_rate", "dmin_prior_x_rate",
            "gs_change_x_b", "gp_frac", "szn_minus_blend_x_gp", "b", "c"]


def windows(games: pd.DataFrame, cp: int, universe: pd.Index) -> pd.DataFrame:
    """Season-to-date / last-14 / last-30-day totals (COMP + MIN + GS) and
    games, from per-game rows (PlayerId, ScoringPeriod, COMP, MIN, GS)
    before scoring period `cp`."""
    before = games[games["ScoringPeriod"] < cp]
    parts = []
    for prefix, g in (("szn", before), ("r14", before[before["ScoringPeriod"] >= cp - 14]),
                      ("r30", before[before["ScoringPeriod"] >= cp - 30])):
        agg = g.groupby("PlayerId")[COMP + ["MIN", "GS"]].sum().reindex(universe).fillna(0.0)
        agg.columns = [f"{prefix}_{c}" for c in agg.columns]
        agg[f"{prefix}_GP"] = g.groupby("PlayerId").size().reindex(universe).fillna(0.0)
        parts.append(agg)
    return pd.concat(parts, axis=1)


def features(blend: pd.DataFrame, win: pd.DataFrame, prior_mpg: pd.Series) -> dict[str, pd.DataFrame]:
    """Per-stat feature frames (FEATURES columns), indexed like blend."""
    w = win.reindex(blend.index)

    def pg(prefix, c):
        gp = w[f"{prefix}_GP"]
        return w[f"{prefix}_{c}"] / gp.where(gp > 0)

    szn_mpg, r14_mpg = pg("szn", "MIN"), pg("r14", "MIN")
    gs_szn, gs_r14 = pg("szn", "GS"), pg("r14", "GS")
    prior_mpg = prior_mpg.reindex(blend.index)
    out = {}
    for c in COMP:
        b = blend[c].astype(float)
        f = pd.DataFrame(index=blend.index)
        f["szn_minus_blend"] = (pg("szn", c) - b).fillna(0)
        f["r14_minus_szn"] = (pg("r14", c) - pg("szn", c)).fillna(0)
        f["r30_minus_szn"] = (pg("r30", c) - pg("szn", c)).fillna(0)
        rate = b / szn_mpg.where(szn_mpg > 0)
        f["dmin_recent_x_rate"] = ((r14_mpg - szn_mpg) * rate).fillna(0)
        f["dmin_prior_x_rate"] = ((szn_mpg - prior_mpg) * rate).fillna(0)
        f["gs_change_x_b"] = ((gs_r14 - gs_szn) * b).fillna(0)
        f["gp_frac"] = w["szn_GP"] / (w["szn_GP"] + 10)
        f["szn_minus_blend_x_gp"] = f["szn_minus_blend"] * f["gp_frac"]
        f["b"] = b
        f["c"] = 1.0
        out[c] = f[FEATURES]
    return out


def correct(blend: pd.DataFrame, feats: dict[str, pd.DataFrame], coefs: dict[str, np.ndarray]) -> pd.DataFrame:
    """blend + the fitted correction, per stat (never below 0; makes never
    above attempts)."""
    out = blend.copy()
    for c in COMP:
        out[c] = (blend[c].astype(float) + feats[c].to_numpy() @ coefs[c]).clip(lower=0)
    out["FGM"] = np.minimum(out["FGM"], out["FGA"])
    out["FTM"] = np.minimum(out["FTM"], out["FTA"])
    return out


def fit(rows: dict[str, pd.DataFrame], targets: dict[str, pd.Series], weights: pd.Series, lam: float = 10.0) -> dict[str, np.ndarray]:
    """Weighted ridge per stat: target = actual rest-of-season per-game -
    blend. rows[c] = features(...)[c] stacked over training checkpoints."""
    coefs = {}
    w = weights.to_numpy(dtype=float)
    for c in COMP:
        X, y = rows[c].to_numpy(dtype=float), targets[c].to_numpy(dtype=float)
        Xw = X * w[:, None]
        coefs[c] = np.linalg.solve(X.T @ Xw + lam * np.eye(X.shape[1]), Xw.T @ y)
    return coefs


# Projection error SD by games played so far: sd(gp) = a + b / sqrt(gp + 1),
# per stat, in per-game units scaled by the player's own line (relative SD
# with an absolute floor). Fitted with `fit_uncertainty`.
def uncertainty(blend: pd.DataFrame, gp: pd.Series, params: dict[str, tuple[float, float, float]]) -> pd.DataFrame:
    g = gp.reindex(blend.index).fillna(0).to_numpy(dtype=float)
    out = pd.DataFrame(index=blend.index)
    for c in COMP:
        rel_a, rel_b, floor = params[c]
        rel = rel_a + rel_b / np.sqrt(g + 1.0)
        out[c] = np.maximum(rel * blend[c].to_numpy(dtype=float), floor)
    return out


def fit_uncertainty(pred: dict[str, pd.Series], actual: dict[str, pd.Series], gp: pd.Series,
                    weights: pd.Series) -> dict[str, tuple[float, float, float]]:
    """Fit relative error SD = a + b/sqrt(gp+1) per stat by binning on games
    played; floor = the error SD among players projected under 1 per game
    of the stat's typical level (keeps tiny lines from getting ~0 SD)."""
    params = {}
    g = gp.to_numpy(dtype=float)
    w = weights.to_numpy(dtype=float)
    bins = [0, 1, 3, 6, 10, 15, 20, 30, 45, 90]
    for c in COMP:
        p, a = pred[c].to_numpy(dtype=float), actual[c].to_numpy(dtype=float)
        ok = p > np.nanpercentile(p, 25)
        xs, ys = [], []
        for lo, hi in zip(bins[:-1], bins[1:]):
            m = ok & (g >= lo) & (g < hi)
            if m.sum() < 30:
                continue
            rel = (a[m] - p[m]) / p[m]
            sd = np.sqrt(np.average(rel ** 2, weights=w[m]))
            xs.append(1 / np.sqrt((lo + hi) / 2 + 1))
            ys.append(sd)
        b, a0 = np.polyfit(xs, ys, 1)
        small = ~ok
        floor = float(np.sqrt(np.average((a[small] - p[small]) ** 2, weights=w[small]))) if small.any() else 0.0
        params[c] = (float(max(a0, 0.0)), float(max(b, 0.0)), floor)
    return params


def load_params(path: Path = PARAMS_PATH) -> dict:
    """The fitted coefficients (as arrays) and uncertainty parameters."""
    p = json.loads(Path(path).read_text())
    if p["features"] != FEATURES:
        raise ValueError("projection_adjust_params.json was fitted with a different feature list")
    return {"coefs": {c: np.array(v) for c, v in p["coefs"].items()},
            "uncertainty": {c: tuple(v) for c, v in p["uncertainty"].items()}}


def adjusted_players(blend: pd.DataFrame, games: pd.DataFrame, cp: int, prior_mpg: pd.Series,
                     params: dict | None = None) -> pd.DataFrame:
    """blend_players() output with the per-game lines corrected. games: this
    season's per-game rows (PlayerId, ScoringPeriod, COMP, MIN, GS);
    prior_mpg: preseason minutes expectation per player (ESPN projection,
    else last season)."""
    params = params or load_params()
    return correct(blend, features(blend, windows(games, cp, blend.index), prior_mpg), params["coefs"])
