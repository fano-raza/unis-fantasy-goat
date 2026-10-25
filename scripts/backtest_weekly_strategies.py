"""Weekly-from-week-1 strategy comparison for the Roster Optimizer
(_planning/roster-optimizer.md, "Weekly use from week 1"): every team-season
2019-2023 starts from its post-draft roster and re-runs a strategy every week:

  optimizer / optimizer3   recommended_config(), up to 2 / 3 swaps a week
  rank_proj / rank_proj3   swap the roster's lowest-valued player for the
                           highest-valued free agent (9-cat z-score of the
                           optimizer's own projections x availability)
  rank_season              same, valued on season-to-date per-game stats
                           (>= 3 games) -- what ESPN's player list shows
  stand_pat                drafted roster all season
  actual                   the manager's real moves

Usage (from the repo root):
  python -m scripts.backtest_weekly_strategies <backtest data dir> <ref dir> <out.csv>
"""
import sys, numpy as np, pandas as pd
from pathlib import Path
sys.path.insert(0, ".")
from scripts import backtest_roster_optimizer as bt
from shared import roster_optimizer as ro
data, ref = Path(sys.argv[1]), Path(sys.argv[2])
COMP=ro.COMPONENTS

def zvalue(lines: pd.DataFrame, reference: pd.Index) -> pd.Series:
    """Standard 9-cat fantasy value: sum of z-scores (TO negative; FG%/FT% as
    volume-weighted impact), means/SDs over the currently rostered players."""
    L=lines[COMP].astype(float)
    ref=L.loc[L.index.intersection(reference)]
    fg=ref.FGM.sum()/ref.FGA.sum(); ft=ref.FTM.sum()/ref.FTA.sum()
    cols={"FGimp":L.FGM-fg*L.FGA, "FTimp":L.FTM-ft*L.FTA}
    rcols={"FGimp":ref.FGM-fg*ref.FGA, "FTimp":ref.FTM-ft*ref.FTA}
    for c in ["3PTM","REB","AST","STL","BLK","PTS"]: cols[c]=L[c]; rcols[c]=ref[c]
    cols["TO"]=-L.TO; rcols["TO"]=-ref.TO
    return sum((cols[c]-rcols[c].mean())/rcols[c].std() for c in cols)

def rank_rolling(s, team, value_kind, weekly_cap=2):
    roster=list(s.roster_on(int(s.week_start[1]))[team]); daily={}; n=0
    for w in s.rs_weeks:
        sp=int(s.week_start[w]); rosters=s.roster_on(sp); rosters[team]=list(roster)
        rostered={p for v in rosters.values() for p in v}
        stats, proj=bt.checkpoint_inputs(s, sp)
        fas=[p for p in stats.PlayerId if p not in rostered]
        pl=ro.blend_players(stats, proj, ro.OptimizerConfig(), replacement_pool=pd.Index(fas), days_elapsed=sp-1)
        if value_kind=="projections":
            lines=pl[COMP].mul(pl.availability, axis=0); eligible=pl.index
        else:  # season-to-date per-game, >= 3 games (what ESPN's player list shows)
            st=stats.set_index("PlayerId"); gp=st.season_GP
            lines=pd.DataFrame({"FGM":st["season_FG%_made"]/gp,"FGA":st["season_FG%_att"]/gp,"FTM":st["season_FT%_made"]/gp,"FTA":st["season_FT%_att"]/gp,
                                **{c:st[f"season_{c}_avg"] for c in ["3PTM","REB","AST","STL","BLK","TO","PTS"]}})
            eligible=gp.index[gp>=3]
        val=zvalue(lines.loc[lines.index.intersection(eligible)].dropna(), pd.Index(list(rostered)))
        out_now=set(pl.index[pl.InjuryStatus.isin(ro.OptimizerConfig().excluded_injury_statuses)])
        pool=[p for p in fas if p in val.index and p not in out_now]
        for _ in range(weekly_cap):
            if not pool: break
            best_fa=max(pool, key=lambda p: val[p])
            mine=[p for p in roster]; worst=min(mine, key=lambda p: val.get(p, -np.inf))
            if val[best_fa] <= val.get(worst, -np.inf): break
            roster[roster.index(worst)]=best_fa; pool.remove(best_fa); n+=1
        end=int(s.weeks.loc[s.weeks.Week==w,"EndSP"].iloc[0])
        for day in range(sp,end+1): daily[day]=list(roster)
    return daily, n

