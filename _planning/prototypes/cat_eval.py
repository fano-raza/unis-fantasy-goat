import pandas as pd, numpy as np, sys
rng=np.random.default_rng(0)
def ci(v):
    v=np.asarray(v,float); b=rng.choice(v,(3000,len(v))).mean(1); return np.percentile(b,[2.5,97.5])
KEY=["year","checkpoint","team"]
for path in sys.argv[1:]:
    d=pd.read_pickle(path)
    d["comb"]=np.where(d["shape"]=="1-for-1", d.adj_gain, d["adjfa0.7_gain"])
    vf=d.partner_value_net>=0
    print(f"\n### {path.split('/')[-1]}  (gains in expected categories won per week = share x 9)")
    for mode,pmin in [("Fair",0.01),("Fleece",-0.01)]:
        for obj,you,part in [("standings (live)","comb","adj_partner_gain"),("categories only","cat_gain","cat_partner_gain")]:
            m=vf&(d[you]>=0.01)&(d[part]>=pmin)
            y=d[m]
            if y.empty: print(mode,obj,"none"); continue
            t=y.loc[y.groupby(KEY)[you].idxmax()]
            g=t.orc_cat_gain*9; pg=t.orc_cat_partner_gain*9; lo,hi=ci(g)
            per=" ".join(f"{yr}:{v:+.2f}" for yr,v in (t.groupby('year').orc_cat_gain.mean()*9).items())
            print(f"  {mode:6s} {obj:17s} n={len(t):3d} you {g.mean():+.2f} [{lo:+.2f},{hi:+.2f}] pos {np.mean(g>0):.0%} | partner {pg.mean():+.2f} | {per}")
