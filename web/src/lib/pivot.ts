import type { AnalysisRow } from "./api";
import type { AnalysisField } from "./fields";

export interface GroupBy {
  team: boolean;
  season: boolean;
  // Off by default -- when off, rows for the same (team[/season], X value)
  // across different weeks are averaged together (pivot()'s normal
  // bucketing), same as before this option existed. When on, each week
  // becomes its own series/point instead of being averaged away.
  week: boolean;
}

export interface PivotResult {
  chartData: Record<string, number>[];
  seriesKeys: string[];
}

export interface ScatterSeries {
  key: string;
  points: { x: number; y: number }[];
}

function groupKeyFor(row: AnalysisRow, groupBy: GroupBy): string {
  const parts: string[] = [];
  if (groupBy.team) parts.push(row.team);
  if (groupBy.season) parts.push(String(row.year));
  if (groupBy.week) parts.push(`Wk${row.week}`);
  return parts.length ? parts.join(" ") : "All";
}

// Groups filtered rows by (group key, X value), averages Y within each
// bucket, sorts by X, one series per group key (or a single "All" series if
// neither Team nor Season grouping is enabled). Appropriate when X is a
// natural progression (Season/Week) -- see pivotScatter for continuous X
// fields (a stat/rating/rank), where bucketing by exact X match is
// meaningless (coincidental float collisions, not real grouping).
export function pivot(
  rows: AnalysisRow[],
  xField: AnalysisField,
  yField: AnalysisField,
  groupBy: GroupBy,
): PivotResult {
  const buckets = new Map<string, Map<number, number[]>>();
  for (const row of rows) {
    const x = xField.get(row);
    const y = yField.get(row);
    if (x === undefined || y === undefined) continue;
    const key = groupKeyFor(row, groupBy);
    if (!buckets.has(key)) buckets.set(key, new Map());
    const xMap = buckets.get(key)!;
    if (!xMap.has(x)) xMap.set(x, []);
    xMap.get(x)!.push(y);
  }

  const seriesKeys = Array.from(buckets.keys()).sort();
  const series = seriesKeys.map((key) => {
    const xMap = buckets.get(key)!;
    const points = Array.from(xMap.entries())
      .map(([x, ys]) => ({ x, y: ys.reduce((a, b) => a + b, 0) / ys.length }))
      .sort((a, b) => a.x - b.x);
    return { key, points };
  });

  const allX = Array.from(new Set(series.flatMap((s) => s.points.map((p) => p.x)))).sort(
    (a, b) => a - b,
  );
  const chartData = allX.map((x) => {
    const point: Record<string, number> = { x };
    for (const s of series) {
      const found = s.points.find((p) => p.x === x);
      if (found) point[s.key] = found.y;
    }
    return point;
  });

  return { chartData, seriesKeys };
}

// For continuous X fields (a stat/rating/rank, not Season/Week): no
// bucketing or averaging -- every row is its own point. Grouping by exact
// X match only makes sense for a handful of discrete values (real "same
// year" grouping); for a per-week rating value it's just coincidental
// float collisions, and connecting the resulting points with a line (as
// `pivot`'s LineChart output does) draws a meaningless zigzag through
// points sorted by a stat value rather than time.
export function pivotScatter(
  rows: AnalysisRow[],
  xField: AnalysisField,
  yField: AnalysisField,
  groupBy: GroupBy,
): ScatterSeries[] {
  const buckets = new Map<string, { x: number; y: number }[]>();
  for (const row of rows) {
    const x = xField.get(row);
    const y = yField.get(row);
    if (x === undefined || y === undefined) continue;
    const key = groupKeyFor(row, groupBy);
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key)!.push({ x, y });
  }

  return Array.from(buckets.keys())
    .sort()
    .map((key) => ({ key, points: buckets.get(key)! }));
}
