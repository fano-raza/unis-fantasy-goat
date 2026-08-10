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
import { Checkbox } from "@/components/ui/checkbox";
import { StatTable } from "@/components/stat-table";
import { LabeledSelect, NO_FOCUS_TEAM } from "@/components/labeled-select";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import {
  getAverages,
  getLeagueMeta,
  getSeasonLeaders,
  getTotals,
  MAIN_CATS,
  type AggregateRow,
  type Category,
  type LeagueMeta,
  type SeasonLeadersResponse,
} from "@/lib/api";

function formatCatValue(cat: Category, value: number): string {
  if (cat === "FG%" || cat === "FT%") return value.toFixed(3);
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

export default function SeasonPage() {
  const [meta, setMeta] = useState<LeagueMeta | null>(null);
  const [year, setYear] = useState<number | null>(null);
  const [statMode, setStatMode] = useState<"totals" | "averages">("totals");
  const [rs, setRs] = useState(true);
  const [po, setPo] = useState(true);
  const [focusTeam, setFocusTeam] = useState<string>(NO_FOCUS_TEAM);
  const [rows, setRows] = useState<AggregateRow[]>([]);
  const [leaders, setLeaders] = useState<SeasonLeadersResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getLeagueMeta().then((m) => {
      setMeta(m);
      setYear(m.current_year);
    });
  }, []);

  const weeks = useMemo(() => {
    if (!meta || year == null) return [];
    const maxWeek = meta.total_matchup_count[String(year)] ?? 1;
    return Array.from({ length: maxWeek }, (_, i) => i + 1);
  }, [meta, year]);

  useEffect(() => {
    if (year == null || weeks.length === 0) return;
    const fetcher = statMode === "totals" ? getTotals : getAverages;

    // "Prior" standings: the same season/filter with its single latest week
    // dropped, for the Rank column's green/red movement arrow -- same
    // technique as Career Stats. Skipped for a single-week season.
    const maxWeek = Math.max(...weeks);
    const priorWeeks = weeks.length > 1 ? weeks.filter((w) => w !== maxWeek) : null;

    Promise.all([
      fetcher({ years: [year], weeks, RS: rs, PO: po }),
      priorWeeks ? fetcher({ years: [year], weeks: priorWeeks, RS: rs, PO: po }) : Promise.resolve(null),
      getSeasonLeaders({ years: [year], weeks, RS: rs, PO: po, mode: statMode }),
    ])
      .then(([current, prior, leadersRes]) => {
        const priorRanks = new Map((prior ?? []).map((r) => [r.team, r.rank]));
        setRows(current.map((r) => ({ ...r, previousRank: priorRanks.get(r.team) ?? null })));
        setLeaders(leadersRes);
        setError(null);
      })
      .catch((err) => {
        setRows([]);
        setLeaders(null);
        setError(err instanceof Error ? err.message : String(err));
      });
  }, [year, weeks, statMode, rs, po]);

  // Only teams actually shown in the current filtered rows, not the full
  // league roster.
  const focusOptions = useMemo(() => [...rows.map((r) => r.team)].sort(), [rows]);

  // Default (and re-default, if the current focus team disappears from a
  // new year/filter's rows) to whichever team ranks #1.
  useEffect(() => {
    const teamsShown = new Set(rows.map((r) => r.team));
    if (focusTeam !== NO_FOCUS_TEAM && teamsShown.has(focusTeam)) return;
    const topTeam = rows.find((r) => r.rank === 1);
    setFocusTeam(topTeam?.team ?? NO_FOCUS_TEAM);
  }, [rows, focusTeam]);

  if (!meta || year == null) return <LoadingBasketballs label="Loading" />;

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Season</CardTitle>
          <CardDescription>
            Ratings, leaders, and losers for a single season
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-6">
          <LabeledSelect
            label="Season"
            value={String(year)}
            onValueChange={(v) => setYear(Number(v))}
            options={meta.years.map((y) => ({ value: String(y), label: String(y) }))}
          />
          <label className="flex items-center gap-2 text-[11px] font-bold tracking-wider uppercase">
            <span className="text-muted-foreground">Totals</span>
            <Switch
              checked={statMode === "averages"}
              onCheckedChange={(checked) => setStatMode(checked ? "averages" : "totals")}
            />
            <span className="text-muted-foreground">Averages</span>
          </label>
          <div className="flex items-center gap-3 text-[11px] font-bold tracking-wider uppercase">
            <label className="flex items-center gap-1.5">
              <Checkbox checked={rs} onCheckedChange={() => setRs((v) => !v)} />
              <span className="text-muted-foreground">Reg Season</span>
            </label>
            <label className="flex items-center gap-1.5">
              <Checkbox checked={po} onCheckedChange={() => setPo((v) => !v)} />
              <span className="text-muted-foreground">Playoffs</span>
            </label>
          </div>
          <LabeledSelect
            label="Focus team"
            value={focusTeam}
            onValueChange={setFocusTeam}
            options={[
              { value: NO_FOCUS_TEAM, label: "None" },
              ...focusOptions.map((m) => ({ value: m, label: m })),
            ]}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Ratings</CardTitle>
          <CardDescription>Ranked by overall Weighted Rank rating</CardDescription>
        </CardHeader>
        <CardContent>
          {error ? (
            <p className="text-sm text-muted-foreground">No data for the current filters ({error}).</p>
          ) : (
            <StatTable
              rows={rows}
              mode="stat"
              focusTeam={focusTeam === NO_FOCUS_TEAM ? undefined : focusTeam}
            />
          )}
        </CardContent>
      </Card>

      {leaders && (
        <Card>
          <CardHeader>
            <CardTitle>Category Leaders &amp; Losers</CardTitle>
            <CardDescription>Best and worst team per category this season</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
              {MAIN_CATS.map((cat) => {
                const entry = leaders[cat];
                if (!entry) return null;
                return (
                  <div key={cat} className="rounded-sm border border-border p-3">
                    <div className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase">
                      {cat}
                    </div>
                    <div className="mt-2 flex items-center justify-between gap-2">
                      <span className="text-xs font-bold tracking-wide text-foreground uppercase">
                        {entry.best.team}
                      </span>
                      <span className="font-mono text-sm font-extrabold tabular-nums text-foreground">
                        {formatCatValue(cat, entry.best.value)}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center justify-between gap-2">
                      <span className="text-xs font-bold tracking-wide text-muted-foreground uppercase">
                        {entry.worst.team}
                      </span>
                      <span className="font-mono text-sm font-extrabold tabular-nums text-muted-foreground">
                        {formatCatValue(cat, entry.worst.value)}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
