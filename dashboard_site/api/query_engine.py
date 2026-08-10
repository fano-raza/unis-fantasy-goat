from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd


BASE_METRIC_ALIASES: dict[str, str] = {
    "pts": "PTS",
    "points": "PTS",
    "reb": "REB",
    "rebounds": "REB",
    "ast": "AST",
    "assists": "AST",
    "stl": "STL",
    "steals": "STL",
    "blk": "BLK",
    "blocks": "BLK",
    "to": "TO",
    "turnovers": "TO",
    "fg%": "FG%",
    "field goal %": "FG%",
    "field goal percentage": "FG%",
    "ft%": "FT%",
    "free throw %": "FT%",
    "free throw percentage": "FT%",
    "3ptm": "3PTM",
    "3pm": "3PTM",
    "threes": "3PTM",
    "three pointers": "3PTM",
    "3pta": "3PTA",
    "fga": "FGA",
    "fgm": "FGM",
    "fta": "FTA",
    "ftm": "FTM",
}

DERIVED_METRIC_ALIASES: dict[str, str] = {
    "wins": "MATCHUP_WINS",
    "win": "MATCHUP_WINS",
    "losses": "MATCHUP_LOSSES",
    "loss": "MATCHUP_LOSSES",
    "draws": "MATCHUP_DRAWS",
    "ties": "MATCHUP_DRAWS",
    "tie": "MATCHUP_DRAWS",
    "win%": "WIN_PCT",
    "win pct": "WIN_PCT",
    "win percentage": "WIN_PCT",
    "category wins": "CAT_WINS",
    "cat wins": "CAT_WINS",
    "category losses": "CAT_LOSSES",
    "cat losses": "CAT_LOSSES",
    "category ties": "CAT_TIES",
    "cat ties": "CAT_TIES",
    "all play wins": "ALL_PLAY_WINS",
    "all play losses": "ALL_PLAY_LOSSES",
    "all play ties": "ALL_PLAY_TIES",
    "all play points": "ALL_PLAY_POINTS",
    "expected wins": "ALL_PLAY_POINTS_AVG",
    "league wl wins": "LEAGUE_WL_WINS",
    "league wl losses": "LEAGUE_WL_LOSSES",
    "league wl ties": "LEAGUE_WL_DRAWS",
    "league wl draws": "LEAGUE_WL_DRAWS",
    "league wl points": "LEAGUE_WL_POINTS",
    "league cats wins": "LEAGUE_CATS_WINS",
    "league cats losses": "LEAGUE_CATS_LOSSES",
    "league cats ties": "LEAGUE_CATS_DRAWS",
    "league cats draws": "LEAGUE_CATS_DRAWS",
    "league cats points": "LEAGUE_CATS_POINTS",
    "schedule luck": "SCHEDULE_LUCK",
    "schedule swap": "SCHEDULE_LUCK",
    "schedule swap delta": "SCHEDULE_LUCK",
    "draft": "DRAFT_SCORE",
    "draft score": "DRAFT_SCORE",
    "draft value": "DRAFT_SCORE",
    "pick count": "DRAFT_PICK_COUNT",
    "draft picks": "DRAFT_PICK_COUNT",
}

METRIC_ALIASES: dict[str, str] = {**BASE_METRIC_ALIASES, **DERIVED_METRIC_ALIASES}

CANONICAL_DISPLAY = {
    "PTS": "Points",
    "REB": "Rebounds",
    "AST": "Assists",
    "STL": "Steals",
    "BLK": "Blocks",
    "TO": "Turnovers",
    "FG%": "Field Goal %",
    "FT%": "Free Throw %",
    "3PTM": "3PT Made",
    "3PTA": "3PT Attempted",
    "FGM": "FG Made",
    "FGA": "FG Attempted",
    "FTM": "FT Made",
    "FTA": "FT Attempted",
    "MATCHUP_WINS": "Matchup Wins",
    "MATCHUP_LOSSES": "Matchup Losses",
    "MATCHUP_DRAWS": "Matchup Draws",
    "WIN_PCT": "Matchup Win %",
    "CAT_WINS": "Category Wins",
    "CAT_LOSSES": "Category Losses",
    "CAT_TIES": "Category Draws",
    "ALL_PLAY_WINS": "All-Play Wins",
    "ALL_PLAY_LOSSES": "All-Play Losses",
    "ALL_PLAY_TIES": "All-Play Draws",
    "ALL_PLAY_POINTS": "All-Play Points",
    "ALL_PLAY_POINTS_AVG": "All-Play Avg Points",
    "LEAGUE_WL_WINS": "League Wins (WL)",
    "LEAGUE_WL_LOSSES": "League Losses (WL)",
    "LEAGUE_WL_DRAWS": "League Draws (WL)",
    "LEAGUE_WL_POINTS": "League Points (WL)",
    "LEAGUE_CATS_WINS": "League Wins (Cats)",
    "LEAGUE_CATS_LOSSES": "League Losses (Cats)",
    "LEAGUE_CATS_DRAWS": "League Draws (Cats)",
    "LEAGUE_CATS_POINTS": "League Points (Cats)",
    "SCHEDULE_LUCK": "Schedule Luck",
    "DRAFT_SCORE": "Draft Score",
    "DRAFT_PICK_COUNT": "Draft Pick Count",
}

