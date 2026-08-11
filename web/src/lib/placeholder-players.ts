import { type CategoryStats } from "./api";

// Trade Box has zero real player-level data source in this repo (confirmed
// repo-wide -- everything else here is fantasy-team-vs-team box scores, not
// individual player stats). This is placeholder data ONLY, so the UI shape
// (picker, 9-cat comparison, difference row) can be built and demoed now.
// Swap this file out entirely once a real player stats feed (past + a real
// projection source) is chosen -- see _planning/web-app-build-plan.md.
export interface PlaceholderPlayer {
  name: string;
  pastAvg: CategoryStats;
  predictedAvg: CategoryStats;
  // Games played (past) / games in a full season (predicted) -- used to
  // derive a "Totals" view from the per-game averages below.
  pastGames: number;
  predictedGames: number;
}

export const PLACEHOLDER_PLAYERS: PlaceholderPlayer[] = [
  {
    name: "A. Sample Wing",
    pastAvg: { "FG%": 0.48, "FT%": 0.82, "3PTM": 2.1, REB: 4.8, AST: 5.2, STL: 1.1, BLK: 0.4, TO: 2.3, PTS: 24.6 },
    predictedAvg: { "FG%": 0.49, "FT%": 0.83, "3PTM": 2.3, REB: 5.0, AST: 5.5, STL: 1.1, BLK: 0.4, TO: 2.2, PTS: 25.8 },
    pastGames: 68,
    predictedGames: 82,
  },
  {
    name: "B. Sample Big",
    pastAvg: { "FG%": 0.58, "FT%": 0.71, "3PTM": 0.3, REB: 11.4, AST: 2.8, STL: 0.8, BLK: 1.9, TO: 2.1, PTS: 19.2 },
    predictedAvg: { "FG%": 0.6, "FT%": 0.73, "3PTM": 0.4, REB: 11.9, AST: 3.0, STL: 0.8, BLK: 2.0, TO: 2.0, PTS: 20.5 },
    pastGames: 74,
    predictedGames: 82,
  },
  {
    name: "C. Sample Guard",
    pastAvg: { "FG%": 0.44, "FT%": 0.88, "3PTM": 3.2, REB: 3.1, AST: 7.9, STL: 1.4, BLK: 0.2, TO: 3.1, PTS: 22.4 },
    predictedAvg: { "FG%": 0.45, "FT%": 0.88, "3PTM": 3.4, REB: 3.2, AST: 8.3, STL: 1.4, BLK: 0.2, TO: 3.0, PTS: 23.1 },
    pastGames: 71,
    predictedGames: 82,
  },
  {
    name: "D. Sample Forward",
    pastAvg: { "FG%": 0.51, "FT%": 0.76, "3PTM": 1.6, REB: 7.9, AST: 3.4, STL: 1.0, BLK: 0.7, TO: 1.8, PTS: 17.8 },
    predictedAvg: { "FG%": 0.52, "FT%": 0.77, "3PTM": 1.7, REB: 8.1, AST: 3.5, STL: 1.0, BLK: 0.7, TO: 1.8, PTS: 18.4 },
    pastGames: 79,
    predictedGames: 82,
  },
  {
    name: "E. Sample Sixth Man",
    pastAvg: { "FG%": 0.46, "FT%": 0.8, "3PTM": 2.6, REB: 3.6, AST: 3.1, STL: 0.9, BLK: 0.3, TO: 1.6, PTS: 15.9 },
    predictedAvg: { "FG%": 0.46, "FT%": 0.8, "3PTM": 2.7, REB: 3.7, AST: 3.2, STL: 0.9, BLK: 0.3, TO: 1.6, PTS: 16.4 },
    pastGames: 65,
    predictedGames: 78,
  },
  {
    name: "F. Sample Rookie",
    pastAvg: { "FG%": 0.42, "FT%": 0.68, "3PTM": 1.1, REB: 4.4, AST: 2.2, STL: 0.7, BLK: 0.5, TO: 1.9, PTS: 10.8 },
    predictedAvg: { "FG%": 0.45, "FT%": 0.72, "3PTM": 1.5, REB: 5.0, AST: 2.6, STL: 0.8, BLK: 0.5, TO: 1.7, PTS: 13.5 },
    pastGames: 58,
    predictedGames: 75,
  },
  {
    name: "G. Sample Vet",
    pastAvg: { "FG%": 0.47, "FT%": 0.85, "3PTM": 2.0, REB: 4.1, AST: 4.6, STL: 1.2, BLK: 0.3, TO: 2.0, PTS: 18.9 },
    predictedAvg: { "FG%": 0.46, "FT%": 0.84, "3PTM": 1.9, REB: 3.9, AST: 4.3, STL: 1.1, BLK: 0.3, TO: 2.0, PTS: 17.6 },
    pastGames: 76,
    predictedGames: 80,
  },
  {
    name: "H. Sample Stretch Big",
    pastAvg: { "FG%": 0.44, "FT%": 0.79, "3PTM": 2.4, REB: 8.6, AST: 1.8, STL: 0.6, BLK: 1.1, TO: 1.4, PTS: 16.2 },
    predictedAvg: { "FG%": 0.44, "FT%": 0.8, "3PTM": 2.5, REB: 8.8, AST: 1.9, STL: 0.6, BLK: 1.1, TO: 1.4, PTS: 16.8 },
    pastGames: 70,
    predictedGames: 82,
  },
];

// Total = per-game average x games played -- a placeholder derivation, not
// a real accumulated-game total.
export function toTotal(avg: CategoryStats, games: number): CategoryStats {
  const result: CategoryStats = {};
  for (const [cat, value] of Object.entries(avg)) {
    if (value !== undefined) result[cat as keyof CategoryStats] = value * games;
  }
  return result;
}
