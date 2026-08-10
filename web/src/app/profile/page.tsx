"use client";

import { useEffect, useMemo, useState, type ComponentType } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { StatTable } from "@/components/stat-table";
import { Medal, Star, Trophy } from "lucide-react";
import {
  getAverages,
  getLeagueMeta,
  getTeamSummary,
  getTotals,
  MAIN_CATS,
  type AggregateRow,
  type Category,
  type LeagueMeta,
  type TeamSummary,
} from "@/lib/api";
import { NEG_CATS } from "@/lib/highlight";
import { comparableFields, formatValue, ordinal, rankFor } from "@/lib/team-summary-fields";

// Excluded from the "League Top 3" list -- either already shown as its own
// stat tile above (nothing should appear twice), or asked to be dropped
// outright (Best/Worst Week Rating: a single-week fluke isn't a meaningful
// "career" top-3 stat).
const TOP3_EXCLUDED = new Set([
  "Championships",
  "Championship Years",
  "MVPs",
  "MVP Years",
  "Best RS Rating",
  "Best RS Rating Years",
  "RS 1st Place",
  "RS 1st Years",
  "Best RS Finish",
  "Best RS Finish Years",
  "Best Week Rating",
  "Worst Week Rating",
]);

// Standard competition ranking for a raw category value across totals/
// averages rows -- same direction convention (NEG_CATS) as the Weekly
// Stats Score column, applied to whichever AggregateRow[] (totals or
// averages) is passed in.
function rankForCategory(cat: Category, rows: AggregateRow[], team: string): number | undefined {
  const target = rows.find((r) => r.team === team);
  const value = target?.stats[cat];
  if (value === undefined) return undefined;
  const higherIsBetter = !NEG_CATS.includes(cat);
  const better = rows.filter((r) => {
    const v = r.stats[cat];
    return v !== undefined && (higherIsBetter ? v > value : v < value);
  }).length;
  return better + 1;
}

const SELECTED_TEAM_KEY = "profile-selected-team";

function splitYears(value: string | number | null | undefined): string {
  if (typeof value !== "string" || !value.trim()) return "—";
  return value;
}

