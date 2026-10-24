"""Tests for the scoring pieces of scripts/backtest_roster_optimizer.py."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import backtest_roster_optimizer as bt


def cats(**kw):
    base = {c: 0.0 for c in bt.STAT_CATS}
    base.update(kw)
    return base


def test_matchup_counts_turnovers_lower_is_better_and_ties():
    a = cats(**{"FG%": 0.5, "PTS": 100, "TO": 10, "REB": 40})
    b = cats(**{"FG%": 0.4, "PTS": 90, "TO": 12, "REB": 40})
    w, l, t = bt.matchup(a, b)
    # FG%, PTS, TO (fewer) won; REB and the 5 all-zero cats tied.
    assert (w, l, t) == (3, 0, 6)


def test_cat_values_builds_percentages_from_makes_and_attempts():
    t = pd.Series({"FGM": 30, "FGA": 60, "FTM": 9, "FTA": 12, "3PTM": 5, "REB": 1, "AST": 2,
                   "STL": 3, "BLK": 4, "TO": 6, "PTS": 80})
    v = bt.cat_values(t)
    assert v["FG%"] == pytest.approx(0.5) and v["FT%"] == pytest.approx(0.75) and v["PTS"] == 80


class FakeSeason:
    """Two teams, weeks 1-2. Real results: A wins week 1. Simulated week 2."""

    def __init__(self):
        rows = []
        for week, a_pts, b_pts in [(1, 100, 50), (2, 10, 20)]:
            for team, opp, pts in [("A", "B", a_pts), ("B", "A", b_pts)]:
                rows.append({"Week": week, "Team": team, "Opp": opp, "FGM": 10, "FGA": 20, "FTM": 5, "FTA": 10,
                             "3PTM": 1, "REB": 1, "AST": 1, "STL": 1, "BLK": 1, "TO": 1, "PTS": pts})
        self.comp = pd.DataFrame(rows)
        self.teams = ["A", "B"]


def sim_week(pts):
    return pd.DataFrame([{**{c: 1.0 for c in bt.COMP}, "FGM": 10, "FGA": 20, "FTM": 5, "FTA": 10, "PTS": pts}], index=[2])


def test_standings_use_real_results_before_checkpoint_and_simulation_after():
    s = FakeSeason()
    # Checkpoint week 2: week 1 is real (A wins on PTS); week 2 simulated with B winning.
    table = bt.standings(s, 2, {"A": sim_week(10), "B": sim_week(99)})
    assert (table.loc["A", "W"], table.loc["A", "L"]) == (1, 1)
    # Same simulation but checkpoint week 3 -> week 2 uses the REAL rows (A 10 vs B 20): still B.
    # Flip the sim so it would favour A: with checkpoint 2 A sweeps.
    table = bt.standings(s, 2, {"A": sim_week(99), "B": sim_week(10)})
    assert (table.loc["A", "W"], table.loc["A", "L"]) == (2, 0)
    assert table.loc["A", "wl_rank"] == 1 and table.loc["B", "wl_rank"] == 2


def test_category_record_accumulates_ties():
    s = FakeSeason()
    table = bt.standings(s, 2, {"A": sim_week(10), "B": sim_week(10)})
    # Week 1 real: A wins PTS only, ties the other 8. Week 2 sim: all 9 tie.
    assert (table.loc["A", "cW"], table.loc["A", "cL"], table.loc["A", "cT"]) == (1, 0, 17)
    assert table.loc["A", "T"] == 1
