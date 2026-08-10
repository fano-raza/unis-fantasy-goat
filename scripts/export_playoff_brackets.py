"""Exports per-year playoff bracket structure (rounds, matchups, seeding,
byes, final standings) from Models/seasons.py::poSeason's fully-computed
bracket logic, so dashboard_site (lightweight venv, never imports Models)
can render a playoff tree on the Standings page.

Bracket advancement/byes/tiebreaks are seeding-derived business logic living
entirely in poSeason (make_PO_matchups/run_playoffs/_resolve_playoff_tie) --
re-deriving that from raw weekly rows in the lightweight path would risk
duplicating (and drifting from) that logic, the same reasoning that led to
scripts/export_real_matchup_flags.py for playoff-matchup membership.

Run this whenever Ref/*_CompStats.csv changes (same cadence as the GDoc/stat
refresh pipeline, same as the other scripts/export_*.py). Requires the full
repo venv (Models/constants dependency chain), unlike dashboard_site itself.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Models.League import fantasyLeague  # noqa: E402
from Models.seasons import poSeason  # noqa: E402
from shared.runtime_config import REF_DIR  # noqa: E402

OUTPUT_PATH = REF_DIR / "playoff_brackets.json"


def round_labels(n: int) -> list[str]:
    if n <= 0:
        return []
    if n == 1:
        return ["Final"]
    if n == 2:
        return ["Semifinals", "Final"]
    if n == 3:
        return ["Quarterfinals", "Semifinals", "Final"]
    # Generic fallback for a hypothetical larger bracket -- untested against
    # real data (this league has never had more than 3 playoff rounds), but
    # keeps the last two labels consistent with the cases above.
    return [f"Round {i + 1}" for i in range(n - 2)] + ["Semifinals", "Final"]


def byes_for_round(season: poSeason, week: int, matchups: list) -> list[str]:
    # A bye team has NO row at all in the raw stat sheet for that week (Yahoo
    # doesn't record a placeholder "Opp=BYE" line) -- so a bye can't be
    # detected from statDict directly. Instead: any team still alive going
    # into this round that isn't playing in one of its matchups had a bye.
    playing = {m.team1 for m in matchups} | {m.team2 for m in matchups}
    elim_week = getattr(season, "elim_week", None) or {}
    alive = [t for t in season.PO_teams if t not in elim_week or elim_week[t] >= week]
    return [t for t in alive if t not in playing]


def matchup_dict(season: poSeason, m, seed_by_team: dict[str, int]) -> dict:
    winner = season._effective_winner(m)
    loser = season._effective_loser(m)
    return {
        "team1": m.team1,
        "team2": m.team2,
        "seed1": seed_by_team.get(m.team1),
        "seed2": seed_by_team.get(m.team2),
        "winner": winner,
        "loser": loser,
        "wins": m.wins,
        "losses": m.losses,
        "ties": m.ties,
        "tiebreak_applied": bool(getattr(m, "tiebreak_applied", False)),
        "tiebreak_reason": getattr(m, "tiebreak_reason", None),
    }


def bracket_for_year(season: poSeason) -> dict | None:
    if season.status == "Not Active" or season.rounds <= 0:
        return None

    seed_by_team = {team: seed for seed, team in (season.PO_seeding or {}).items()}
    labels = round_labels(season.rounds)

    rounds = []
    # Elimination rounds (every round before the final) -- their matchup
    # lists are already fully resolved (byes/eliminated-team cascades
    # stripped out) by poSeason.run_playoffs, so just serialize them as-is.
    for i in range(season.rounds - 1):
        week = season.RSweekCount + 1 + i
        matchups = season.PO_matchups_by_week.get(week) or []
        rounds.append(
            {
                "week": week,
                "label": labels[i],
                "byes": byes_for_round(season, week, matchups),
                "matchups": [matchup_dict(season, m, seed_by_team) for m in matchups],
            }
        )

    # Final round -- read from the special 'Final'/'3rd Place' keys rather
    # than the numeric week key, since those are the canonical resolved
    # slots (the numeric key's list isn't specially filtered for this week).
    final_week = season.RSweekCount + season.rounds
    final_m = season.PO_matchups_by_week.get("Final")
    third_m = season.PO_matchups_by_week.get("3rd Place")
    final_round_matchups = [m for m in (final_m, third_m) if m is not None]
    final_matchups = []
    if final_m is not None:
        final_matchups.append({"slot": "Final", **matchup_dict(season, final_m, seed_by_team)})
    if third_m is not None:
        final_matchups.append({"slot": "3rd Place", **matchup_dict(season, third_m, seed_by_team)})
    rounds.append(
        {
            "week": final_week,
            "label": "Final",
            "byes": byes_for_round(season, final_week, final_round_matchups),
            "matchups": final_matchups,
        }
    )

    return {
        "status": season.status,
        "team_count": len(season.PO_teams),
        "seeding": {str(seed): team for seed, team in (season.PO_seeding or {}).items()},
        "champion": season.PO_champ,
        "standings": {str(place): team for place, team in (season.PO_standings or {}).items()},
        "rounds": rounds,
    }


def main() -> None:
    lg = fantasyLeague()
    out: dict[str, dict] = {}
    for year, ls in lg.seasons.items():
        bracket = bracket_for_year(ls.playoffs)
        if bracket is not None:
            out[str(year)] = bracket

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(out, f, indent=2)

    print(f"Wrote {len(out)} years of playoff bracket data to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
