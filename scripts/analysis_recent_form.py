"""Recent-form analysis for the Roster Optimizer (2026-10-25): does blending a
player's last-7/14-day average into his season-to-date stats predict better?
Writes per-(season, horizon, window, weight) normalized squared errors.

  python -m scripts.analysis_recent_form <backtest data dir> <ref dir> <out.csv>

Findings in _planning/roster-optimizer.md ("Recent form").
"""
from pathlib import Path
sys.path.insert(0, ".")
from scripts import backtest_roster_optimizer as bt
from shared import roster_optimizer as ro
data, ref = Path(sys.argv[1]), Path(sys.argv[2])
CATS=["PTS","REB","AST","3PTM","STL","BLK","FGM","FGA","FTM","FTA"]
ALPHAS=[0,0.1,0.2,0.3,0.4,0.5,0.7]
rows=[]   # (year, horizon, window, alpha) -> per-cat sq err sums
acc={}
def add(key, err, n):
    a=acc.setdefault(key,[np.zeros(len(CATS)),0]); a[0]+=err; a[1]+=n
for y in [2019,2020,2021,2022,2023]:
    s=bt.Season(y, data, ref)
    last_sp=int(s.weeks.loc[s.weeks.Week==max(s.rs_weeks),"EndSP"].iloc[0])
    for w in [wk for wk in s.rs_weeks if 3<=wk<=18]:
        sp0=int(s.week_start[w])
        stats, proj=bt.checkpoint_inputs(s, sp0)
        rosters=s.roster_on(sp0); rostered={p for v in rosters.values() for p in v}
        fas=pd.Index([p for p in stats.PlayerId if p not in rostered])
        before=s.games[s.games.ScoringPeriod<sp0]
        targets={}
        for hz,end in [("next14",min(sp0+13,last_sp)),("rest",last_sp)]:
            g=s.games[(s.games.ScoringPeriod>=sp0)&(s.games.ScoringPeriod<=end)]
            gp=g.groupby("PlayerId").size(); t=g.groupby("PlayerId")[ro.COMPONENTS].sum().div(gp,axis=0)
            targets[hz]=t[gp>=(4 if hz=="next14" else 10)]
        st=stats.set_index("PlayerId")
        for win in [7,14]:
            rec=before[before.ScoringPeriod>=sp0-win]; rgp=rec.groupby("PlayerId").size()
            rpg=rec.groupby("PlayerId")[ro.COMPONENTS].sum().div(rgp,axis=0)
            for a in ALPHAS:
                mod=st.copy(); gp_s=mod["season_GP"].astype(float)
                has=mod.index.isin(rpg.index) & (gp_s>0)
                idx=mod.index[has]
                # season per-game
                sea={c: mod.loc[idx,f"season_{c}_avg"] for c in ["3PTM","REB","AST","STL","BLK","TO","PTS"]}
                sea["FGM"]=mod.loc[idx,"season_FG%_made"]/gp_s[idx]; sea["FGA"]=mod.loc[idx,"season_FG%_att"]/gp_s[idx]
                sea["FTM"]=mod.loc[idx,"season_FT%_made"]/gp_s[idx]; sea["FTA"]=mod.loc[idx,"season_FT%_att"]/gp_s[idx]
                mix={c:(1-a)*sea[c]+a*rpg.loc[idx,c] for c in sea}
                for c in ["3PTM","REB","AST","STL","BLK","TO","PTS"]: mod.loc[idx,f"season_{c}_avg"]=mix[c]
                mod.loc[idx,"season_FG%_made"]=mix["FGM"]*gp_s[idx]; mod.loc[idx,"season_FG%_att"]=mix["FGA"]*gp_s[idx]
                mod.loc[idx,"season_FT%_made"]=mix["FTM"]*gp_s[idx]; mod.loc[idx,"season_FT%_att"]=mix["FTA"]*gp_s[idx]
                pl=ro.blend_players(mod.reset_index(), proj, ro.OptimizerConfig(), replacement_pool=fas, days_elapsed=sp0-1)
                for hz,T in targets.items():
                    ok=T.index.intersection(pl.index[pl.GP>0])
                    if not len(ok): continue
                    sd=T.loc[ok,CATS].std().replace(0,np.nan)
                    err=(((pl.loc[ok,CATS]-T.loc[ok,CATS])/sd)**2).sum().to_numpy()
                    add((y,hz,win,a), err, len(ok))
    print(y,"done",flush=True)
out=[]
for (y,hz,win,a),(e,n) in acc.items():
    out.append({"year":y,"horizon":hz,"window":win,"alpha":a,"n":n,**dict(zip(CATS,e))})
pd.DataFrame(out).to_csv(sys.argv[3],index=False)
