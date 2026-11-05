"""Who won a trade: the fantasy value each side RECEIVED, from the day after
the trade until each player left his new fantasy team (dropped, traded away)
or the season ended (user decision 2026-11-04: option 1, production after
the trade -- the simplest and most objective measure).

Value of a stretch of games = sum over the 9 categories of the stretch's
total, divided by that category's typical spread between fantasy-relevant
players (the per-game SD of their season averages), so a steal and a few
points weigh about the same:
  counting stats (3PTM, REB, AST, STL, BLK, PTS): + total / sd
  TO:                                             - total / sd
  FG%, FT%: makes above the league rate on the same attempts
            (FGM - lg% x FGA) / sd of that per-game impact
So more games of the same production = more value, and a player who never
plays for his new team adds 0. A side's value is the sum over the players it
received. The winner is the side with more; within DRAW_SHARE of each other
it's "Even".

Pure pandas (no network) -- scripts/export_trades.py supplies the game logs
and each player's stretch.
"""
from __future__ import annotations

import pandas as pd

COMP = ["FGM", "FGA", "FTM", "FTA", "3PTM", "REB", "AST", "STL", "BLK", "TO", "PTS"]
COUNTING = ["3PTM", "REB", "AST", "STL", "BLK", "PTS"]
DRAW_SHARE = 0.05
# Fantasy-relevant players for the scale: enough games (a quarter of the most
# anyone has played so far, at least 3 -- so it works early in a season) and
# 20+ minutes a game when minutes are known.
MIN_MPG = 20.0


def season_scale(games: pd.DataFrame) -> dict:
    """Per-category SDs (and league FG/FT rates) from one season's game logs
    (one row per player-game, COMP columns, optional MIN)."""
    g = games.copy()
    gp = g.groupby("PlayerId").size()
    pool = gp[gp >= max(3, int(0.25 * gp.max()))].index
    avg = g[g["PlayerId"].isin(pool)].groupby("PlayerId")[COMP + (["MIN"] if "MIN" in g else [])].mean()
    if "MIN" in avg and (avg["MIN"] >= MIN_MPG).sum() >= 30:
        avg = avg[avg["MIN"] >= MIN_MPG]
    fg = avg["FGM"].sum() / avg["FGA"].sum()
    ft = avg["FTM"].sum() / avg["FTA"].sum()
    sd = {c: float(avg[c].std()) for c in COUNTING + ["TO"]}
    sd["FG"] = float((avg["FGM"] - fg * avg["FGA"]).std())
    sd["FT"] = float((avg["FTM"] - ft * avg["FTA"]).std())
    return {"fg": fg, "ft": ft, "sd": sd}


def stretch_value(totals: pd.Series | dict, scale: dict) -> float:
    """Value of a player's (or side's) summed COMP totals."""
    t = {c: float(totals.get(c, 0.0)) for c in COMP}
    sd = scale["sd"]
    v = sum(t[c] / sd[c] for c in COUNTING if sd[c] > 0)
    v -= t["TO"] / sd["TO"] if sd["TO"] > 0 else 0.0
    if sd["FG"] > 0:
        v += (t["FGM"] - scale["fg"] * t["FGA"]) / sd["FG"]
    if sd["FT"] > 0:
        v += (t["FTM"] - scale["ft"] * t["FTA"]) / sd["FT"]
    return v


def winner(team_a: str, value_a: float, team_b: str, value_b: float) -> str:
    """Team that received more value, or "Even" within DRAW_SHARE."""
    top = max(abs(value_a), abs(value_b))
    if top == 0 or abs(value_a - value_b) <= DRAW_SHARE * top:
        return "Even"
    return team_a if value_a > value_b else team_b


# ---------------------------------------------------------------------------
# Wins a received player added (user request 2026-11-04): re-score each of
# his new team's real matchups without his games -- the drop in matchup wins
# (W=1, T=0.5) and category wins (tie = 0.5) is what he added. Only games he
# was in the active lineup count (bench/IR games don't score); Yahoo seasons
# have no lineup history, so there every game on the roster counts.
# ---------------------------------------------------------------------------

CATS = ["FG%", "FT%", "3PTM", "REB", "AST", "STL", "BLK", "TO", "PTS"]
# Yahoo seasons' weekly team stats have FG%/FT% but no makes/attempts. FTA is
# estimated as this share of FGA (league-typical) and FGA solved from
# PTS = 2*FGM + 3PTM + FTM.
FTA_PER_FGA = 0.29  # median of the ESPN seasons 2019-23 (est. FGA within ~3%)


def week_line(row: dict) -> dict:
    """A team-week as COMP totals (estimating attempts when missing)."""
    line = {c: float(row.get(c) or 0.0) for c in COMP}
    if not line["FGA"]:
        fg, ft = float(row.get("FG%") or 0.0), float(row.get("FT%") or 0.0)
        denom = 2 * fg + FTA_PER_FGA * ft
        fga = (line["PTS"] - line["3PTM"]) / denom if denom > 0 else 0.0
        line.update(FGA=fga, FGM=fg * fga, FTA=FTA_PER_FGA * fga, FTM=ft * FTA_PER_FGA * fga)
    return line


def _cat_values(line: dict) -> dict:
    v = {c: line[c] for c in ["3PTM", "REB", "AST", "STL", "BLK", "TO", "PTS"]}
    v["FG%"] = line["FGM"] / line["FGA"] if line["FGA"] else 0.0
    v["FT%"] = line["FTM"] / line["FTA"] if line["FTA"] else 0.0
    return v


def score(own: dict, opp: dict) -> tuple[float, float]:
    """(category wins with ties as 0.5, matchup result 1/0.5/0) for `own`."""
    a, b = _cat_values(own), _cat_values(opp)
    won = lost = 0.0
    for c in CATS:
        x, y = (-a[c], -b[c]) if c == "TO" else (a[c], b[c])
        if abs(x - y) < 1e-9:
            continue
        won, lost = (won + 1, lost) if x > y else (won, lost + 1)
    ties = len(CATS) - won - lost
    result = 1.0 if won > lost else 0.0 if won < lost else 0.5
    return won + 0.5 * ties, result


def wins_added(matchups: list[tuple[dict, dict, dict]]) -> tuple[float, float]:
    """Sum over (team week, opponent week, player's totals that week) of the
    (matchup wins, category wins) the team would lose without the player."""
    match = cat = 0.0
    for own, opp, player in matchups:
        without = {c: own[c] - float(player.get(c, 0.0)) for c in COMP}
        c1, m1 = score(own, opp)
        c0, m0 = score(without, opp)
        match += m1 - m0
        cat += c1 - c0
    return match, cat
