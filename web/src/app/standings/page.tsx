"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { LabeledSelect } from "@/components/labeled-select";
import {
  getLeagueMeta,
  getStandings,
  type LeagueMeta,
  type StandingsResponse,
  type StandingsRow,
} from "@/lib/api";

// Games Behind: leader's score minus this row's score, score = wins + 0.5*ties
// (the user's own explicit formula -- note this is a plain half-point, not
// the 0.49 tie-weight fudge factor used for ranking tiebreaks elsewhere in
// this app). Leader shows "-" (standard sports-table convention for GB=0).
function gamesBehind(rows: StandingsRow[]): Map<string, number> {
  const score = (r: StandingsRow) => r.wins + 0.5 * r.ties;
  const leaderScore = Math.max(...rows.map(score));
  return new Map(rows.map((r) => [r.team, leaderScore - score(r)]));
}

function formatGB(value: number): string {
  if (value === 0) return "-";
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function StandingsTable({ rows }: { rows: StandingsRow[] }) {
  const gb = gamesBehind(rows);
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Place</TableHead>
          <TableHead>Team</TableHead>
          <TableHead className="text-right">Record</TableHead>
          <TableHead className="text-right">GB</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.team}>
            <TableCell>{row.rank}</TableCell>
            <TableCell className="font-sans font-extrabold tracking-wide uppercase">
              {row.team}
            </TableCell>
            <TableCell className="text-right">
              {row.wins}-{row.losses}-{row.ties}
            </TableCell>
            <TableCell className="text-right">{formatGB(gb.get(row.team) ?? 0)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export default function StandingsPage() {
  const [meta, setMeta] = useState<LeagueMeta | null>(null);
  const [year, setYear] = useState<number | null>(null);
  const [weekRange, setWeekRange] = useState<[number, number] | null>(null);
  const [oneVOneMode, setOneVOneMode] = useState<"wl" | "cats">("wl");
  const [leagueMode, setLeagueMode] = useState<"wl" | "cats">("wl");
  const [standings, setStandings] = useState<StandingsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getLeagueMeta().then((m) => {
      setMeta(m);
      setYear(m.current_year);
    });
  }, []);

  const maxWeek = useMemo(() => {
    if (!meta || year == null) return 1;
    return meta.rs_week_count[String(year)] ?? 1;
  }, [meta, year]);

  // Default both toggles to whatever format that season actually used
  // (some years were scored by matchup W/L, others by aggregate category
  // wins -- see dashboard_site/api/league_store.py's SEASON_IS_WL). Resets
  // whenever the year changes, also covering the initial load.
  useEffect(() => {
    if (!meta || year == null) return;
    const format = meta.season_format[String(year)] ?? "wl";
    setOneVOneMode(format);
    setLeagueMode(format);
  }, [meta, year]);

  // Reset to the full RS range whenever the year changes (also covers the
  // initial load, once meta/year are both set).
  useEffect(() => {
    if (!meta || year == null) return;
    setWeekRange([1, maxWeek]);
  }, [meta, year, maxWeek]);

  // Debounced live-refetch -- a slider drag fires many intermediate values,
  // and this payload is tiny (a handful of teams' summed W-L-T), so a full
  // Apply-gated flow (like Career Stats/Analysis' mobile filter drawer)
  // would be unnecessary friction here.
  useEffect(() => {
    if (year == null || !weekRange) return;
    const timeout = setTimeout(() => {
      getStandings({ year, min_week: weekRange[0], max_week: weekRange[1] })
        .then((r) => {
          setStandings(r);
          setError(null);
        })
        .catch((err) => {
          setStandings(null);
          setError(err instanceof Error ? err.message : String(err));
        });
    }, 200);
    return () => clearTimeout(timeout);
  }, [year, weekRange]);

  if (!meta || year == null || !weekRange) return null;

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Standings</CardTitle>
          <CardDescription>
            Regular-season standings for any week range
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          <LabeledSelect
            label="Season"
            value={String(year)}
            onValueChange={(v) => setYear(Number(v))}
            options={meta.years.map((y) => ({ value: String(y), label: String(y) }))}
          />
          <div className="flex flex-col gap-3">
            <span className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase">
              Week {weekRange[0]} &ndash; Week {weekRange[1]}
            </span>
            <Slider
              min={1}
              max={maxWeek}
              step={1}
              value={weekRange}
              onValueChange={(v) => setWeekRange(v as [number, number])}
            />
          </div>
        </CardContent>
      </Card>

      {error ? (
        <Card>
          <CardContent>
            <p className="text-sm text-muted-foreground">No data for the current filters ({error}).</p>
          </CardContent>
        </Card>
      ) : (
        standings && (
          <>
            <Card>
              <CardHeader>
                <CardTitle>1v1 Standings</CardTitle>
                <CardDescription>Real matchup win-loss-tie record, by matchup outcome or aggregate category record</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <label className="flex items-center gap-2 self-start text-[11px] font-bold tracking-wider uppercase">
                  <span className="text-muted-foreground">W/L</span>
                  <Switch
                    checked={oneVOneMode === "cats"}
                    onCheckedChange={(checked) => setOneVOneMode(checked ? "cats" : "wl")}
                  />
                  <span className="text-muted-foreground">Cats</span>
                </label>
                <StandingsTable rows={oneVOneMode === "wl" ? standings.wl : standings.cats} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>League Wins Standings</CardTitle>
                <CardDescription>
                  All-play record -- every team vs. every other team, every week
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <label className="flex items-center gap-2 self-start text-[11px] font-bold tracking-wider uppercase">
                  <span className="text-muted-foreground">W/L</span>
                  <Switch
                    checked={leagueMode === "cats"}
                    onCheckedChange={(checked) => setLeagueMode(checked ? "cats" : "wl")}
                  />
                  <span className="text-muted-foreground">Cats</span>
                </label>
                <StandingsTable rows={leagueMode === "wl" ? standings.league_wl : standings.league_cats} />
              </CardContent>
            </Card>
          </>
        )
      )}
    </div>
  );
}
