"use client";

import { Suspense, useEffect, useMemo, useState, type ComponentType } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  Card,
  CardAction,
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
import { RoutedViewSwitcher } from "@/components/routed-view-switcher";
import { SourceLastUpdated } from "@/components/source-last-updated";
import { Podium, Star, Trophy } from "lucide-react";
import {
  getAverages,
  getCategoryHistory,
  getLeagueMeta,
  getQuery,
  getTeamSummary,
  getTotals,
  MAIN_CATS,
  type AggregateRow,
  type Category,
  type CategoryHistoryResponse,
  type LeagueMeta,
  type QueryRow,
  type TeamSummary,
} from "@/lib/api";
import { NEG_CATS } from "@/lib/highlight";
import { comparableFields, formatValue, ordinal, rankFor } from "@/lib/team-summary-fields";
import { cn } from "@/lib/utils";
import { ProfileHistoryChart } from "@/components/profile-history-chart";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { buildBadges, POSITIVE_BADGE_TYPES } from "@/lib/badges";
import { TeamBadges } from "@/components/team-badges";
import { BadgeDrawer } from "@/components/badge-drawer";
import { SELECTED_TEAM_STORAGE_KEY } from "@/lib/use-selected-team";

const VIEW_OPTIONS = [
  { value: "profile", label: "Profile" },
  { value: "comparison", label: "Comparison" },
  { value: "roster", label: "Roster" },
];
const VIEW_PATHS = { profile: "/profile", comparison: "/profile/comparison", roster: "/profile/roster" };

// Gold / silver / bronze for the League Top 3 table's 1st/2nd/3rd rank text
// -- topFields is always filtered to rank <= 3, so no 4th-place case exists.
function rankColorClass(rank: number): string {
  if (rank === 1) return "text-[#d4af37]";
  if (rank === 2) return "text-[#c0c0c0]";
  return "text-[#cd7f32]";
}