MATCHUP_METRICS = {
    "MATCHUP_WINS",
    "MATCHUP_LOSSES",
    "MATCHUP_DRAWS",
    "WIN_PCT",
    "CAT_WINS",
    "CAT_LOSSES",
    "CAT_TIES",
    "ALL_PLAY_WINS",
    "ALL_PLAY_LOSSES",
    "ALL_PLAY_TIES",
    "ALL_PLAY_POINTS",
    "ALL_PLAY_POINTS_AVG",
    "LEAGUE_WL_WINS",
    "LEAGUE_WL_LOSSES",
    "LEAGUE_WL_DRAWS",
    "LEAGUE_WL_POINTS",
    "LEAGUE_CATS_WINS",
    "LEAGUE_CATS_LOSSES",
    "LEAGUE_CATS_DRAWS",
    "LEAGUE_CATS_POINTS",
    "SCHEDULE_LUCK",
}

DRAFT_METRICS = {"DRAFT_SCORE", "DRAFT_PICK_COUNT"}

LOWER_BETTER = {
    "TO",
    "MATCHUP_LOSSES",
    "CAT_LOSSES",
    "ALL_PLAY_LOSSES",
    "LEAGUE_WL_LOSSES",
    "LEAGUE_CATS_LOSSES",
}


class StatsStore:
    def __init__(self, ref_dir: str | None = None) -> None:
        self.ref_dir = self._resolve_ref_dir(ref_dir)
        self.df = self._load_all_compstats(self.ref_dir)
        self._matchup_df: pd.DataFrame | None = None
        self._draft_df: pd.DataFrame | None = None

    @staticmethod
    def _resolve_ref_dir(ref_dir: str | None) -> Path:
        if ref_dir:
            return Path(ref_dir)
        if os.getenv("FANTASY_REF_DIR"):
            return Path(os.environ["FANTASY_REF_DIR"])

        candidates = [
            (Path(__file__).resolve().parents[2] / "Ref").resolve(),
            (Path(__file__).resolve().parents[3] / "Ref").resolve(),
            Path("/srv/unisfantasy/data/ref"),
        ]
        for c in candidates:
            if c.exists():
                return c
        return candidates[0]

    @staticmethod
    def _load_all_compstats(ref_dir: Path) -> pd.DataFrame:
        files = sorted(ref_dir.glob("*_CompStats.csv"))
        if not files:
            raise FileNotFoundError(f"No *_CompStats.csv found in {ref_dir}")

        frames: list[pd.DataFrame] = [pd.read_csv(f) for f in files]
        all_df = pd.concat(frames, ignore_index=True)

        if "Count" in all_df.columns:
            all_df["Count"] = all_df["Count"].astype(str).str.lower().isin(["true", "1", "t", "yes"])

        # Stat-pipeline re-runs have occasionally appended an identical block of rows
        # (e.g. 2025 week 20 PO). Models/seasons.py's dict-keyed loader collapses these
        # naturally (last write wins); this row-based loader needs an explicit dedupe.
        all_df = all_df.drop_duplicates(ignore_index=True)

        return all_df

    @staticmethod
    def _extract_year_from_path(path: Path) -> int | None:
        m = re.match(r"(\d{4})", path.stem)
        if m:
            return int(m.group(1))
        m2 = re.search(r"(\d{4})", str(path.parent.name))
        if m2:
            return int(m2.group(1))
        return None

    def _resolve_draft_roots(self) -> list[Path]:
        roots: list[Path] = []
        env_root = os.getenv("FANTASY_DRAFT_DIR")
        if env_root:
            roots.append(Path(env_root))
        roots.append(self.ref_dir.parent)
        roots.append(self.ref_dir.parent.parent)
        dedup: list[Path] = []
        seen = set()
        for r in roots:
            rr = r.resolve()
            if rr not in seen and rr.exists():
                dedup.append(rr)
                seen.add(rr)
        return dedup

    def _load_draft_scores(self) -> pd.DataFrame:
        rows: list[dict] = []
        seen_files: set[Path] = set()
        for root in self._resolve_draft_roots():
            for csv_path in root.glob("*/**/*Draft Results.csv"):
                csv_path = csv_path.resolve()
                if csv_path in seen_files:
                    continue
                seen_files.add(csv_path)
                try:
                    df = pd.read_csv(csv_path)
                except Exception:
                    continue
                if not {"Team", "Score"}.issubset(set(df.columns)):
                    continue
                year = self._extract_year_from_path(csv_path)
                if year is None:
                    continue
                for _, r in df.iterrows():
                    try:
                        score = float(r["Score"])
                    except Exception:
                        continue
                    rows.append({"Year": year, "Team": str(r["Team"]), "DRAFT_SCORE": score, "DRAFT_PICK_COUNT": 1.0})

        if not rows:
            return pd.DataFrame(columns=["Year", "Team", "DRAFT_SCORE", "DRAFT_PICK_COUNT"])
        return pd.DataFrame(rows)

    def _ensure_draft_df(self) -> pd.DataFrame:
        if self._draft_df is None:
            self._draft_df = self._load_draft_scores()
        return self._draft_df

    @staticmethod
    def _build_matchup_features(base_df: pd.DataFrame) -> pd.DataFrame:
        cats_pos = ["FG%", "FT%", "3PTM", "REB", "AST", "STL", "BLK", "PTS"]
        cat_neg = ["TO"]

        # Actual matchup rows only.
        use = base_df.copy()
        if "Count" in use.columns:
            use = use[use["Count"] == True]

        cols = ["Year", "Week", "Season", "Team", "Opp"] + cats_pos + cat_neg
        use = use[cols].copy()
        opp_cols = ["Year", "Week", "Season", "Team"] + cats_pos + cat_neg
        right = use[opp_cols].copy().rename(columns={"Team": "_opp_team"})

        merged = use.merge(
            right,
            left_on=["Year", "Week", "Season", "Opp"],
            right_on=["Year", "Week", "Season", "_opp_team"],
            suffixes=("", "_opp"),
            how="inner",
        )

        wins = pd.Series(0, index=merged.index)
        losses = pd.Series(0, index=merged.index)
        ties = pd.Series(0, index=merged.index)

        for c in cats_pos:
            wins += (merged[c] > merged[f"{c}_opp"]).astype(int)
            losses += (merged[c] < merged[f"{c}_opp"]).astype(int)
            ties += (merged[c] == merged[f"{c}_opp"]).astype(int)

        for c in cat_neg:
            wins += (merged[c] < merged[f"{c}_opp"]).astype(int)
            losses += (merged[c] > merged[f"{c}_opp"]).astype(int)
            ties += (merged[c] == merged[f"{c}_opp"]).astype(int)

        merged["CAT_WINS"] = wins.astype(float)
        merged["CAT_LOSSES"] = losses.astype(float)
        merged["CAT_TIES"] = ties.astype(float)
        merged["MATCHUP_WINS"] = (wins > losses).astype(float)
        merged["MATCHUP_LOSSES"] = (wins < losses).astype(float)
        merged["MATCHUP_DRAWS"] = (wins == losses).astype(float)
        merged["MATCHUP_POINTS"] = merged["MATCHUP_WINS"] + 0.49 * merged["MATCHUP_DRAWS"]

        # All-play schedule context per week.
        for key, g in merged.groupby(["Year", "Week", "Season"], sort=False):
            by_team = {str(r["Team"]): r for _, r in g.iterrows()}
            teams = list(by_team.keys())
            n = len(teams)
            for t in teams:
                w = l = d = 0.0
                points = 0.0
                cat_wins_sum = cat_losses_sum = cat_ties_sum = 0.0
                a = by_team[t]
                for o in teams:
                    if o == t:
                        continue
                    b = by_team[o]
                    cw = cl = ct = 0
                    for c in cats_pos:
                        av = float(a[c])
                        bv = float(b[c])
                        if av > bv:
                            cw += 1
                        elif av < bv:
                            cl += 1
                        else:
                            ct += 1
                    # TO lower is better.
                    at = float(a["TO"])
                    bt = float(b["TO"])
                    if at < bt:
                        cw += 1
                    elif at > bt:
                        cl += 1
                    else:
                        ct += 1

                    if cw > cl:
                        w += 1
                        points += 1
                    elif cw < cl:
                        l += 1
                    else:
                        d += 1
                        points += 0.49
                    cat_wins_sum += cw
                    cat_losses_sum += cl
                    cat_ties_sum += ct

                row_idx = g[g["Team"] == t].index[0]
                merged.at[row_idx, "ALL_PLAY_WINS"] = w
                merged.at[row_idx, "ALL_PLAY_LOSSES"] = l
                merged.at[row_idx, "ALL_PLAY_TIES"] = d
                merged.at[row_idx, "ALL_PLAY_POINTS"] = points
                merged.at[row_idx, "ALL_PLAY_POINTS_AVG"] = points / max(n - 1, 1)
                # First-class "league wins" style metrics.
                merged.at[row_idx, "LEAGUE_WL_WINS"] = w
                merged.at[row_idx, "LEAGUE_WL_LOSSES"] = l
                merged.at[row_idx, "LEAGUE_WL_DRAWS"] = d
                merged.at[row_idx, "LEAGUE_WL_POINTS"] = points
                merged.at[row_idx, "LEAGUE_CATS_WINS"] = cat_wins_sum
                merged.at[row_idx, "LEAGUE_CATS_LOSSES"] = cat_losses_sum
                merged.at[row_idx, "LEAGUE_CATS_DRAWS"] = cat_ties_sum
                merged.at[row_idx, "LEAGUE_CATS_POINTS"] = cat_wins_sum + 0.49 * cat_ties_sum

        merged["SCHEDULE_LUCK"] = merged["MATCHUP_POINTS"] - merged["ALL_PLAY_POINTS_AVG"]
        merged["WIN_PCT"] = (
            merged["MATCHUP_WINS"] + 0.5 * merged["MATCHUP_DRAWS"]
        ) / (merged["MATCHUP_WINS"] + merged["MATCHUP_LOSSES"] + merged["MATCHUP_DRAWS"]).replace(0, 1)

        return merged

    def _ensure_matchup_df(self) -> pd.DataFrame:
        if self._matchup_df is None:
            self._matchup_df = self._build_matchup_features(self.df)
        return self._matchup_df

    def available_meta(self) -> dict:
        df = self.df
        return {
            "years": sorted(df["Year"].dropna().astype(int).unique().tolist()),
            "weeks": sorted(df["Week"].dropna().astype(int).unique().tolist()),
            "teams": sorted(df["Team"].dropna().astype(str).unique().tolist()),
            "opponents": sorted(df["Opp"].dropna().astype(str).unique().tolist()),
            "metrics": CANONICAL_DISPLAY,
        }

    @staticmethod
    def resolve_metric(metric: str) -> str:
        m = metric.strip()
        key = m.lower()
        if key in METRIC_ALIASES:
            return METRIC_ALIASES[key]

        upper = m.upper()
        if upper in CANONICAL_DISPLAY:
            return upper

        raise ValueError(f"Unsupported metric: {metric}")

    def _apply_common_filters(
        self,
        df: pd.DataFrame,
        years: list[int] | None,
        weeks: list[int] | None,
        teams: list[str] | None,
        opponents: list[str] | None,
        seasons: list[str] | None,
    ) -> pd.DataFrame:
        out = df
        if years and "Year" in out.columns:
            out = out[out["Year"].isin(years)]
        if weeks and "Week" in out.columns:
            out = out[out["Week"].isin(weeks)]
        if teams and "Team" in out.columns:
            out = out[out["Team"].isin(teams)]
        if opponents and "Opp" in out.columns:
            out = out[out["Opp"].isin(opponents)]
        if seasons and "Season" in out.columns:
            normalized = [s.strip().upper() for s in seasons]
            out = out[out["Season"].isin(normalized)]
        return out

    def _dataset_for_metric(self, canonical_metric: str, count_only: bool) -> pd.DataFrame:
        if canonical_metric in DRAFT_METRICS:
            return self._ensure_draft_df()
        if canonical_metric in MATCHUP_METRICS:
            return self._ensure_matchup_df()

        out = self.df
        if count_only and "Count" in out.columns:
            out = out[out["Count"] == True]
        return out

    def query(
        self,
        metric: str,
        aggregation: str,
        group_by: list[str],
        years: list[int] | None,
        weeks: list[int] | None,
        teams: list[str] | None,
        opponents: list[str] | None,
        seasons: list[str] | None,
        count_only: bool,
        sort_desc: bool,
        limit: int,
    ) -> pd.DataFrame:
        col = self.resolve_metric(metric)
        df = self._dataset_for_metric(col, count_only=count_only)
        df = self._apply_common_filters(
            df=df,
            years=years,
            weeks=weeks,
            teams=teams,
            opponents=opponents,
            seasons=seasons,
        )

        if df.empty:
            return pd.DataFrame(columns=group_by + ["value"])

        for g in group_by:
            if g not in df.columns:
                raise ValueError(f"Unsupported group_by '{g}' for metric '{col}'")

        if col not in df.columns:
            raise ValueError(f"Metric '{col}' is not available in selected dataset")

        if aggregation == "sum":
            out = df.groupby(group_by, as_index=False)[col].sum().rename(columns={col: "value"})
        elif aggregation == "avg":
            out = df.groupby(group_by, as_index=False)[col].mean().rename(columns={col: "value"})
        elif aggregation == "min":
            out = df.groupby(group_by, as_index=False)[col].min().rename(columns={col: "value"})
        elif aggregation == "max":
            out = df.groupby(group_by, as_index=False)[col].max().rename(columns={col: "value"})
        elif aggregation == "count":
            out = df.groupby(group_by, as_index=False)[col].count().rename(columns={col: "value"})
        elif aggregation == "rank":
            out = df.groupby(group_by, as_index=False)[col].mean().rename(columns={col: "value"})
            ascending = col in LOWER_BETTER
            out["rank"] = out["value"].rank(method="min", ascending=ascending).astype(int)
            out = out.sort_values("rank", ascending=True)
            return out.head(limit)
        else:
            raise ValueError(f"Unsupported aggregation: {aggregation}")

        out = out.sort_values("value", ascending=not sort_desc)
        return out.head(limit)

    def timeseries(
        self,
        metric: str,
        aggregation: str,
        group_by: str,
        years: list[int] | None,
        weeks: list[int] | None,
        teams: list[str] | None,
        opponents: list[str] | None,
        seasons: list[str] | None,
        count_only: bool,
    ) -> pd.DataFrame:
        col = self.resolve_metric(metric)
        df = self._dataset_for_metric(col, count_only=count_only)
        df = self._apply_common_filters(
            df=df,
            years=years,
            weeks=weeks,
            teams=teams,
            opponents=opponents,
            seasons=seasons,
        )
        if df.empty:
            return pd.DataFrame(columns=[group_by, "value"])

        if group_by not in df.columns:
            raise ValueError(f"Unsupported timeseries group_by '{group_by}' for metric '{col}'")

        if aggregation == "sum":
            out = df.groupby(group_by, as_index=False)[col].sum().rename(columns={col: "value"}).sort_values(group_by)
        else:
            out = df.groupby(group_by, as_index=False)[col].mean().rename(columns={col: "value"}).sort_values(group_by)

        return out

    def schedule_swap(
        self,
        years: list[int] | None,
        weeks: list[int] | None,
        teams: list[str] | None,
        seasons: list[str] | None,
        limit: int,
    ) -> pd.DataFrame:
        df = self._ensure_matchup_df()
        df = self._apply_common_filters(
            df=df,
            years=years,
            weeks=weeks,
            teams=teams,
            opponents=None,
            seasons=seasons,
        )
        if df.empty:
            return pd.DataFrame(columns=["Team", "actual_points", "all_play_avg_points", "schedule_luck"]) 

        out = (
            df.groupby("Team", as_index=False)
            .agg(
                actual_points=("MATCHUP_POINTS", "sum"),
                all_play_avg_points=("ALL_PLAY_POINTS_AVG", "sum"),
                schedule_luck=("SCHEDULE_LUCK", "sum"),
            )
            .sort_values("schedule_luck", ascending=False)
        )
        return out.head(limit)
