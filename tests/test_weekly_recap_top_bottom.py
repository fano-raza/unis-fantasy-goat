"""Weekly recap "Top & Bottom" section (discord/weekly_rankings.py): the
week's top/bottom-rated teams' facts, the plain fallback, and the CSV
header upgrade for the new top_bottom_json column."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "discord"))
import weekly_rankings as wr  # noqa: E402


def _row(team, rank, rating, opp, win, cats=(5, 4)):
    return {"team": team, "rank": rank, "rating": rating, "opponent": opp, "matchup_win": win,
            "matchup_loss": not win, "matchup_tie": False, "cat_wins": cats[0], "cat_losses": cats[1], "cat_ties": 0}


def test_top_bottom_facts_streaks_and_counts():
    wk3 = [_row("A", 1, 70, "C", False, (4, 5)), _row("B", 2, 60, "D", True), _row("C", 3, 50, "A", True), _row("D", 4, 30, "B", False)]
    wk2 = [_row("B", 1, 65, "A", True), _row("A", 2, 60, "B", False), _row("C", 3, 40, "D", True), _row("D", 4, 20, "C", False)]
    wk1 = [_row("A", 1, 66, "D", True), _row("B", 2, 55, "C", True), _row("C", 3, 45, "B", False), _row("D", 4, 25, "A", False)]
    weeks_desc = [(3, wk3), (2, wk2), (1, wk1)]
    facts = wr._top_bottom_facts(wk3, weeks_desc, {"A": 2, "B": 1, "C": 3, "D": 4})
    top, bottom = facts["top"], facts["bottom"]
    assert top["team"] == "A" and top["top_rank_streak"] == 1 and top["top_rank_count_this_season"] == 2
    assert top["matchup_result"] == "loss" and top["category_score"] == "4-5" and top["rating_gap_to_next"] == 10
    assert bottom["team"] == "D" and bottom["bottom_rank_streak"] == 3 and bottom["bottom_rank_count_this_season"] == 3
    assert wr._top_bottom_fallback(facts) == ["A had the best week (rating 70)", "D had the worst week (rating 30)"]


def test_csv_header_upgraded_in_place(tmp_path):
    path = tmp_path / "weekly_recaps.csv"
    old = [f for f in wr.CSV_FIELDS if f != "top_bottom_json"]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=old)
        w.writeheader()
        w.writerow({k: ("2027" if k == "year" else "1" if k == "week" else "x") for k in old})
    wr._ensure_csv(path)
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert reader.fieldnames == wr.CSV_FIELDS
    assert rows[0]["year"] == "2027" and rows[0]["top_bottom_json"] == "" and rows[0]["upsets_json"] == "x"