export default function ProfilePage() {
  const [meta, setMeta] = useState<LeagueMeta | null>(null);
  const [allTeams, setAllTeams] = useState<TeamSummary[]>([]);
  const [totals, setTotals] = useState<AggregateRow[]>([]);
  const [averages, setAverages] = useState<AggregateRow[]>([]);
  const [team, setTeam] = useState<string | null>(null);

  useEffect(() => {
    getLeagueMeta().then((m) => {
      setMeta(m);
      let restored = m.members[0] ?? null;
      try {
        const saved = localStorage.getItem(SELECTED_TEAM_KEY);
        if (saved && m.members.includes(saved)) restored = saved;
      } catch {}
      setTeam(restored);
    });
    getTeamSummary({}).then(setAllTeams);
    getTotals({}).then(setTotals);
    getAverages({}).then(setAverages);
  }, []);

  useEffect(() => {
    if (team) localStorage.setItem(SELECTED_TEAM_KEY, team);
  }, [team]);

  const profile = allTeams.find((r) => r.Team === team);
  const totalsRow = totals.find((r) => r.team === team);
  const averagesRow = averages.find((r) => r.team === team);

  const playoffFinish = useMemo(() => {
    if (!profile) return null;
    const chipYears = typeof profile["Championship Years"] === "string" ? profile["Championship Years"] : "";
    const finalsYears = typeof profile["Finals Years"] === "string" ? profile["Finals Years"] : "";
    const playoffYears = typeof profile["Playoff Years"] === "string" ? profile["Playoff Years"] : "";
    if (chipYears) return { label: "Champion", years: chipYears };
    if (finalsYears) return { label: "Runner-up", years: finalsYears };
    if (playoffYears) return { label: "Made Playoffs", years: playoffYears };
    return { label: "Did Not Qualify", years: "—" };
  }, [profile]);

  const topFields = useMemo(() => {
    if (!team || allTeams.length === 0) return [];
    const summaryFields = comparableFields(allTeams)
      .filter((f) => !TOP3_EXCLUDED.has(f))
      .map((field) => ({
        field,
        rank: rankFor(field, allTeams, team),
        value: allTeams.find((r) => r.Team === team)?.[field] ?? null,
      }));

    const statFields =
      totals.length && averages.length
        ? MAIN_CATS.flatMap((cat) => [
            {
              field: `Total ${cat}`,
              rank: rankForCategory(cat, totals, team),
              value: totals.find((r) => r.team === team)?.stats[cat] ?? null,
            },
            {
              field: `Avg ${cat}`,
              rank: rankForCategory(cat, averages, team),
              value: averages.find((r) => r.team === team)?.stats[cat] ?? null,
            },
          ])
        : [];

    return [...summaryFields, ...statFields]
      .filter((r): r is { field: string; rank: number; value: string | number | null } => r.rank !== undefined && r.rank <= 3)
      .sort((a, b) => a.rank - b.rank);
  }, [team, allTeams, totals, averages]);

  if (!meta || !team) return null;

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Career Profile</CardTitle>
          <CardDescription>Full career snapshot for one team</CardDescription>
        </CardHeader>
        <CardContent>
          <label className="flex items-center gap-2">
            <span className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase">
              Team
            </span>
            <Select value={team} onValueChange={(v) => v !== null && setTeam(v)}>
              <SelectTrigger size="sm">
                <SelectValue>{(v: string) => v}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {meta.members.map((m) => (
                  <SelectItem key={m} value={m}>
                    {m}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
        </CardContent>
      </Card>

      {profile && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <StatTile
            label="Championships"
            value={profile.Championships ?? 0}
            sub={splitYears(profile["Championship Years"])}
            icon={Trophy}
          />
          <StatTile label="MVPs" value={profile.MVPs ?? 0} sub={splitYears(profile["MVP Years"])} icon={Star} />
          <StatTile
            label="Best RS Rating"
            value={typeof profile["Best RS Rating"] === "number" ? profile["Best RS Rating"].toFixed(1) : "—"}
            sub={splitYears(profile["Best RS Rating Years"])}
          />
          <StatTile
            label="RS 1st Place"
            value={profile["RS 1st Place"] ?? 0}
            sub={splitYears(profile["RS 1st Years"])}
            icon={Medal}
          />
          <StatTile
            label="Best RS Finish"
            value={typeof profile["Best RS Finish"] === "number" ? ordinal(profile["Best RS Finish"]) : "—"}
            sub={splitYears(profile["Best RS Finish Years"])}
          />
          {playoffFinish && (
            <StatTile label="Best Playoff Finish" value={playoffFinish.label} sub={playoffFinish.years} />
          )}
        </div>
      )}

      {topFields.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>League Top 3</CardTitle>
            <CardDescription>
              Every career stat where {team} ranks in the top 3 league-wide
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Stat</TableHead>
                  <TableHead className="text-right">Value</TableHead>
                  <TableHead className="text-right">Rank</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {topFields.map((row) => (
                  <TableRow key={row.field}>
                    <TableCell className="font-sans font-medium text-muted-foreground">
                      {row.field}
                    </TableCell>
                    <TableCell className="text-right">{formatValue(row.value)}</TableCell>
                    <TableCell className="text-right font-extrabold text-primary">
                      {ordinal(row.rank)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Career Totals</CardTitle>
          <CardDescription>League-wide rank included</CardDescription>
        </CardHeader>
        <CardContent>
          {totalsRow ? (
            <StatTable rows={[totalsRow]} mode="stat" />
          ) : (
            <p className="text-sm text-muted-foreground">No data.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Career Averages</CardTitle>
          <CardDescription>League-wide rank included</CardDescription>
        </CardHeader>
        <CardContent>
          {averagesRow ? (
            <StatTable rows={[averagesRow]} mode="stat" />
          ) : (
            <p className="text-sm text-muted-foreground">No data.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function StatTile({
  label,
  value,
  sub,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  sub: string;
  // Rendered once per count when value is a number (e.g. 2 championships ->
  // 2 trophies), not just once as a static decoration.
  icon?: ComponentType<{ className?: string }>;
}) {
  const iconCount = Icon && typeof value === "number" ? value : 0;
  return (
    <div className="rounded-sm border border-border p-4">
      <div className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase">
        {label}
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-1.5">
        <span className="font-mono text-3xl font-extrabold tracking-wide text-primary uppercase tabular-nums">
          {value}
        </span>
        {Icon &&
          iconCount > 0 &&
          Array.from({ length: iconCount }, (_, i) => (
            <Icon key={i} className="size-4 text-amber-400" />
          ))}
      </div>
      <div className="mt-1 text-xs text-muted-foreground">{sub}</div>
    </div>
  );
}