// Excluded from the "League Top 3" list -- either not rankable (year lists
// paired with a count field already included) or asked to be dropped
// outright (Best/Worst Week Rating: a single-week fluke isn't a meaningful
// "career" top-3 stat). Championships/MVPs/RS 1st Place are shown both as
// their own stat tile above AND here -- the user asked for them included.
const TOP3_EXCLUDED = new Set([
  "Championship Years",
  "MVP Years",
  "Worst Ratings",
  "Worst Rating Years",
  "Best RS Rating",
  "Best RS Rating Years",
  "RS 1st Years",
  "RS Last Place",
  "RS Last Years",
  "Best RS Finish",
  "Best RS Finish Years",
  "Best Week Rating",
  "Worst Week Rating",
  // Redundant with the rating fields already shown -- same reasoning as
  // COMPARISON_EXCLUDED_FIELDS in team-summary-fields.ts.
  "Avg Weighted Rank",
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

const SELECTED_TEAM_KEY = SELECTED_TEAM_STORAGE_KEY;

// Win/loss career totals for the "League Top 3" table -- not present in
// team_summary.csv (that has W-L-T strings, not individually rankable
// counts), so pulled from the generic /query endpoint instead of a new
// export. "Total"/"Total Category" scope both RS+PO; the rest split by
// season. Losses rank "lower is better" (fewest losses = rank 1), the same
// convention this app already uses for "Worst Losing Streak"/"Lowest
// Rating Weeks" in web/src/lib/team-summary-fields.ts.
interface QueryTotalField {
  label: string;
  metric: string;
  seasons?: string[];
  direction: "higher" | "lower";
}

const QUERY_TOTAL_FIELDS: QueryTotalField[] = [
  // Same underlying /query data is also surfaced as its own row on the
  // Comparison page's table (app/profile/comparison/page.tsx) under this
  // same field name -- keep the two in sync if either changes.
  { label: "Matchup Wins", metric: "MATCHUP_WINS", seasons: ["RS", "PO"], direction: "higher" },
  { label: "Total Losses", metric: "MATCHUP_LOSSES", seasons: ["RS", "PO"], direction: "lower" },
  { label: "Category Wins", metric: "CAT_WINS", seasons: ["RS", "PO"], direction: "higher" },
  { label: "Total Category Losses", metric: "CAT_LOSSES", seasons: ["RS", "PO"], direction: "lower" },
  { label: "Total Reg Season Wins", metric: "MATCHUP_WINS", seasons: ["RS"], direction: "higher" },
  { label: "Total Reg Season Losses", metric: "MATCHUP_LOSSES", seasons: ["RS"], direction: "lower" },
  { label: "Playoff Wins", metric: "MATCHUP_WINS", seasons: ["PO"], direction: "higher" },
  { label: "Total Playoff Losses", metric: "MATCHUP_LOSSES", seasons: ["PO"], direction: "lower" },
];

function rankFromQueryRows(
  rows: QueryRow[],
  team: string,
  direction: "higher" | "lower",
): { rank: number; value: number } | undefined {
  const target = rows.find((r) => r.Team === team);
  if (!target) return undefined;
  const better =
    direction === "higher"
      ? rows.filter((r) => r.value > target.value).length
      : rows.filter((r) => r.value < target.value).length;
  return { rank: better + 1, value: target.value };
}

function splitYears(value: string | number | null | undefined): string {
  if (typeof value !== "string" || !value.trim()) return "—";
  return value;
}

// Parses a comma-joined years string (e.g. "2019, 2021, 2023") and returns
// the most recent one, or null if the field is empty/missing -- used to
// resolve each stat tile's "latest year they achieved X" deep-link target.
function latestYear(value: string | number | null | undefined): number | null {
  if (typeof value !== "string" || !value.trim()) return null;
  const years = value
    .split(",")
    .map((y) => Number(y.trim()))
    .filter((y) => Number.isFinite(y));
  return years.length ? Math.max(...years) : null;
}

export default function ProfilePage() {
  return (
    <Suspense fallback={<LoadingBasketballs label="Loading" />}>
      <ProfilePageInner />
    </Suspense>
  );
}

// useSearchParams() (for the ?team= deep link) requires a Suspense boundary
// around whatever calls it, per Next.js -- the actual page content lives
// here, wrapped by the plain default export above.
function ProfilePageInner() {
  const [meta, setMeta] = useState<LeagueMeta | null>(null);
  const [allTeams, setAllTeams] = useState<TeamSummary[]>([]);
  const [totals, setTotals] = useState<AggregateRow[]>([]);
  const [averages, setAverages] = useState<AggregateRow[]>([]);
  const [queryTotals, setQueryTotals] = useState<Record<string, QueryRow[]>>({});
  const [categoryHistory, setCategoryHistory] = useState<CategoryHistoryResponse | null>(null);
  const [team, setTeam] = useState<string | null>(null);

  const searchParams = useSearchParams();

  useEffect(() => {
    // A ?team= link (from a table row elsewhere in the app) wins over the
    // remembered last-selected team; falls back to that, then the first
    // member, exactly like before this existed.
    const teamFromUrl = searchParams.get("team");
    getLeagueMeta().then((m) => {
      setMeta(m);
      let restored = m.members[0] ?? null;
      if (teamFromUrl && m.members.includes(teamFromUrl)) {
        restored = teamFromUrl;
      } else {
        try {
          const saved = localStorage.getItem(SELECTED_TEAM_KEY);
          if (saved && m.members.includes(saved)) restored = saved;
        } catch {}
      }
      setTeam(restored);
    });
    getTeamSummary({}).then(setAllTeams);
    getTotals({}).then(setTotals);
    getAverages({}).then(setAverages);
    getCategoryHistory().then(setCategoryHistory);
    Promise.all(
      QUERY_TOTAL_FIELDS.map((f) =>
        getQuery({
          metric: f.metric,
          aggregation: "sum",
          group_by: ["Team"],
          seasons: f.seasons,
          limit: 50,
        }).then((res) => [f.label, res.rows] as const),
      ),
    ).then((entries) => setQueryTotals(Object.fromEntries(entries)));
    // Deliberately only reads searchParams once, at mount -- not a dep, so
    // a later manual team switch on this same page load isn't fought by
    // this effect re-running.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (team) localStorage.setItem(SELECTED_TEAM_KEY, team);
  }, [team]);

  const profile = allTeams.find((r) => r.Team === team);
  const totalsRow = totals.find((r) => r.team === team);
  const averagesRow = averages.find((r) => r.team === team);

  // Distinct from "badges is empty" -- profile/categoryHistory arrive from
  // separate, sometimes-slower fetches than the meta/team that gate the
  // page's own loading screen below, so without this the page used to
  // render past that guard and show a real "0 total badges" flash before
  // the actual count popped in a moment later.
  const badgesLoading = !profile || !categoryHistory;

  const badges = useMemo(() => {
    if (!team || !profile || !categoryHistory) return { positive: [], negative: [] };
    return buildBadges(team, profile, categoryHistory, meta?.goat);
  }, [team, profile, categoryHistory, meta?.goat]);

  const uniquePositiveCount = new Set(badges.positive.map((b) => b.type)).size;

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

    const queryFields = QUERY_TOTAL_FIELDS.map((f) => {
      const rows = queryTotals[f.label];
      const result = rows ? rankFromQueryRows(rows, team, f.direction) : undefined;
      return { field: f.label, rank: result?.rank, value: result?.value ?? null };
    });

    return [...summaryFields, ...statFields, ...queryFields]
      .filter((r): r is { field: string; rank: number; value: string | number | null } => r.rank !== undefined && r.rank <= 3)
      .sort((a, b) => a.rank - b.rank);
  }, [team, allTeams, totals, averages, queryTotals]);

  if (!meta || !team) return <LoadingBasketballs label="Loading" />;

  return (
    <div className="flex flex-col gap-4">
      <div className="sticky top-0 z-30 flex flex-wrap items-center gap-3 rounded-sm border border-border bg-card px-3 py-2 shadow-sm">
        <RoutedViewSwitcher options={VIEW_OPTIONS} current="profile" paths={VIEW_PATHS} />

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

        <div className="ml-auto">
          <SourceLastUpdated source="team_summary" />
        </div>
      </div>

      <Card>
        <CardHeader>
          {/* Grouped in one div so grid auto-placement can't split them into
              separate cells -- CardAction is `hidden` (removed from the box
              tree, not just visually hidden) below `sm`, and when it's gone
              the header's grid-cols-[1fr_auto] auto-placement algorithm was
              putting CardTitle in column 2 instead of stacking it under
              CardDescription in column 1. */}
          <div>
            <CardDescription>Career Profile</CardDescription>
            <CardTitle className="text-4xl sm:text-5xl">{team}</CardTitle>
            <p className="mt-1 hidden text-sm text-muted-foreground sm:block">
              {badgesLoading
                ? "Loading badges…"
                : `${badges.positive.length} total badges · ${uniquePositiveCount}/${POSITIVE_BADGE_TYPES.length} unique`}
            </p>
          </div>
          <CardAction className="hidden max-w-md sm:block">
            {badgesLoading ? (
              <span className="text-sm text-muted-foreground">Loading badges…</span>
            ) : (
              <TeamBadges positive={badges.positive} negative={badges.negative} />
            )}
          </CardAction>
        </CardHeader>
        <CardContent className="sm:hidden">
          {badgesLoading ? (
            <span className="text-sm text-muted-foreground">Loading badges…</span>
          ) : (
            <BadgeDrawer positive={badges.positive} negative={badges.negative} />
          )}
        </CardContent>
      </Card>

      {profile && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <StatTile
            label="Championships"
            value={profile.Championships ?? 0}
            sub={splitYears(profile["Championship Years"])}
            icon={Trophy}
            href={`/standings?year=${latestYear(profile["Championship Years"]) ?? meta.current_year}&tree=1`}
          />
          <StatTile
            label="MVPs"
            value={profile.MVPs ?? 0}
            sub={splitYears(profile["MVP Years"])}
            icon={Star}
            href={`/standings/ratings?year=${latestYear(profile["MVP Years"]) ?? meta.current_year}`}
          />
          <StatTile
            label="Best RS Rating"
            value={typeof profile["Best RS Rating"] === "number" ? profile["Best RS Rating"].toFixed(1) : "—"}
            sub={splitYears(profile["Best RS Rating Years"])}
            href={`/standings/ratings?year=${latestYear(profile["Best RS Rating Years"]) ?? meta.current_year}`}
          />
          <StatTile
            label="RS 1st Place"
            value={profile["RS 1st Place"] ?? 0}
            sub={splitYears(profile["RS 1st Years"])}
            icon={Podium}
            href={`/standings?year=${latestYear(profile["RS 1st Years"]) ?? meta.current_year}`}
          />
          <StatTile
            label="Best RS Finish"
            value={typeof profile["Best RS Finish"] === "number" ? ordinal(profile["Best RS Finish"]) : "—"}
            sub={splitYears(profile["Best RS Finish Years"])}
            href={`/standings?year=${latestYear(profile["Best RS Finish Years"]) ?? meta.current_year}`}
          />
          {playoffFinish && (
            <StatTile
              label="Best Playoff Finish"
              value={playoffFinish.label}
              sub={playoffFinish.years}
              valueClassName={playoffFinish.label === "Champion" ? "text-amber-400" : undefined}
              href={`/standings?year=${latestYear(playoffFinish.years) ?? meta.current_year}&tree=1`}
            />
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
                    <TableCell className={cn("text-right font-extrabold", rankColorClass(row.rank))}>
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

      <ProfileHistoryChart team={team} meta={meta} />
    </div>
  );
}

function StatTile({
  label,
  value,
  sub,
  icon: Icon,
  valueClassName,
  href,
}: {
  label: string;
  value: string | number;
  sub: string;
  // Rendered once per count when value is a number (e.g. 2 championships ->
  // 2 trophies), not just once as a static decoration.
  icon?: ComponentType<{ className?: string }>;
  valueClassName?: string;
  // When present, the whole tile links out to the resolved-year page for
  // this stat (Ratings page or playoff tree) -- see the per-tile hrefs
  // computed in ProfilePageInner for the exact per-stat resolution logic.
  href?: string;
}) {
  const iconCount = Icon && typeof value === "number" ? value : 0;
  const className = cn(
    "rounded-sm border border-border p-4",
    href && "transition-colors hover:border-primary",
  );
  const content = (
    <>
      <div className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase">
        {label}
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-1.5">
        <span
          className={cn(
            "font-mono text-3xl font-extrabold tracking-wide text-primary uppercase tabular-nums",
            valueClassName,
          )}
        >
          {value}
        </span>
        {Icon &&
          iconCount > 0 &&
          Array.from({ length: iconCount }, (_, i) => (
            <Icon key={i} className="size-4 text-amber-400" />
          ))}
      </div>
      <div className="mt-1 text-xs text-muted-foreground">{sub}</div>
    </>
  );
  if (href) {
    return (
      <Link href={href} className={className}>
        {content}
      </Link>
    );
  }
  return <div className={className}>{content}</div>;
}
