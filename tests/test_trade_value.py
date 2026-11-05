"""shared/trade_value.py: the value each side of a trade received."""
from __future__ import annotations

import pandas as pd
import pytest

from shared import trade_value as tv


def _games(lines: dict[int, dict], n: int) -> pd.DataFrame:
    rows = []
    for pid, line in lines.items():
        rows += [{"PlayerId": pid, "ScoringPeriod": d, **line} for d in range(1, n + 1)]
    return pd.DataFrame(rows)


BASE = {"FGM": 5, "FGA": 10, "FTM": 2, "FTA": 3, "3PTM": 1, "REB": 5, "AST": 3, "STL": 1, "BLK": 0.5, "TO": 2, "PTS": 13, "MIN": 28}


@pytest.fixture
def scale():
    # Players differ in every stat so every category has a spread.
    lines = {i: {k: v * (0.6 + 0.1 * i) if k != "MIN" else v for k, v in BASE.items()} for i in range(10)}
    for i, line in lines.items():  # vary shooting too
        line["FGM"] *= 0.9 + 0.02 * i
        line["FTM"] *= 0.95 + 0.01 * i
    return tv.season_scale(_games(lines, 20))


def test_more_games_more_value(scale):
    one = tv.stretch_value(pd.Series(BASE), scale)
    ten = tv.stretch_value(pd.Series({k: 10 * v for k, v in BASE.items()}), scale)
    assert ten == pytest.approx(10 * one) and one > 0


def test_turnovers_count_against(scale):
    more_to = {**BASE, "TO": 6}
    assert tv.stretch_value(pd.Series(more_to), scale) < tv.stretch_value(pd.Series(BASE), scale)


def test_bad_shooting_costs(scale):
    bricks = {**BASE, "FGM": 2}  # same attempts, fewer makes (points held equal)
    assert tv.stretch_value(pd.Series(bricks), scale) < tv.stretch_value(pd.Series(BASE), scale)


def test_nothing_played_is_zero(scale):
    assert tv.stretch_value(pd.Series(dtype=float), scale) == 0


def test_winner_and_even():
    assert tv.winner("Fano", 100, "Juan", 80) == "Fano"
    assert tv.winner("Fano", 80, "Juan", 100) == "Juan"
    assert tv.winner("Fano", 100, "Juan", 96) == "Even"   # within 5%
    assert tv.winner("Fano", 0, "Juan", 0) == "Even"


def _line(**kw):
    base = {"FGM": 40, "FGA": 90, "FTM": 15, "FTA": 20, "3PTM": 10, "REB": 45, "AST": 25, "STL": 8, "BLK": 5, "TO": 14, "PTS": 105}
    return {**base, **kw}


def test_score_counts_categories_and_result():
    own, opp = _line(PTS=110), _line()  # only PTS differs
    cats, result = tv.score(own, opp)
    assert cats == 1 + 0.5 * 8 and result == 1.0
    cats, result = tv.score(_line(TO=20), opp)  # more turnovers loses TO
    assert cats == 0.5 * 8 and result == 0.0


def test_wins_added_flips_a_close_week():
    own, opp = _line(PTS=110, REB=50), _line()        # wins 2-0 (7 ties)
    player = {"PTS": 30, "REB": 12, "FGM": 12, "FGA": 24}  # without him: loses PTS and REB
    match, cats = tv.wins_added([(own, opp, player)])
    assert match == 1.0 and cats > 0
    # A blowout week he doesn't swing.
    big = _line(PTS=300, REB=200, AST=100, STL=40, BLK=30, **{"3PTM": 50})
    match, _ = tv.wins_added([(big, opp, {"PTS": 10})])
    assert match == 0.0


def test_week_line_estimates_attempts():
    line = tv.week_line({"FG%": 0.47, "FT%": 0.78, "3PTM": 60, "PTS": 600})
    assert line["FGA"] > 0 and abs(line["FGM"] / line["FGA"] - 0.47) < 1e-9
    assert abs(2 * line["FGM"] + 60 + line["FTM"] - 600) < 1e-6
