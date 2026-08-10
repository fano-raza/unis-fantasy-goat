from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

from shared.weighted_rank import aggregate_rating, per_week_rating  # noqa: E402

from .query_engine import StatsStore

# Mirrors constants.mainCats / negCats / mainCatsPCT / mainCatsSum. Duplicated
# here (rather than importing constants.py) so this module stays on the
# lightweight dashboard venv — constants.py pulls in gspread/espn_fr/yfpy_fr
# as an import-time side effect that has nothing to do with this data path.
MAIN_CATS = ["FG%", "FT%", "3PTM", "REB", "AST", "STL", "BLK", "TO", "PTS"]
NEG_CATS = ["TO"]
PCT_CATS = ["FG%", "FT%"]
SUM_CATS = ["3PTM", "REB", "AST", "STL", "BLK", "TO", "PTS"]
RATING_COLS = [f"{c}_rating" for c in MAIN_CATS]
RANK_COLS = [f"{c}_rank" for c in MAIN_CATS]

# Mirrors constants.seasonInfo's 3rd tuple element (is W/L scoring) per
# year -- some seasons were actually scored by matchup W/L, others by
# aggregate category wins ("Cats"). Used only to pick a sensible default
# toggle state on the Standings page; keep in sync with constants.py by
# hand if that ever changes (same tradeoff already accepted for
# MAIN_CATS/etc. above).
SEASON_IS_WL = {
    2019: True,
    2020: True,
    2021: True,
    2022: True,
    2023: True,
    2024: False,
    2025: True,
    2026: False,
}


