import { MAIN_CATS, type AnalysisRow } from "./api";

export interface AnalysisField {
  key: string;
  label: string;
  group: "General" | "Stats" | "Ratings" | "Ranks";
  get: (row: AnalysisRow) => number | undefined;
}

export const ANALYSIS_FIELDS: AnalysisField[] = [
  { key: "year", label: "Season", group: "General", get: (r) => r.year },
  { key: "week", label: "Week", group: "General", get: (r) => r.week },
  {
    key: "cat_wins",
    label: "Category Wins",
    group: "General",
    get: (r) => r.cat_wins,
  },
  {
    key: "cat_losses",
    label: "Category Losses",
    group: "General",
    get: (r) => r.cat_losses,
  },
  {
    key: "matchup_win",
    label: "Matchup Win",
    group: "General",
    get: (r) => (r.matchup_win ? 1 : 0),
  },
  {
    key: "matchup_win_pct",
    label: "Matchup Win%",
    group: "General",
    get: (r) => (r.matchup_win ? 100 : 0),
  },
  {
    key: "cat_win_pct",
    label: "Category Win%",
    group: "General",
    get: (r) => {
      const total = r.cat_wins + r.cat_losses + r.cat_ties;
      return total > 0 ? (r.cat_wins / total) * 100 : undefined;
    },
  },
  {
    key: "overall_rating",
    label: "Overall Rating",
    group: "Ratings",
    get: (r) => r.week_rating,
  },
  {
    key: "overall_rank",
    label: "Overall Rank",
    group: "Ranks",
    get: (r) => r.week_rank,
  },
  ...MAIN_CATS.map(
    (cat): AnalysisField => ({
      key: `stat:${cat}`,
      label: cat,
      group: "Stats",
      get: (r) => r.stats[cat],
    }),
  ),
  ...MAIN_CATS.map(
    (cat): AnalysisField => ({
      key: `rating:${cat}`,
      label: `${cat} Rating`,
      group: "Ratings",
      get: (r) => r.ratings[cat],
    }),
  ),
  ...MAIN_CATS.map(
    (cat): AnalysisField => ({
      key: `rank:${cat}`,
      label: `${cat} Rank`,
      group: "Ranks",
      get: (r) => r.ranks[cat],
    }),
  ),
];

export const DEFAULT_X_FIELD = "year";

export function getField(key: string): AnalysisField {
  const field = ANALYSIS_FIELDS.find((f) => f.key === key);
  if (!field) throw new Error(`Unknown analysis field: ${key}`);
  return field;
}
