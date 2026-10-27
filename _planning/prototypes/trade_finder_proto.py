# Throwaway prototype for _planning/trade-recommender.md (2026-10-27).
# Run: .venv-dashboard/bin/python _planning/prototypes/trade_finder_proto.py "$PWD" <dir with player_stats/roster_ranks/player_projections/week_calendar CSVs>
# Note: days_elapsed is hard-coded to 2026-10-27.
"""Prototype: mutually beneficial trades on live data, scored with the
roster optimizer's standings objective (both teams rescored vs the league)."""
import sys, itertools, time
from datetime import date
import numpy as np, pandas as pd
sys.path.insert(0, sys.argv[1])
from shared import roster_optimizer as ro
REF = sys.argv[2]
stats = pd.read_csv(f"{REF}/player_stats.csv"); proj = pd.read_csv(f"{REF}/player_projections.csv")
rr = pd.read_csv(f"{REF}/roster_ranks.csv"); cal = pd.read_csv(f"{REF}/week_calendar.csv")
year = int(rr["Year"].max()); rr = rr[rr["Year"] == year]
name_to_id = dict(zip(stats["Player"], stats["PlayerId"]))
rosters, rostered = {}, set()
for row in rr.itertuples():
    if isinstance(row.FantasyTeam, str) and row.FantasyTeam and row.Player in name_to_id:
        rostered.add(name_to_id[row.Player])
        if row.LineupSlot != "IR":
            rosters.setdefault(row.FantasyTeam, []).append(name_to_id[row.Player])
fas = [p for p in stats["PlayerId"] if p not in rostered]
w1 = pd.Timestamp(cal[(cal.Year == year) & (cal.Week == 1)]["StartDate"].iloc[0]).date()
cfg = ro.recommended_config()
players = ro.blend_players(stats, proj, cfg, replacement_pool=pd.Index(fas), days_elapsed=float((date(2026,10,27)-w1).days))
players[ro.COMPONENTS] = players[ro.COMPONENTS].astype(float).mul(players["availability"], axis=0)
teams = sorted(rosters); T = {t: i for i, t in enumerate(teams)}
comps = players[ro.COMPONENTS]; scale = ro.roster_scale(rosters, cfg.roster_size)
sums = np.stack([comps.loc[rosters[t]].sum().to_numpy() * scale[t] for t in teams])
vals = ro.category_values(sums)
sigma = ro.category_sigma(pd.DataFrame(vals, columns=ro.MAIN_CATS), cfg)
ign = np.array([c in cfg.ignored_cats for c in ro.MAIN_CATS])

def scores(S):
    """S (..., nteams, 11) -> (..., nteams) standings score of every team vs the rest."""
    V = ro.category_values(S)
    diff = (V[..., :, None, :] - V[..., None, :, :]) * np.where(np.array([c in ro.NEG_CATS for c in ro.MAIN_CATS]), -1, 1)
    p = ro.normal_cdf(diff / (sigma * np.sqrt(2)))
    p = np.where(ign, 0.5, p)
    n = len(teams); mask = ~np.eye(n, dtype=bool)
    m = ro.at_least_k(p, cfg.cats_to_win)              # (..., n, n)
    cat = p.mean(-1)
    m = np.where(mask, m, 0).sum(-1) / (n - 1); cat = np.where(mask, cat, 0).sum(-1) / (n - 1)
    return 0.5 * m + 0.5 * cat, None

base, _ = scores(sums)
print(f"{year}: {len(teams)} teams, roster sizes {sorted(len(v) for v in rosters.values())}, days {(date(2026,10,27)-w1).days}")

