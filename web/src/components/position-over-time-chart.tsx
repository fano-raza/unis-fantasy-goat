"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ChartLegend } from "@/components/chart-legend";

// Reshapes standings_history's {team: [{week, rank}]} into one row per week
// with a rank column per team, the shape recharts' LineChart wants.
export function buildHistoryChartData(
  byTeam: Record<string, { week: number; rank: number }[]>,
  minWeek: number,
  maxWeek: number,
): Record<string, number>[] {
  const teams = Object.keys(byTeam);
  const rows: Record<string, number>[] = [];
  for (let week = minWeek; week <= maxWeek; week++) {
    const row: Record<string, number> = { week };
    for (const team of teams) {
      const point = byTeam[team]?.find((p) => p.week === week);
      if (point) row[team] = point.rank;
    }
    rows.push(row);
  }
  return rows;
}

// Shared by Season Standings and League Wins (identical rendering, just
// different underlying rank data/teams/colors) -- each team's standings
// place, week by week over the selected range.
export function PositionOverTimeChart({
  data,
  teams,
  colors,
  weekRange,
  modeLabel,
}: {
  data: Record<string, number>[];
  teams: string[];
  colors: string[];
  weekRange: [number, number];
  modeLabel: "W/L" | "Cats";
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Position Over Time</CardTitle>
        <CardDescription>
          Each team&apos;s {modeLabel} standings place, week by week over the selected range
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-[360px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ left: 8, right: 16, top: 8, bottom: 24 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
              <XAxis
                dataKey="week"
                type="number"
                domain={[weekRange[0], weekRange[1]]}
                ticks={Array.from({ length: weekRange[1] - weekRange[0] + 1 }, (_, i) => weekRange[0] + i)}
                tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
                stroke="var(--border)"
                label={{
                  value: "Week",
                  position: "insideBottom",
                  offset: -4,
                  fill: "var(--muted-foreground)",
                  fontSize: 12,
                }}
              />
              <YAxis
                reversed
                allowDecimals={false}
                domain={[1, teams.length]}
                width={32}
                tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
                stroke="var(--border)"
                label={{
                  value: "Place",
                  angle: -90,
                  position: "insideLeft",
                  fill: "var(--muted-foreground)",
                  fontSize: 12,
                }}
              />
              <Tooltip
                contentStyle={{
                  background: "var(--card)",
                  border: "1px solid var(--border)",
                  fontSize: 12,
                }}
                labelFormatter={(w) => `Week ${w}`}
                itemSorter={(item) => (typeof item.value === "number" ? item.value : Infinity)}
              />
              {teams.map((team, i) => (
                <Line
                  key={team}
                  dataKey={team}
                  name={team}
                  stroke={colors[i]}
                  connectNulls
                  dot={{ r: 2 }}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
        <ChartLegend items={teams.map((team, i) => ({ key: team, color: colors[i] }))} />
      </CardContent>
    </Card>
  );
}