class LeagueStore:
    """Weighted-Rank-bearing views built on dashboard_site's own CSV-loaded
    data (via StatsStore), deliberately independent of Models/League.py so
    this stays on the lightweight dashboard venv. The actual rating math
    lives in shared/weighted_rank.py, which Models/League.py and
    Models/seasons.py also call — one implementation of each formula, used
    from both the heavy (Models) and light (dashboard_site) code paths."""

    def __init__(self, store: StatsStore | None = None) -> None:
        self.store = store or StatsStore()
        self._rated_df: pd.DataFrame | None = None
        self._weekly_df: pd.DataFrame | None = None
        self._team_summary_df: pd.DataFrame | None = None
        self._po_lookup = self._load_po_real_matchup_lookup()

    def _load_po_real_matchup_lookup(self) -> dict[tuple[int, int, str, str], bool]:
        """Count==True is a reliable "real matchup" proxy for regular-season
        rows, but not for playoff weeks: the raw CompStats CSVs mark
        consolation-bracket games Count=True right alongside real
        championship-bracket games, and which teams are actually in the
        bracket (including byes) is seeding-derived logic that lives in
        Models/seasons.py, not something the CSV states directly. Rather than
        re-derive that (risking a fresh bug in logic that was already
        non-trivial to get right there), read the small precomputed lookup
        from scripts/export_real_matchup_flags.py. Falls back to Count alone
        if that hasn't been generated yet -- degraded but not broken."""
        ref_dir = getattr(self.store, "ref_dir", None)
        if ref_dir is None:
            return {}
        path = Path(ref_dir) / "real_matchup_flags.csv"
        if not path.exists():
            return {}
        lookup_df = pd.read_csv(path)
        return {
            (int(r.Year), int(r.Week), r.Season, r.Team): bool(r.real_matchup)
            for r in lookup_df.itertuples()
        }

    def _real_matchup_mask(self, df: pd.DataFrame) -> pd.Series:
        mask = (df["Count"] == True) if "Count" in df.columns else pd.Series(True, index=df.index)  # noqa: E712
        if not self._po_lookup:
            return mask
        # The lookup only has entries for teams Models.League's own PO_teams
        # seeding actually kept (it strips non-bracket teams internally
        # before we ever export it) -- so for PO rows, default to "not real"
        # and only flip to True when the lookup explicitly confirms it.
        # Defaulting to the raw Count flag instead would silently let
        # consolation-bracket teams (absent from the lookup entirely) count.
        po_idx = df.index[df["Season"] == "PO"]
        for idx in po_idx:
            row = df.loc[idx]
            key = (int(row["Year"]), int(row["Week"]), row["Season"], row["Team"])
            mask.loc[idx] = self._po_lookup.get(key, False)
        return mask

    def meta(self) -> dict:
        df = self.store.df
        years = sorted(df["Year"].dropna().astype(int).unique().tolist())
        count_df = df[self._real_matchup_mask(df)]
        current_year = max(years) if years else None
        current_week = None
        if current_year is not None:
            weeks = count_df.loc[count_df["Year"] == current_year, "Week"]
            current_week = int(weeks.max()) if not weeks.empty else None

        rs_week_count: dict[int, int] = {}
        playoff_rounds: dict[int, int] = {}
        for year, group in count_df.groupby("Year"):
            rs_weeks = group.loc[group["Season"] == "RS", "Week"]
            po_weeks = group.loc[group["Season"] == "PO", "Week"]
            if not rs_weeks.empty:
                rs_week_count[int(year)] = int(rs_weeks.max())
            if not po_weeks.empty:
                playoff_rounds[int(year)] = int(po_weeks.nunique())

        total_matchup_count = {y: rs_week_count.get(y, 0) + playoff_rounds.get(y, 0) for y in years}

        members = sorted(t for t in df["Team"].dropna().astype(str).unique().tolist() if t != "BYE")
        season_format = {y: ("wl" if SEASON_IS_WL.get(y, True) else "cats") for y in years}
        return {
            "years": years,
            "members": members,
            "current_year": current_year,
            "current_week": current_week,
            "rs_week_count": rs_week_count,
            "playoff_rounds": playoff_rounds,
            "total_matchup_count": total_matchup_count,
            "categories": MAIN_CATS,
            "season_format": season_format,
        }

    def weekly_team(self, year: int, week: int, team: str) -> dict:
        df = self._ensure_weekly_df()
        row = df[(df["Year"] == year) & (df["Week"] == week) & (df["Team"] == team)]
        if row.empty:
            raise ValueError(f"No data for team={team!r}, year={year}, week={week}")
        return self._week_row_to_dict(row.iloc[0])

    def weekly_leaderboard(self, year: int, week: int) -> list[dict]:
        df = self._ensure_weekly_df()
        df = df[(df["Year"] == year) & (df["Week"] == week)].sort_values("week_rank")
        if df.empty:
            raise ValueError(f"No data for year={year}, week={week}")
        return [self._week_row_to_dict(row) for _, row in df.iterrows()]

    def totals(
        self,
        years: list[int] | None = None,
        weeks: list[int] | None = None,
        teams: list[str] | None = None,
        RS: bool = True,
        PO: bool = True,
    ) -> list[dict]:
        df = self._filtered_raw(years, weeks, teams, RS, PO)[["Team"] + MAIN_CATS]
        agg_dict = {c: "mean" for c in PCT_CATS}
        agg_dict.update({c: "sum" for c in SUM_CATS})
        grouped = df.groupby("Team", as_index=False).agg(agg_dict)
        return self._agg_df_to_list(aggregate_rating(grouped, MAIN_CATS, NEG_CATS))

    def averages(
        self,
        years: list[int] | None = None,
        weeks: list[int] | None = None,
        teams: list[str] | None = None,
        RS: bool = True,
        PO: bool = True,
    ) -> list[dict]:
        df = self._filtered_raw(years, weeks, teams, RS, PO)[["Team"] + MAIN_CATS]
        grouped = df.groupby("Team", as_index=False).mean()
        return self._agg_df_to_list(aggregate_rating(grouped, MAIN_CATS, NEG_CATS))

    def leaders(self, years: list[int] | None = None, RS: bool = True, PO: bool = True) -> dict:
        """All-time career totals leader per category: best aggregate value and who holds it."""
        df = self._filtered_raw(years, None, None, RS, PO)[["Team"] + MAIN_CATS]
        agg_dict = {c: "mean" for c in PCT_CATS}
        agg_dict.update({c: "sum" for c in SUM_CATS})
        grouped = df.groupby("Team", as_index=False).agg(agg_dict)
        out: dict[str, dict] = {}
        for cat in MAIN_CATS:
            ascending = cat in NEG_CATS
            row = grouped.loc[grouped[cat].idxmin() if ascending else grouped[cat].idxmax()]
            out[cat] = {"team": str(row["Team"]), "value": float(row[cat])}
        return out

    def team_summary(self, teams: list[str] | None = None) -> list[dict]:
        """Career profile stats (chips, finals, playoffs, streaks, draft scores)
        for the Career Comparison page. Reads scripts/export_team_summary.py's
        precomputed Ref/team_summary.csv directly -- this data needs the heavy
        Models/TeamManager dependency chain, so it's never computed live here."""
        df = self._ensure_team_summary_df()
        if teams:
            df = df[df["Team"].isin(teams)]
        df = df.where(pd.notnull(df), None)
        return df.to_dict(orient="records")

    # Comma-joined year lists -- forced to string dtype so a column doesn't
    # silently come back as int64 whenever every row this refresh happens to
    # have exactly one year (no comma anywhere), which breaks any consumer
    # expecting a string. Single-year columns (Best/Worst Draft Season) are
    # deliberately NOT here -- those are meant to stay numeric.
    _TEAM_SUMMARY_YEAR_LIST_COLS = [
        "Championship Years",
        "Finals Years",
        "Playoff Years",
        "MVP Years",
        "RS 1st Years",
        "Best RS Rating Years",
        "Best RS Finish Years",
    ]

    def _ensure_team_summary_df(self) -> pd.DataFrame:
        if self._team_summary_df is not None:
            return self._team_summary_df
        ref_dir = getattr(self.store, "ref_dir", None)
        path = Path(ref_dir) / "team_summary.csv" if ref_dir else None
        if path is None or not path.exists():
            raise ValueError(
                "team_summary.csv not found -- run scripts/export_team_summary.py first"
            )
        dtype = {col: str for col in self._TEAM_SUMMARY_YEAR_LIST_COLS}
        self._team_summary_df = pd.read_csv(path, dtype=dtype)
        return self._team_summary_df

    def head_to_head(
        self,
        team_a: str,
        team_b: str,
        years: list[int] | None = None,
        RS: bool = True,
        PO: bool = True,
    ) -> dict:
        df = self._ensure_weekly_df()
        seasons = self._require_seasons(RS, PO)
        mask = (df["Team"] == team_a) & (df["Opp"] == team_b) & df["Season"].isin(seasons)
        if years:
            mask &= df["Year"].isin(years)
        df = df[mask].sort_values(["Year", "Week"])
        if df.empty:
            raise ValueError(f"No matchups found between {team_a!r} and {team_b!r}")
        matchups = [self._week_row_to_dict(row) for _, row in df.iterrows()]
        return {
            "team_a": team_a,
            "team_b": team_b,
            "record": {
                "wins": int(df["MATCHUP_WINS"].sum()),
                "losses": int(df["MATCHUP_LOSSES"].sum()),
                "ties": int(df["MATCHUP_DRAWS"].sum()),
            },
            "category_record": {
                "wins": int(df["CAT_WINS"].sum()),
                "losses": int(df["CAT_LOSSES"].sum()),
                "ties": int(df["CAT_TIES"].sum()),
            },
            "matchups": matchups,
        }

    def records(self, years: list[int] | None = None, RS: bool = True, PO: bool = True) -> dict:
        """Best single week ever (overall rating and per category) plus longest win streaks per team."""
        # Excludes BYE rows -- a bye week's real box-score stats are still
        # real numbers (raw stats aren't null there, only the comparison
        # fields are), so without this a bye week could win a "best week
        # ever" category record despite never being compared to anyone.
        df = self._ensure_weekly_df()
        df = df[df["Opp"] != "BYE"]
        seasons = self._require_seasons(RS, PO)
        mask = df["Season"].isin(seasons)
        if years:
            mask &= df["Year"].isin(years)
        df = df[mask].reset_index(drop=True)
        if df.empty:
            raise ValueError("No data available for the given filters")

        best_week_overall = self._week_row_to_dict(df.loc[df["week_rating"].idxmax()])

        best_week_by_category = {}
        for cat in MAIN_CATS:
            ascending = cat in NEG_CATS
            row = df.loc[df[cat].idxmin() if ascending else df[cat].idxmax()]
            best_week_by_category[cat] = {
                "team": str(row["Team"]),
                "year": int(row["Year"]),
                "week": int(row["Week"]),
                "value": float(row[cat]),
            }

        return {
            "best_week_overall": best_week_overall,
            "best_week_by_category": best_week_by_category,
            "longest_win_streaks": self._compute_win_streaks(df),
        }

    def analysis_rows(
        self,
        years: list[int] | None = None,
        weeks: list[int] | None = None,
        teams: list[str] | None = None,
        RS: bool = True,
        PO: bool = True,
    ) -> list[dict]:
        """Full row-level dataset for the Analysis page: every stat, per-category
        rank/rating, and overall rating/rank for every team/week matching the
        filters -- the frontend does its own X/Y pivoting and grouping over
        this, rather than the backend anticipating specific chart shapes."""
        # Excludes BYE rows (_ensure_weekly_df now includes them for the
        # Weekly Stats page) -- they have no rating/rank/cat W-L-T, which
        # _analysis_row_to_dict isn't NaN-safe for, and the Analysis page's
        # per-row rank/rating fields assume every row played a real matchup.
        df = self._ensure_weekly_df()
        df = df[df["Opp"] != "BYE"]
        seasons = self._require_seasons(RS, PO)
        mask = df["Season"].isin(seasons)
        if years:
            mask &= df["Year"].isin(years)
        if weeks:
            mask &= df["Week"].isin(weeks)
        if teams:
            mask &= df["Team"].isin(teams)
        df = df[mask]
        return [self._analysis_row_to_dict(row) for _, row in df.iterrows()]

    def standings(self, year: int, min_week: int, max_week: int) -> dict:
        """RS-only standings for the Standings page: real matchup W/L, real
        matchup category W/L, and "League Wins" (all-play -- every team vs.
        every other team every week, hypothetically) W/L and Cats. Mirrors
        the GDoc "Overall Rank" sheet's four sections (GDoc/GDoc_Week.py::
        updateStandings), computed for an arbitrary week range rather than
        a fixed cutoff. The all-play columns (LEAGUE_WL_*/LEAGUE_CATS_*)
        are already computed per team per week in
        StatsStore._build_matchup_features's "All-play schedule context"
        block (query_engine.py) -- this just aggregates what's already
        flowing through _ensure_weekly_df, nothing new to compute there.

        Deliberately does NOT replicate Models/seasons.py's multi-level
        tiebreaker chain (_sort_with_tiebreakers) or constants.py's
        standingsOverwrite (a single-year manual correction for 2025's
        full-season W/L standings only) -- ties share a rank instead, the
        same convention used elsewhere in this app (e.g. Weekly Stats'
        display-rank fix). See _planning/web-app-build-plan.md for the
        full reasoning."""
        df = self._ensure_weekly_df()
        df = df[
            (df["Season"] == "RS")
            & (df["Year"] == year)
            & (df["Week"] >= min_week)
            & (df["Week"] <= max_week)
            & (df["Opp"] != "BYE")
        ]
        if df.empty:
            raise ValueError(f"No data for year={year}, weeks {min_week}-{max_week}")

        def _standings(win_col: str, loss_col: str, tie_col: str) -> list[dict]:
            grouped = df.groupby("Team")[[win_col, loss_col, tie_col]].sum()
            rows = [
                {
                    "team": str(team),
                    "wins": int(r[win_col]),
                    "losses": int(r[loss_col]),
                    "ties": int(r[tie_col]),
                }
                for team, r in grouped.iterrows()
            ]
            return self._rank_standings(rows)

        return {
            "wl": _standings("MATCHUP_WINS", "MATCHUP_LOSSES", "MATCHUP_DRAWS"),
            "cats": _standings("CAT_WINS", "CAT_LOSSES", "CAT_TIES"),
            "league_wl": _standings("LEAGUE_WL_WINS", "LEAGUE_WL_LOSSES", "LEAGUE_WL_DRAWS"),
            "league_cats": _standings("LEAGUE_CATS_WINS", "LEAGUE_CATS_LOSSES", "LEAGUE_CATS_DRAWS"),
        }

    @staticmethod
    def _rank_standings(rows: list[dict]) -> list[dict]:
        """Standard competition ranking (ties share a rank) by win/loss
        score (wins + 0.49*ties, the tie-weight convention used throughout
        this codebase), descending. Alphabetical as a stable display-order
        tiebreak only -- doesn't affect the rank *value* two tied teams
        get, only which order they're listed in."""

        def score(r: dict) -> float:
            return r["wins"] + 0.49 * r["ties"]

        ranked = sorted(rows, key=lambda r: (-score(r), r["team"]))
        for i, row in enumerate(ranked):
            row["rank"] = i + 1 if i == 0 or score(row) != score(ranked[i - 1]) else ranked[i - 1]["rank"]
        return ranked

    def _filtered_raw(
        self,
        years: list[int] | None,
        weeks: list[int] | None,
        teams: list[str] | None,
        RS: bool,
        PO: bool,
    ) -> pd.DataFrame:
        df = self.store.df
        df = df[self._real_matchup_mask(df)]
        seasons = self._require_seasons(RS, PO)
        df = self.store._apply_common_filters(df, years=years, weeks=weeks, teams=teams, opponents=None, seasons=seasons)
        if df.empty:
            raise ValueError("No data for the given filters")
        return df

    @staticmethod
    def _require_seasons(RS: bool, PO: bool) -> list[str]:
        seasons = (["RS"] if RS else []) + (["PO"] if PO else [])
        if not seasons:
            raise ValueError("At least one of RS or PO must be true")
        return seasons

    def _ensure_rated_df(self) -> pd.DataFrame:
        """Per-week Weighted Rank columns, ranked within each (Year, Season)
        partition — mirrors Models/seasons.py, where a separate
        regSeason/poSeason object (and its own df_build_out() call) exists
        per year per RS-or-PO, and ranking never mixes across those
        boundaries.

        Deliberately uses the broader Count==True universe here, NOT the
        stricter bracket-aware _real_matchup_mask: Models/seasons.py computes
        ratings BEFORE its own playoff-bracket filtering runs, so a playoff
        week's rating is calculated against everyone who played a real game
        that week -- including consolation-bracket teams -- not just the
        championship bracket. Matching that ordering matters: rank/rating are
        relative to the comparison pool, so narrowing the pool changes the
        numbers even for teams that ARE in the bracket. The bracket-aware
        mask is applied separately, only to decide which rows get surfaced
        (see _ensure_weekly_df / _filtered_raw)."""
        if self._rated_df is not None:
            return self._rated_df

        df = self.store.df
        if "Count" in df.columns:
            df = df[df["Count"] == True]  # noqa: E712

        parts = []
        for _key, group in df.groupby(["Year", "Season"], sort=False):
            team_count = group["Team"].nunique()
            parts.append(per_week_rating(group, MAIN_CATS, NEG_CATS, team_count))

        self._rated_df = pd.concat(parts, ignore_index=True) if parts else df
        return self._rated_df

    def _ensure_weekly_df(self) -> pd.DataFrame:
        if self._weekly_df is not None:
            return self._weekly_df
        # Deliberately not store._ensure_matchup_df(): that builds pairings
        # off the raw Count flag, which (like _ensure_rated_df above) wrongly
        # includes consolation-bracket teams for playoff weeks. Build our own
        # matchup pairing from the same real-matchup-filtered rows instead,
        # scoped to this module so the generic /query endpoint's existing
        # Count-based matchup semantics are untouched.
        real_df = self.store.df[self._real_matchup_mask(self.store.df)]
        matchup_df = StatsStore._build_matchup_features(real_df)
        rated_cols = ["Year", "Week", "Season", "Team", "week_rating", "week_rank"] + RATING_COLS + RANK_COLS
        rated_df = self._ensure_rated_df()[rated_cols]
        weekly_df = matchup_df.merge(rated_df, on=["Year", "Week", "Season", "Team"], how="left")

        # A team on a bye that week never enters _build_matchup_features'
        # inner merge (Opp=="BYE" means Count=False, filtered out before
        # pairing even runs) -- surface them anyway with their real raw
        # stats and nothing else (no opponent to compare against, so no
        # rating/rank/cat W-L-T). pd.concat unions in NaN for every column
        # only matchup_df/rated_df has; _week_row_to_dict is NaN-safe.
        bye_df = self.store.df[self.store.df["Opp"] == "BYE"]
        if not bye_df.empty:
            weekly_df = pd.concat([weekly_df, bye_df], ignore_index=True, sort=False)

        self._weekly_df = weekly_df
        return self._weekly_df

    @staticmethod
    def _compute_win_streaks(df: pd.DataFrame) -> list[dict]:
        out = []
        for team, group in df.sort_values(["Year", "Week"]).groupby("Team"):
            best = cur = 0
            for win in group["MATCHUP_WINS"].values:
                cur = cur + 1 if win == 1 else 0
                best = max(best, cur)
            out.append({"team": str(team), "longest_win_streak": int(best)})
        out.sort(key=lambda r: r["longest_win_streak"], reverse=True)
        return out

    @staticmethod
    def _analysis_row_to_dict(row: pd.Series) -> dict:
        return {
            "team": str(row["Team"]),
            "opponent": str(row["Opp"]),
            "year": int(row["Year"]),
            "week": int(row["Week"]),
            "season": str(row["Season"]),
            "stats": {cat: float(row[cat]) for cat in MAIN_CATS},
            "ratings": {cat: round(float(row[f"{cat}_rating"]), 2) for cat in MAIN_CATS},
            "ranks": {cat: int(row[f"{cat}_rank"]) for cat in MAIN_CATS},
            "week_rating": round(float(row["week_rating"]), 2),
            "week_rank": int(row["week_rank"]),
            "cat_wins": int(row["CAT_WINS"]),
            "cat_losses": int(row["CAT_LOSSES"]),
            "cat_ties": int(row["CAT_TIES"]),
            "matchup_win": bool(row["MATCHUP_WINS"]),
        }

    @staticmethod
    def _week_row_to_dict(row: pd.Series) -> dict:
        # BYE-week rows (see _ensure_weekly_df) have no opponent to compare
        # against, so every comparison-derived field is NaN -- None instead,
        # rather than crashing on int(nan)/bool(nan).
        def _opt_int(value) -> int | None:
            return None if pd.isna(value) else int(value)

        def _opt_float(value, digits: int = 2) -> float | None:
            return None if pd.isna(value) else round(float(value), digits)

        def _opt_bool(value) -> bool | None:
            return None if pd.isna(value) else bool(value)

        return {
            "team": str(row["Team"]),
            "opponent": str(row["Opp"]),
            "year": int(row["Year"]),
            "week": int(row["Week"]),
            "season": str(row["Season"]),
            "stats": {cat: float(row[cat]) for cat in MAIN_CATS},
            "ratings": {
                cat: round(float(row[f"{cat}_rating"]), 2)
                for cat in MAIN_CATS
                if pd.notna(row[f"{cat}_rating"])
            },
            "cat_wins": _opt_int(row["CAT_WINS"]),
            "cat_losses": _opt_int(row["CAT_LOSSES"]),
            "cat_ties": _opt_int(row["CAT_TIES"]),
            "matchup_win": _opt_bool(row["MATCHUP_WINS"]),
            "matchup_loss": _opt_bool(row["MATCHUP_LOSSES"]),
            "matchup_tie": _opt_bool(row["MATCHUP_DRAWS"]),
            "rating": _opt_float(row["week_rating"]),
            "rank": _opt_int(row["week_rank"]),
        }

    @staticmethod
    def _agg_df_to_list(df: pd.DataFrame) -> list[dict]:
        df = df.sort_values("Rank")
        return [
            {
                "team": str(row["Team"]),
                "stats": {cat: float(row[cat]) for cat in MAIN_CATS},
                # NOTE: aggregate_rating()'s per-category _rating is 0-1 scaled (no *100,
                # unlike per_week_rating()'s) -- matches avg_rating's existing convention.
                "ratings": {cat: round(float(row[f"{cat}_rating"]), 4) for cat in MAIN_CATS},
                "rating": round(float(row["avg_rating"]), 4),
                "rank": int(row["Rank"]),
            }
            for _, row in df.iterrows()
        ]


_league_store: LeagueStore | None = None


def get_league_store(store: StatsStore | None = None) -> LeagueStore:
    global _league_store
    if _league_store is None:
        _league_store = LeagueStore(store)
    return _league_store
