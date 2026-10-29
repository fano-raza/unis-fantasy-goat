"""Rescore saved candidate trades under the categories-only objective:
model view (corrected projections; free agent x0.7 for your side) and the
oracle (actual rest-of-season production)."""
import sys, json, time, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd
from scripts import backtest_roster_optimizer as bt
from scripts.backtest_trade_finder import active_rosters
from scripts.trade_finder_tuning import oracle_lines
from shared import roster_optimizer as ro, trade_finder as tf, projection_adjust as pa
COMP = ro.COMPONENTS
# score_rows(lg, a, rows, Lin, Lout, Lcen, Lfa=None) from rescore_fa.py
_src = open(Path(__file__).with_name("rescore_fa.py")).read()
exec("def score_rows" + _src.split("def score_rows")[1].split("def run_year")[0])
cand_path, data, ref, pub, params_path, out_path = sys.argv[1:7]
P = json.load(open(params_path))
CAT = ro.recommended_config(objective="categories")
ORC = ro.recommended_config(objective="categories", use_availability=False)

def run_year(year):
    c = pd.read_pickle(cand_path); c = c[c.year == year]
    s = bt.Season(year, Path(data), Path(ref))
    pg = pd.read_csv(Path(pub) / f"{year}_games.csv"); pproj = pd.read_csv(Path(pub) / f"{year}_projections.csv").set_index("PlayerId")
    prevp = Path(pub) / f"{year - 1}_games.csv"
    last_mpg = None
    if prevp.exists():
        prev = pd.read_csv(prevp); last_mpg = prev.groupby("PlayerId")["MIN"].sum() / prev.groupby("PlayerId").size()
    co = {k: np.array(v) for k, v in P["coefs"][str(year) if str(year) in P["coefs"] else "all"].items()}
    outs = []
    for cp, cc in c.groupby("checkpoint"):
        t0 = time.time(); sp0 = int(s.week_start[cp])
        stats, projections = bt.checkpoint_inputs(s, sp0)
        rosters = active_rosters(s, sp0)
        allr = set(s.rosters.loc[s.rosters.ScoringPeriod == sp0, "PlayerId"].astype(int))
        fas = [p for p in stats.PlayerId if p not in allr]
        blend = ro.blend_players(stats, projections, ro.OptimizerConfig(), replacement_pool=pd.Index(fas), days_elapsed=sp0 - 1)
        prior = pproj["proj_MIN"].reindex(blend.index)
        if last_mpg is not None: prior = prior.fillna(last_mpg.reindex(blend.index))
        adj = pa.correct(blend, pa.features(blend, pa.windows(pg, sp0, blend.index), prior), co)
        cen = adj[COMP].mul(blend["availability"], axis=0)
        lg = tf.League(adj, rosters, CAT); base = lg.score(lg.sums, list(range(len(lg.teams))))[0]
        olines = oracle_lines(s, sp0, blend.index)
        olg = tf.League(olines, rosters, ORC); obase = olg.score(olg.sums, list(range(len(olg.teams))))[0]
        ocomp = olg.comps
        res = pd.DataFrame(index=cc.index)
        for team, rows in cc.groupby("team"):
            a = lg.idx[team]; bidx = rows.partner.map(lg.idx).to_numpy()
            sc = score_rows(lg, a, rows, cen, cen, cen, cen * 0.7)
            res.loc[rows.index, "cat_gain"] = sc[:, 0] - base[a]
            sc = score_rows(lg, a, rows, cen, cen, cen)
            res.loc[rows.index, "cat_partner_gain"] = sc[:, 1] - base[bidx]
            sc = score_rows(olg, a, rows, ocomp, ocomp, ocomp)
            res.loc[rows.index, "orc_cat_gain"] = sc[:, 0] - obase[a]
            res.loc[rows.index, "orc_cat_partner_gain"] = sc[:, 1] - obase[bidx]
        outs.append(res); print(f"  {year} week {cp}: {time.time() - t0:.0f}s", flush=True)
    return pd.concat(outs)

if __name__ == "__main__":
    years = [int(y) for y in sys.argv[7].split(",")]
    with ProcessPoolExecutor(max_workers=len(years)) as ex:
        parts = list(ex.map(run_year, years))
    c = pd.read_pickle(cand_path); c = c[c.year.isin(years)]
    c.join(pd.concat(parts)).to_pickle(out_path); print("done")
