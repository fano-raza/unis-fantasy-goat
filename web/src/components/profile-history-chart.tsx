"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { getAnalysisRows, getRsFinishHistory, type LeagueMeta } from "@/lib/api";

type YMode = "rating" | "place";

interface SeasonPoint {
  year: number;
  rating?: number;
  place?: number;
}

export function ProfileHistoryChart({ team, meta }: { team: string; meta: LeagueMeta }) {
  const [points, setPoints] = useState<SeasonPoint[] | null>(null);
  const [mode, setMode] = useState<YMode>("rating");

  useEffect(() => {
    let cancelled = false;

    getAnalysisRows({ teams: [team], RS: true, PO: false }).then(async (rows) => {
      if (cancelled) return;

      // Rating-by-season: average week_rating per year -- mirrors
      // Models/team_profile.py's own avg_rating calc (rs_df["week_rating"].mean()),
      // so this matches what "Best RS Rating" elsewhere on this page is built from.
      const byYear = new Map<number, number[]>();
      for (const row of rows) {
        const list = byYear.get(row.year) ?? [];
        list.push(row.week_rating);
        byYear.set(row.year, list);
      }
      const years = [...byYear.keys()].sort((a, b) => a - b);
      const ratingByYear = new Map(
        years.map((y) => {
          const list = byYear.get(y)!;
          return [y, list.reduce((a, b) => a + b, 0) / list.length] as const;
        }),
      );

      // RS place finish per season -- one bulk call covering every team/
      // year (server-cached, see LeagueStore.rs_finish_history) instead of
      // one /league/standings request per season this team played (used to
      // be up to 8 client-side round trips on a single Profile page load).
      const finishHistory = await getRsFinishHistory();
      const placeByYear = new Map(
        years.map((year) => [year, finishHistory[String(year)]?.[team]] as const),
      );

      if (!cancelled) {
        setPoints(
          years.map((year) => ({
            year,
            rating: ratingByYear.get(year),
            place: placeByYear.get(year),
          })),
        );
      }
    });

    return () => {
      cancelled = true;
    };
  }, [team, meta]);

  const chartData = useMemo(
    () => (points ?? []).map((p) => ({ year: p.year, value: mode === "rating" ? p.rating : p.place })),
    [points, mode],
  );

  if (!points || points.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Rating &amp; Standing Over Time</CardTitle>
        <CardDescription>Regular-season performance across every year {team} has played</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <label className="flex items-center gap-2 self-start text-[11px] font-bold tracking-wider uppercase">
          <span className="text-muted-foreground">Overall Rating</span>
          <Switch
            checked={mode === "place"}
            onCheckedChange={(checked) => setMode(checked ? "place" : "rating")}
          />
          <span className="text-muted-foreground">RS Place Finish</span>
        </label>
        <div className="h-[320px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ left: 8, right: 16, top: 8, bottom: 24 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
              <XAxis
                dataKey="year"
                type="number"
                domain={["dataMin", "dataMax"]}
                ticks={points.map((p) => p.year)}
                tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
                stroke="var(--border)"
                label={{
                  value: "Season",
                  position: "insideBottom",
                  offset: -4,
                  fill: "var(--muted-foreground)",
                  fontSize: 12,
                }}
              />
              {mode === "rating" ? (
                <YAxis
                  domain={[0, 100]}
                  width={40}
                  tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
                  stroke="var(--border)"
                  label={{
                    value: "Overall Rating",
                    angle: -90,
                    position: "insideLeft",
                    fill: "var(--muted-foreground)",
                    fontSize: 12,
                  }}
                />
              ) : (
                <YAxis
                  reversed
                  allowDecimals={false}
                  domain={[1, meta.members.length]}
                  width={32}
                  tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
                  stroke="var(--border)"
                  label={{
                    value: "RS Place Finish",
                    angle: -90,
                    position: "insideLeft",
                    fill: "var(--muted-foreground)",
                    fontSize: 12,
                  }}
                />
              )}
              <Tooltip
                contentStyle={{
                  background: "var(--card)",
                  border: "1px solid var(--border)",
                  fontSize: 12,
                }}
                labelFormatter={(y) => `Season ${y}`}
                formatter={(value) => [
                  typeof value === "number" ? value.toFixed(mode === "rating" ? 1 : 0) : String(value),
                  mode === "rating" ? "Overall Rating" : "RS Place Finish",
                ]}
              />
              <Line
                dataKey="value"
                name={team}
                stroke="var(--primary)"
                connectNulls
                dot={{ r: 3 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
