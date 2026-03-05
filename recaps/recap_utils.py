from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from Models.seasons import regSeason
from constants import mainCats, seasonInfoDict
from shared.runtime_config import DATA_ROOT


@dataclass
class RegularSeasonRecapData:
    year: int
    avg_rating: pd.DataFrame
    top_performer_counts: pd.Series
    non_used_format_name: str
    non_used_standings: dict
    opp_rating: pd.DataFrame
    top10_picks: pd.DataFrame
    bottom10_picks: pd.DataFrame
    draft_score_by_team: pd.DataFrame
    category_rankings: dict[str, pd.DataFrame]


def _format_number(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}"


def _format_signed(value: float, digits: int = 2) -> str:
    return f"+{value:.{digits}f}" if value > 0 else f"{value:.{digits}f}"


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return lines


def _build_regular_season_frame(season: regSeason) -> pd.DataFrame:
    return season.statDF.loc[
        (season.statDF["Week Name"].str.startswith("M"))
        & (season.statDF["real_matchup"] == 1)
        & (season.statDF["Team"].isin(season.teams))
    ].copy()


def _build_draft_tables(year: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    draft_path = DATA_ROOT / str(year) / f"{year} Draft Results.csv"
    draft_df = pd.read_csv(draft_path)

    draft_df["Rank_num"] = pd.to_numeric(draft_df["Rank"], errors="coerce")
    draft_df["Score_num"] = pd.to_numeric(draft_df["Score"], errors="coerce")
    draft_df["Overall_num"] = pd.to_numeric(draft_df["Overall"], errors="coerce")

    def quality(rank: float) -> int:
        if pd.notna(rank) and rank != 501:
            return 2
        if pd.notna(rank):
            return 1
        return 0

    draft_df["quality"] = draft_df["Rank_num"].apply(quality)
    dedup = (
        draft_df.sort_values(["Overall_num", "quality"], ascending=[True, False])
        .drop_duplicates(subset=["Overall_num"], keep="first")
        .copy()
    )

    dedup["final_rank"] = dedup["Rank_num"].fillna(501)
    dedup["final_score"] = dedup["Score_num"].where(
        dedup["Score_num"].notna(),
        dedup["Overall_num"] - dedup["final_rank"],
    )

    pick_sorted = dedup.sort_values("final_score", ascending=False).reset_index(drop=True)
    top10 = pick_sorted.head(10).copy()
    bottom10 = pick_sorted.tail(10).sort_values("final_score", ascending=True).copy()
    by_team = (
        dedup.groupby("Team", as_index=False)["final_score"]
        .sum()
        .sort_values("final_score", ascending=False)
        .reset_index(drop=True)
    )
    return top10, bottom10, by_team


def build_regular_season_recap_data(year: int) -> RegularSeasonRecapData:
    season = regSeason(year)
    rs = _build_regular_season_frame(season)

    avg_rating = (
        rs.groupby("Team", as_index=False)["week_rating"]
        .mean()
        .sort_values("week_rating", ascending=False)
        .reset_index(drop=True)
    )

    top_performer_counts = (
        rs.loc[rs["week_rank"] == 1]
        .groupby("Team")
        .size()
        .reindex(season.teams, fill_value=0)
        .sort_values(ascending=False)
    )

    uses_wl = bool(seasonInfoDict[year]["is_WL"])
    if uses_wl:
        non_used_format_name = "Category"
        non_used_standings = season.get_Cats_standings()
    else:
        non_used_format_name = "Matchup W/L"
        non_used_standings = season.get_WL_standings()

    opp_rating = (
        rs.groupby("Team", as_index=False)["week_rating_opp"]
        .mean()
        .sort_values("week_rating_opp", ascending=True)
        .reset_index(drop=True)
    )

    top10_picks, bottom10_picks, draft_score_by_team = _build_draft_tables(year)

    cat_avg = rs.groupby("Team", as_index=False)[mainCats].mean()
    category_rankings = {}
    for cat in mainCats:
        asc = cat == "TO"
        category_rankings[cat] = (
            cat_avg[["Team", cat]]
            .sort_values(cat, ascending=asc)
            .reset_index(drop=True)
        )

    return RegularSeasonRecapData(
        year=year,
        avg_rating=avg_rating,
        top_performer_counts=top_performer_counts,
        non_used_format_name=non_used_format_name,
        non_used_standings=non_used_standings,
        opp_rating=opp_rating,
        top10_picks=top10_picks,
        bottom10_picks=bottom10_picks,
        draft_score_by_team=draft_score_by_team,
        category_rankings=category_rankings,
    )


def render_regular_season_recap_markdown(data: RegularSeasonRecapData) -> str:
    year = data.year
    lines: list[str] = []
    lines.append(f"# {year - 1}/{year} Regular Season Recap")
    lines.append("")

    lines.append("## MVP (Best Average Rating)")
    lines.append(
        f"**Winner:** {data.avg_rating.iloc[0]['Team']} ({_format_number(data.avg_rating.iloc[0]['week_rating'])})"
    )
    lines.append("**Full Ranking (Avg Rating):**")
    lines.append("")
    lines.extend(
        _table(
            ["Rank", "Team", "Avg Rating"],
            [
                [str(i + 1), str(row["Team"]), _format_number(row["week_rating"])]
                for i, row in data.avg_rating.iterrows()
            ],
        )
    )

    lines.append("")
    lines.append("## Worst Player (Worst Average Rating)")
    lines.append(
        f"**Worst:** {data.avg_rating.iloc[-1]['Team']} ({_format_number(data.avg_rating.iloc[-1]['week_rating'])})"
    )
    lines.append("**Full Ranking (Avg Rating, Best to Worst):**")
    lines.append("")
    lines.extend(
        _table(
            ["Rank", "Team", "Avg Rating"],
            [
                [str(i + 1), str(row["Team"]), _format_number(row["week_rating"])]
                for i, row in data.avg_rating.iterrows()
            ],
        )
    )

    lines.append("")
    lines.append("## Top Performer (Most #1 Weekly Ratings)")
    lines.append(
        f"**Winner:** {data.top_performer_counts.index[0]} ({int(data.top_performer_counts.iloc[0])} #1 weeks)"
    )
    lines.append("**Full Ranking (#1 Weekly Ratings):**")
    lines.append("")
    lines.extend(
        _table(
            ["Rank", "Team", "#1 Weeks"],
            [
                [str(i), str(team), str(int(count))]
                for i, (team, count) in enumerate(data.top_performer_counts.items(), start=1)
            ],
        )
    )

    lines.append("")
    lines.append(
        f"## Final Standings ({data.non_used_format_name} Format — Not Used by League This Season)"
    )
    lines.extend(
        _table(
            ["Place", "Team", "Record"],
            [
                [str(place), str(data.non_used_standings[place][0]), str(data.non_used_standings[place][1])]
                for place in sorted(data.non_used_standings.keys())
            ],
        )
    )

    lines.append("")
    lines.append("## Luckiest / Unluckiest (Average Opponent Rating)")
    lines.append(
        f"**Luckiest (lowest avg opp rating):** {data.opp_rating.iloc[0]['Team']} ({_format_number(data.opp_rating.iloc[0]['week_rating_opp'])})"
    )
    lines.append(
        f"**Unluckiest (highest avg opp rating):** {data.opp_rating.iloc[-1]['Team']} ({_format_number(data.opp_rating.iloc[-1]['week_rating_opp'])})"
    )
    lines.append("**Full Ranking (Lowest to Highest Avg Opp Rating):**")
    lines.append("")
    lines.extend(
        _table(
            ["Rank", "Team", "Avg Opp Rating"],
            [
                [str(i + 1), str(row["Team"]), _format_number(row["week_rating_opp"])]
                for i, row in data.opp_rating.iterrows()
            ],
        )
    )

    lines.append("")
    lines.append("## Draft Pick Score (Top 10)")
    lines.extend(
        _table(
            ["Rank", "Overall Pick", "Player", "Team", "Current Yahoo Rank", "Draft Score"],
            [
                [
                    str(i + 1),
                    str(int(row["Overall_num"])),
                    str(row["Player"]),
                    str(row["Team"]),
                    "N/A" if int(row["final_rank"]) == 501 else str(int(row["final_rank"])),
                    _format_signed(row["final_score"]),
                ]
                for i, row in data.top10_picks.reset_index(drop=True).iterrows()
            ],
        )
    )

    lines.append("")
    lines.append("## Draft Pick Score (Bottom 10)")
    lines.extend(
        _table(
            ["Rank", "Overall Pick", "Player", "Team", "Current Yahoo Rank", "Draft Score"],
            [
                [
                    str(i + 1),
                    str(int(row["Overall_num"])),
                    str(row["Player"]),
                    str(row["Team"]),
                    "N/A" if int(row["final_rank"]) == 501 else str(int(row["final_rank"])),
                    _format_signed(row["final_score"]),
                ]
                for i, row in data.bottom10_picks.reset_index(drop=True).iterrows()
            ],
        )
    )

    lines.append("")
    lines.append("## Draft Score (By Team)")
    lines.extend(
        _table(
            ["Rank", "Team", "Draft Score"],
            [
                [str(i + 1), str(row["Team"]), _format_number(row["final_score"])]
                for i, row in data.draft_score_by_team.reset_index(drop=True).iterrows()
            ],
        )
    )

    lines.append("")
    lines.append("## League Leaders by Category (Regular-Season Averages)")
    leader_rows: list[list[str]] = []
    loser_rows: list[list[str]] = []

    for cat, ranked in data.category_rankings.items():
        digits = 3 if "%" in cat else 2
        best = ranked.iloc[0]
        worst = ranked.iloc[-1]
        leader_rows.append(
            [cat, str(best["Team"]), f"{_format_number(best[cat], digits)} {cat}PG"]
        )
        loser_rows.append(
            [cat, str(worst["Team"]), f"{_format_number(worst[cat], digits)} {cat}PG"]
        )

    lines.append("")
    lines.append("### League Leaders Table")
    lines.extend(_table(["Category", "Team", "Stat Value"], leader_rows))

    lines.append("")
    lines.append("### League Losers Table")
    lines.extend(_table(["Category", "Team", "Stat Value"], loser_rows))

    for cat, ranked in data.category_rankings.items():
        digits = 3 if "%" in cat else 2
        best = ranked.iloc[0]
        worst = ranked.iloc[-1]
        lines.append("")
        lines.append(f"### {cat}")
        lines.append(f"**Best:** {best['Team']} ({_format_number(best[cat], digits)})")
        lines.append(f"**Worst:** {worst['Team']} ({_format_number(worst[cat], digits)})")
        lines.append("**Full Ranking:**")
        lines.append("")
        lines.extend(
            _table(
                ["Rank", "Team", cat],
                [
                    [str(i + 1), str(row["Team"]), _format_number(row[cat], digits)]
                    for i, row in ranked.iterrows()
                ],
            )
        )

    return "\n".join(lines) + "\n"


def write_regular_season_recap(year: int, output_path: Path | None = None) -> Path:
    data = build_regular_season_recap_data(year)
    markdown = render_regular_season_recap_markdown(data)
    output = output_path or Path("recaps") / f"{year}_regular_season_recap.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    return output