rows=[]; swaps=[]
for y in [2019,2020,2021,2022,2023]:
    s=bt.Season(y, data, ref); cp=1; sp0=int(s.week_start[cp])
    stats, proj=bt.checkpoint_inputs(s, sp0)
    rosters=s.roster_on(sp0); rostered={p for v in rosters.values() for p in v}
    fas=[p for p in stats.PlayerId if p not in rostered]
    players=ro.blend_players(stats, proj, ro.OptimizerConfig(), replacement_pool=pd.Index(fas), days_elapsed=0)
    priority=(players["PTS"]+1.2*players["REB"]+1.5*players["AST"]).to_dict()
    base={t: bt.weekly_totals(s, cp, bt.real_daily(s, t, sp0), priority) for t in s.teams}
    for team in s.teams:
        d_opt,n_opt=bt.rolling_roster(s, team, cp, ro.recommended_config(), ro.OptimizerConfig(), weekly_cap=2)
        d_opt3,n_opt3=bt.rolling_roster(s, team, cp, ro.recommended_config(), ro.OptimizerConfig(), weekly_cap=3)
        d_rp,n_rp=rank_rolling(s, team, "projections")
        d_rp3,n_rp3=rank_rolling(s, team, "projections", weekly_cap=3)
        d_rs,n_rs=rank_rolling(s, team, "season")
        swaps.append(dict(optimizer=n_opt, optimizer3=n_opt3, rank_proj=n_rp, rank_proj3=n_rp3, rank_season=n_rs))
        sims={"optimizer": bt.weekly_totals(s, cp, d_opt, priority),
              "optimizer3": bt.weekly_totals(s, cp, d_opt3, priority),
              "rank_proj": bt.weekly_totals(s, cp, d_rp, priority),
              "rank_proj3": bt.weekly_totals(s, cp, d_rp3, priority),
              "rank_season": bt.weekly_totals(s, cp, d_rs, priority),
              "stand_pat": bt.weekly_totals(s, cp, bt.frozen_daily(s, rosters[team], sp0), priority),
              "actual": base[team]}
        for row in s.comp[s.comp.Team==team].itertuples():
            w=row.Week
            if w not in base[row.Opp].index: continue
            opp=bt.cat_values(base[row.Opp].loc[w]); rec={"year":y,"team":team,"week":w}
            for k,v in sims.items():
                if w not in v.index: rec[k]=np.nan; rec[k+"_cats"]=np.nan; continue
                W,L,T=bt.matchup(bt.cat_values(v.loc[w]), opp)
                rec[k]=1.0 if W>L else 0.0 if L>W else 0.5; rec[k+"_cats"]=W+0.5*T
            rows.append(rec)
    print(y,"done",flush=True)
pd.DataFrame(rows).to_csv(sys.argv[3],index=False)
print("avg swaps per team-season:", pd.DataFrame(swaps).mean().round(1).to_dict())

d=pd.DataFrame(rows); d=d[d.week<=18]; rng=np.random.default_rng(0)
def ci(v):
    b=[rng.choice(v,len(v)).mean() for _ in range(4000)]; return np.percentile(b,2.5), np.percentile(b,97.5)
print("18-week totals per team-season vs stand_pat (95% CI):")
for k in ["optimizer","optimizer3","rank_proj","rank_proj3","rank_season","actual"]:
    t=d.assign(x=d[k]-d.stand_pat, c=d[k+"_cats"]-d.stand_pat_cats).groupby(["year","team"])[["x","c"]].sum()
    lo,hi=ci(t.x.values); print(f"  {k:12} wins {t.x.mean():+.2f} [{lo:+.2f},{hi:+.2f}]  cat wins {t.c.mean():+.1f}")
