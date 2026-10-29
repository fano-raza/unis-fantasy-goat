"""Rescore saved candidate trades with (a) corrected projections and (b)
pessimistic-for-you uncertainty discounts (incoming players down k*sd,
outgoing up k*sd, on counting stats and makes)."""
import sys, json, time, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd
from scripts import backtest_roster_optimizer as bt
from scripts.backtest_trade_finder import active_rosters
from shared import roster_optimizer as ro, trade_finder as tf, projection_adjust as pa
COMP = ro.COMPONENTS
PESS = ["FGM", "FTM", "3PTM", "REB", "AST", "STL", "BLK", "PTS"]  # lowered for incoming; TO/attempts untouched
KS = (0.25, 0.5, 1.0)
cand_path, data, ref, pub, params_path, out_path = sys.argv[1:7]
P = json.load(open(params_path))

def score_rows(lg, a, rows, Lin, Lout, Lcen, Lfa=None):
    """rows: DataFrame of candidates for team a. A's delta uses Lin for incoming,
    Lout for outgoing; partner uses central lines Lcen. Returns (n,2) scores."""
    n = len(rows); S = np.repeat(lg.sums[None], n, axis=0)
    sa = lg.scale[a]
    def L(frame, col):
        ids = rows[col]
        ok = ids.notna().to_numpy()
        out = np.zeros((n, len(COMP)))
        out[ok] = frame.loc[ids[ok].astype(int)].to_numpy()
        return out
    gin = L(Lin, "get") + L(Lin if Lfa is None else Lfa, "fa"); gout = L(Lout, "give1") + L(Lout, "give2")
    S[np.arange(n), a] += sa * (gin - gout)
    b_idx = rows["partner"].map(lg.idx).to_numpy()
    sb = lg.scale[b_idx][:, None]
    pin = L(Lcen, "give1") + L(Lcen, "give2"); pout = L(Lcen, "get") + L(Lcen, "drop")
    S[np.arange(n), b_idx] += sb * (pin - pout)
    # score only rows a and b: compute all teams once (n x teams) -- cheap enough
    sc, _ = lg.score(S, list(range(len(lg.teams))))
    return np.stack([sc[:, a], sc[np.arange(n), b_idx]], axis=1)

def run_year(year):
    c = pd.read_pickle(cand_path); c = c[c.year == year]
    s = bt.Season(year, Path(data), Path(ref))
    pg = pd.read_csv(Path(pub) / f"{year}_games.csv"); pproj = pd.read_csv(Path(pub) / f"{year}_projections.csv").set_index("PlayerId")
    prevp = Path(pub) / f"{year - 1}_games.csv"
    prev = pd.read_csv(prevp) if prevp.exists() else None
    key = str(year) if str(year) in P["coefs"] else "all"
    co = {k: np.array(v) for k, v in P["coefs"][key].items()}
    cfg = ro.recommended_config()
    outs = []
    for cp, cc in c.groupby("checkpoint"):
        t0 = time.time(); sp0 = int(s.week_start[cp])
        stats, projections = bt.checkpoint_inputs(s, sp0)
        rosters = active_rosters(s, sp0)
        allr = set(s.rosters.loc[s.rosters.ScoringPeriod == sp0, "PlayerId"].astype(int))
        fas = [p for p in stats.PlayerId if p not in allr]
        blend = ro.blend_players(stats, projections, ro.OptimizerConfig(), replacement_pool=pd.Index(fas), days_elapsed=sp0 - 1)
        win = pa.windows(pg, sp0, blend.index)
        last_mpg = None
        if prev is not None:
            lg_ = prev.groupby("PlayerId")[["MIN"]].sum()["MIN"] / prev.groupby("PlayerId").size()
            last_mpg = lg_
        prior_mpg = pproj["proj_MIN"].reindex(blend.index)
        if last_mpg is not None:
            prior_mpg = prior_mpg.fillna(last_mpg.reindex(blend.index))
        adj = pa.correct(blend, pa.features(blend, win, prior_mpg), co)
        sd = pa.uncertainty(adj, stats.set_index("PlayerId")["season_GP"], P["uncertainty"])
        avail = blend["availability"]
        cen_b = blend[COMP].mul(avail, axis=0); cen_a = adj[COMP].mul(avail, axis=0); sdl = sd[COMP].mul(avail, axis=0)
        lg_b = tf.League(blend, rosters, cfg); lg_a = tf.League(adj, rosters, cfg)
        base_b = lg_b.score(lg_b.sums, list(range(len(lg_b.teams))))[0]
        base_a = lg_a.score(lg_a.sums, list(range(len(lg_a.teams))))[0]
        res = pd.DataFrame(index=cc.index)
        for team, rows in cc.groupby("team"):
            a = lg_a.idx[team]; bidx = rows.partner.map(lg_a.idx).to_numpy()
            sc = score_rows(lg_a, a, rows, cen_a, cen_a, cen_a)
            res.loc[rows.index, "adj_gain"] = sc[:, 0] - base_a[a]; res.loc[rows.index, "adj_partner_gain"] = sc[:, 1] - base_a[bidx]
            for f_ in (0.7, 0.5):
                tw = rows[rows["shape"] == "2-for-1"]
                if len(tw):
                    bt_ = tw.partner.map(lg_a.idx).to_numpy()
                    sc = score_rows(lg_b, a, tw, cen_b, cen_b, cen_b, cen_b * f_)
                    res.loc[tw.index, f"fa{f_}_gain"] = sc[:, 0] - base_b[a]
                    sc = score_rows(lg_a, a, tw, cen_a, cen_a, cen_a, cen_a * f_)
                    res.loc[tw.index, f"adjfa{f_}_gain"] = sc[:, 0] - base_a[a]
            for k in ():
                pin = cen_b.copy(); pout = cen_b.copy()
                pin[PESS] = (cen_b[PESS] - k * sdl[PESS]).clip(lower=0); pout[PESS] = cen_b[PESS] + k * sdl[PESS]
                sc = score_rows(lg_b, a, rows, pin, pout, cen_b)
                res.loc[rows.index, f"lcb{k}_gain"] = sc[:, 0] - base_b[a]
                ain = cen_a.copy(); aout = cen_a.copy()  # (pessimism variants disabled in this pass)
                ain[PESS] = (cen_a[PESS] - k * sdl[PESS]).clip(lower=0); aout[PESS] = cen_a[PESS] + k * sdl[PESS]
                sc = score_rows(lg_a, a, rows, ain, aout, cen_a)
                res.loc[rows.index, f"adjlcb{k}_gain"] = sc[:, 0] - base_a[a]
        outs.append(res)
        print(f"  {year} week {cp}: {len(cc)} rows {time.time() - t0:.0f}s", flush=True)
    return pd.concat(outs)

if __name__ == "__main__":
    years = [int(y) for y in sys.argv[7].split(",")]
    with ProcessPoolExecutor(max_workers=len(years)) as ex:
        parts = list(ex.map(run_year, years))
    c = pd.read_pickle(cand_path); c = c[c.year.isin(years)]
    new = pd.concat(parts); c = c.join(new[[k for k in new.columns if k not in c.columns]]); c.to_pickle(out_path); print("done", len(c))