nm = players["Player"]
rules = {"both +1": (0.01, 0.01), "you +1, them > -3": (0.01, -0.03), "you +1, them > -1": (0.01, -0.01)}
per_player = {r: set() for r in rules}; counts = {r: 0 for r in rules}; tot = 0; best = {}
for A in teams:
    a = T[A]
    for B in teams:
        if B == A: continue
        b = T[B]
        X = comps.loc[rosters[A]].to_numpy(); Y = comps.loc[rosters[B]].to_numpy()
        d = Y[None] - X[:, None]
        S = np.broadcast_to(sums, d.shape[:2] + sums.shape).copy()
        S[:, :, a] += scale[A] * d; S[:, :, b] -= scale[B] * d
        sc, _ = scores(S)
        ga, gb = sc[..., a] - base[a], sc[..., b] - base[b]
        tot += ga.size
        for r, (ma, mb) in rules.items():
            ok = (ga > ma) & (gb > mb)
            counts[r] += int(ok.sum())
            for i, j in zip(*np.nonzero(ok)):
                per_player[r].add(rosters[A][i])
                if r == "you +1, them > -3":
                    best.setdefault(A, []).append((ga[i, j], gb[i, j], nm[rosters[A][i]], B, nm[rosters[B][j]]))
print(f"1-for-1 (directed: you give x, get y): {tot}")
for r in rules:
    print(f"  {r:22s}: {counts[r]:5d} trades; your players with >=1 option: {len(per_player[r])}/{sum(len(v) for v in rosters.values())}")
for A in ["Fano", "Juan", "Ange"]:
    print(f"\n{A} top (you +1, them > -3), by your gain:")
    for g in sorted(best.get(A, []), reverse=True)[:5]:
        print(f"   give {g[2]:24s} get {g[4]:24s} ({g[3]:8s}) you {g[0]*100:+.1f}  them {g[1]*100:+.1f}")

# 2-for-1 for one team: A gives 2, gets 1. A fills open spot with best of top-10 FAs; B drops its weakest remaining.
ok_fa = [p for p in fas if p in players.index and players.at[p, "InjuryStatus"] not in cfg.excluded_injury_statuses and players.at[p, "NBATeam"] != "FA"]
F = comps.loc[ok_fa].to_numpy()
z = ((F - F.mean(0)) / (F.std(0) + 1e-9)) * np.where(np.array([c == "TO" for c in ro.COMPONENTS]), -1, 1)
top = np.argsort(-z.sum(1))[:10]; F = F[top]
A = "Fano"; a = T[A]; t0 = time.time(); res = []; n = 0
for B in teams:
    if B == A: continue
    b = T[B]
    for x1, x2 in itertools.combinations(rosters[A], 2):
        X = comps.loc[[x1, x2]].to_numpy().sum(0)
        for y in rosters[B]:
            Y = comps.loc[y].to_numpy(); keep = [p for p in rosters[B] if p != y]; D = comps.loc[keep].to_numpy()
            S = np.broadcast_to(sums, (len(keep), len(F)) + sums.shape).copy()
            S[..., a, :] += scale[A] * (Y - X + F[None]); S[..., b, :] += scale[B] * (X - Y - D[:, None])
            sc, _ = scores(S); ga = sc[..., a] - base[a]; gb = sc[..., b] - base[b]
            j = int(np.argmax(ga.max(0))); i = int(np.argmax(gb[:, j])); n += 1
            if ga[i, j] > 0.01 and gb[i, j] > -0.03:
                res.append((ga[i, j], gb[i, j], nm[x1], nm[x2], B, nm[y], nm[keep[i]], nm[ok_fa[top[j]]]))
print(f"\n2-for-1 for {A}: {n} trades in {time.time()-t0:.0f}s; you +1 & them > -3: {len(res)}; both +1: {sum(1 for r in res if r[1] > 0.01)}")
for r in sorted(res, key=lambda r: -min(r[0], r[1]))[:6]:
    print(f"   give {r[2]} + {r[3]} -> {r[4]}'s {r[5]}; {r[4]} drops {r[6]}; {A} adds {r[7]} | you {r[0]*100:+.1f} them {r[1]*100:+.1f}")
