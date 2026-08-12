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
import { buttonVariants } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { StatTable } from "@/components/stat-table";
import { ArrowToggle } from "@/components/arrow-toggle";
import { SourceLastUpdated } from "@/components/source-last-updated";
import { Podium, Star, Trophy, X } from "lucide-react";
import {
  getAverages,
  getCategoryHistory,
  getHeadToHead,
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
import {
  comparableFields,
  COMPARISON_EXCLUDED_FIELDS,
  directionFor,
  EMPHASIZED_FIELDS,
  formatValue,
  formatValueWithYears,
  ordinal,
  rankFor,
} from "@/lib/team-summary-fields";
import { cn } from "@/lib/utils";
import { ProfileHistoryChart } from "@/components/profile-history-chart";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { buildBadges, POSITIVE_BADGE_TYPES } from "@/lib/badges";
import { TeamBadges } from "@/components/team-badges";
import { BadgeDrawer } from "@/components/badge-drawer";
import { useMediaQuery } from "@/lib/use-media-query";
import { useElementHeight } from "@/lib/use-element-height";

type View = "profile" | "comparison";
const VIEW_OPTIONS = [
  { value: "profile", label: "Profile" },
  { value: "comparison", label: "Comparison" },
];

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

const SELECTED_TEAM_KEY = "profile-selected-team";
const SELECTED_TEAMS_KEY = "comparison-selected-teams";
const MOBILE_TEAM_CAP = 2;
const DESKTOP_TEAM_CAP = 4;

type BestWorst = "best" | "worst" | "neutral";

function highlightFor(field: string, rows: TeamSummary[]): Record<string, BestWorst> {
  const result: Record<string, BestWorst> = {};
  for (const row of rows) result[row.Team] = "neutral";

  const direction = directionFor(field);
  if (direction === "skip" || rows.length < 2) return result;

  const numeric = rows
    .map((row) => ({ team: row.Team, value: row[field] }))
    .filter((r): r is { team: string; value: number } => typeof r.value === "number");
  if (numeric.length < 2) return result;

  const values = numeric.map((r) => r.value);
  if (values.every((v) => v === values[0])) return result;

  const best = direction === "higher" ? Math.max(...values) : Math.min(...values);
  for (const { team, value } of numeric) {
    result[team] = value === best ? "best" : "worst";
  }
  return result;
}

const highlightClass: Record<BestWorst, string> = {
  best: "bg-win/15 text-win",
  worst: "bg-loss/15 text-loss",
  neutral: "",
};

// Aggregate head-to-head, summed across every *other* selected team (see
// the fetch effect below) -- winPct uses the app's standard 0.49 tie weight,
// same convention as every other W/L% field on this page.
interface H2HRow {
  team: string;
  wins: number;
  losses: number;
  ties: number;
  winPct: number;
}

function highlightH2H(rows: H2HRow[]): Record<string, BestWorst> {
  const result: Record<string, BestWorst> = {};
  for (const row of rows) result[row.team] = "neutral";
  if (rows.length < 2) return result;
  const pcts = rows.map((r) => r.winPct);
  if (pcts.every((p) => p === pcts[0])) return result;
  const best = Math.max(...pcts);
  for (const row of rows) result[row.team] = row.winPct === best ? "best" : "worst";
  return result;
}

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
  // Renamed from "Total Wins"/"Total Category Wins" so the same field name
  // (and the same underlying /query data) can also be surfaced as its own
  // row in the Comparison table's Winning section, not just used behind the
  // scenes for League Top 3 -- see the Comparison-page section below for
  // where these two get injected into selectedRows.
  { label: "Matchup Wins", metric: "MATCHUP_WINS", seasons: ["RS", "PO"], direction: "higher" },
  { label: "Total Losses", metric: "MATCHUP_LOSSES", seasons: ["RS", "PO"], direction: "lower" },
  { label: "Category Wins", metric: "CAT_WINS", seasons: ["RS", "PO"], direction: "higher" },
  { label: "Total Category Losses", metric: "CAT_LOSSES", seasons: ["RS", "PO"], direction: "lower" },
  { label: "Total Reg Season Wins", metric: "MATCHUP_WINS", seasons: ["RS"], direction: "higher" },
  { label: "Total Reg Season Losses", metric: "MATCHUP_LOSSES", seasons: ["RS"], direction: "lower" },
  // Renamed from "Total Playoff Wins" for the same reason as Matchup/
  // Category Wins above -- now also a Comparison-table row (Playoffs
  // section), not just a League Top 3 contributor.
  { label: "Playoff Wins", metric: "MATCHUP_WINS", seasons: ["PO"], direction: "higher" },
  { label: "Total Playoff Losses", metric: "MATCHUP_LOSSES", seasons: ["PO"], direction: "lower" },
];

// Comparison table's 4 subcategory sections. Every non-excluded
// team_summary column (see COMPARISON_EXCLUDED_FIELDS) should appear in
// exactly one of these -- "Regular Season" was the user's own anchor
// ("MVP, all ratings, RS standings placement"); the other 3 buckets follow
// the same logic (playoff-specific / general win-loss+streaks / draft).
// Fields with a companion year/season column (see PAIRED_YEARS_FIELD in
// team-summary-fields.ts) are listed once here -- their years render inline
// in parentheses on the same row (formatValueWithYears), not as a second
// row, so the standalone "X Years"/"X Season" column names never appear
// here.
const COMPARISON_GROUPS: { title: string; fields: string[] }[] = [
  {
    title: "Playoffs",
    fields: ["Championships", "Finals", "Playoffs", "Playoff Wins", "PO W/L", "PO W/L %", "PO Cats", "PO Cats %"],
  },
  {
    title: "Regular Season",
    fields: [
      "MVPs",
      "Worst Ratings",
      "RS 1st Place",
      "RS Last Place",
      "Best RS Rating",
      "Best RS Finish",
      "Avg Rating (out of 100)",
      "Avg Rank",
      "#1 Rating Weeks",
      "Lowest Rating Weeks",
      "Avg Opp Rating (out of 100)",
      "Opponent Rating Ratio",
    ],
  },
  {
    title: "Winning",
    fields: [
      "Matchup Wins",
      "Category Wins",
      "Career W/L",
      "Career W/L %",
      "Career Matchups",
      "RS W/L",
      "RS W/L %",
      "Career Cats",
      "Career Cats %",
      "Career Cat Games",
      "RS Cats",
      "RS Cats %",
      "Best Win Streak",
      "Worst Losing Streak",
      "Best Undefeated Streak",
      "Longest 1st Place Streak",
      "Longest Last Streak",
      "Longest #1 Rating Streak",
      "Longest Last Rating Streak",
    ],
  },
  {
    title: "Draft",
    fields: ["Career Draft Score", "Avg Draft Score", "Best Draft Score", "Worst Draft Score"],
  },
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
  const [view, setView] = useState<View>("profile");

  // Comparison view state -- ported from the retired /comparison page.
  const [selected, setSelected] = useState<string[]>([]);
  const [addOpen, setAddOpen] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const [h2h, setH2h] = useState<H2HRow[] | null>(null);

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

  // Hydrate synchronously (no async dependency) so `hydrated` flips true in
  // the same initial render pass, before the persist-effect below ever gets
  // a chance to write. Gating on an async fetch here would leave a window
  // where React's dev-mode double-effect-invocation re-reads localStorage
  // AFTER the persist-effect has already clobbered it with the default `[]`
  // -- the read and the "mark as hydrated" must be atomic and synchronous.
  useEffect(() => {
    try {
      const raw = localStorage.getItem(SELECTED_TEAMS_KEY);
      if (raw) setSelected(JSON.parse(raw) as string[]);
    } catch {}
    setHydrated(true);
  }, []);

  // Drop any persisted team names no longer present once the real team list
  // loads (data changed, or a stale localStorage value from an old session).
  useEffect(() => {
    if (allTeams.length === 0) return;
    setSelected((s) => s.filter((t) => allTeams.some((r) => r.Team === t)));
  }, [allTeams]);

  useEffect(() => {
    if (!hydrated) return;
    localStorage.setItem(SELECTED_TEAMS_KEY, JSON.stringify(selected));
  }, [hydrated, selected]);

  // Switching into Comparison seeds the list with whichever team Profile
  // currently has selected, if nothing's already picked -- keeps the arrow
  // toggle feeling continuous instead of dropping you on an empty table.
  function handleViewChange(next: string) {
    const nextView = next as View;
    if (nextView === "comparison" && team && selected.length === 0) {
      setSelected([team]);
    }
    setView(nextView);
  }

  const isMobile = useMediaQuery("(max-width: 639px)");
  // Measures the sticky top bar's real height so the Comparison table's own
  // header row can stick directly below it (see useElementHeight's comment
  // for why a hardcoded offset isn't reliable -- the bar's height changes
  // between the Profile/Comparison views and across viewport widths).
  const [stickyBarRef, stickyBarHeight] = useElementHeight<HTMLDivElement>();
  // Cap the *display* at MOBILE_TEAM_CAP on mobile / DESKTOP_TEAM_CAP on
  // desktop without mutating `selected` itself, so a wider-viewport
  // selection persisted from desktop still fits on mobile without
  // horizontal scroll rather than being silently discarded.
  const cap = isMobile ? MOBILE_TEAM_CAP : DESKTOP_TEAM_CAP;
  const visibleSelected = selected.slice(0, cap);
  const canAddMore = selected.length < cap;
  // "Matchup Wins"/"Category Wins" aren't team_summary.csv columns (they
  // come from the generic /query endpoint via QUERY_TOTAL_FIELDS, same
  // data League Top 3 already uses) -- appended here so the Winning
  // group's field list isn't filtered out by comparisonFields.includes(f).
  const comparisonFields = comparableFields(allTeams)
    .filter((f) => !COMPARISON_EXCLUDED_FIELDS.has(f))
    .concat(["Matchup Wins", "Category Wins", "Playoff Wins"]);
  const selectedRows = visibleSelected
    .map((t) => allTeams.find((r) => r.Team === t))
    .filter((r): r is TeamSummary => !!r)
    .map((r) => ({
      ...r,
      "Matchup Wins": queryTotals["Matchup Wins"]?.find((q) => q.Team === r.Team)?.value ?? null,
      "Category Wins": queryTotals["Category Wins"]?.find((q) => q.Team === r.Team)?.value ?? null,
      "Playoff Wins": queryTotals["Playoff Wins"]?.find((q) => q.Team === r.Team)?.value ?? null,
    }));
  const availableTeams = allTeams.filter((r) => !selected.includes(r.Team));
  // Equal-width columns (Stat column + one per selected team) on every
  // viewport -- computed as a percentage rather than a fixed Tailwind
  // fraction class since the team count varies (1-4 on desktop, 1-2 on
  // mobile).
  const colWidthPct = `${100 / (selectedRows.length + 1)}%`;

  const selectedTeamKey = selectedRows.map((r) => r.Team).join("|");

  // Aggregate H2H: summed matchup W-L-T against every *other* selected team
  // (pairwise -- N teams = N*(N-1)/2 calls to the existing single-pair
  // endpoint, same fan-out pattern as the rest of this app's multi-fetch
  // effects). A pair with no real matchup history throws on the backend --
  // caught and treated as 0-0-0 for that pair rather than failing the whole
  // aggregate.
  useEffect(() => {
    const teams = selectedRows.map((r) => r.Team);
    if (teams.length < 2) {
      setH2h(null);
      return;
    }
    // Clear immediately (not just on the < 2 early-return above) so adding/
    // removing a team shows the loading state right away instead of the
    // previous team set's now-stale H2H rows (with a "--" for whichever
    // team just changed) sitting on screen until the new fetch resolves.
    setH2h(null);
    let cancelled = false;
    const pairs: [string, string][] = [];
    for (let i = 0; i < teams.length; i++) {
      for (let j = i + 1; j < teams.length; j++) pairs.push([teams[i], teams[j]]);
    }
    Promise.all(pairs.map(([a, b]) => getHeadToHead({ team_a: a, team_b: b }).catch(() => null))).then(
      (results) => {
        if (cancelled) return;
        const totals = new Map(teams.map((t) => [t, { wins: 0, losses: 0, ties: 0 }]));
        results.forEach((res, idx) => {
          if (!res) return;
          const [a, b] = pairs[idx];
          const ta = totals.get(a)!;
          const tb = totals.get(b)!;
          ta.wins += res.record.wins;
          ta.losses += res.record.losses;
          ta.ties += res.record.ties;
          tb.wins += res.record.losses;
          tb.losses += res.record.wins;
          tb.ties += res.record.ties;
        });
        setH2h(
          teams.map((t) => {
            const { wins, losses, ties } = totals.get(t)!;
            const denom = wins + losses + ties;
            return { team: t, wins, losses, ties, winPct: denom > 0 ? (wins + 0.49 * ties) / denom : 0 };
          }),
        );
      },
    );
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTeamKey]);

  const profile = allTeams.find((r) => r.Team === team);
  const totalsRow = totals.find((r) => r.team === team);
  const averagesRow = averages.find((r) => r.team === team);

  // Distinct from "badges is empty" -- profile/categoryHistory arrive from
  // separate, sometimes-slower fetches than the meta/team that gate the
  // page's own loading screen (line ~410 below), so without this the page
  // used to render past that guard and show a real "0 total badges" flash
  // before the actual count popped in a moment later.
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
      <div
        ref={stickyBarRef}
        className="sticky top-0 z-30 flex flex-wrap items-center gap-3 rounded-sm border border-border bg-card px-3 py-2 shadow-sm"
      >
        <ArrowToggle options={VIEW_OPTIONS} value={view} onChange={handleViewChange} />

        {view === "profile" ? (
          <>
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
          </>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            {visibleSelected.map((t) => (
              <span
                key={t}
                className="flex items-center gap-1.5 rounded-sm bg-secondary px-3 py-1 text-xs font-bold tracking-wide text-secondary-foreground uppercase"
              >
                {t}
                <button
                  type="button"
                  onClick={() => setSelected((s) => s.filter((x) => x !== t))}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <X className="size-3.5" />
                </button>
              </span>
            ))}
            {canAddMore && (
              <Popover open={addOpen} onOpenChange={setAddOpen}>
                <PopoverTrigger className={buttonVariants({ variant: "outline", size: "sm" })}>
                  + Add team
                </PopoverTrigger>
                <PopoverContent className="w-56 p-0">
                  <Command>
                    <CommandInput placeholder="Search teams..." />
                    <CommandList>
                      <CommandEmpty>No teams found.</CommandEmpty>
                      <CommandGroup>
                        {availableTeams.map((row) => (
                          <CommandItem
                            key={row.Team}
                            onSelect={() => {
                              setSelected((s) => [...s, row.Team]);
                              setAddOpen(false);
                            }}
                          >
                            {row.Team}
                          </CommandItem>
                        ))}
                      </CommandGroup>
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>
            )}
          </div>
        )}

        <div className="ml-auto">
          <SourceLastUpdated source="team_summary" />
        </div>
      </div>

      {view === "comparison" ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Career Comparison</CardTitle>
              <CardDescription>
                Add teams to compare career profile stats side by side
              </CardDescription>
            </CardHeader>
          </Card>

          {selectedRows.length === 0 ? (
            <Card>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Add two or more teams to compare.
                </p>
              </CardContent>
            </Card>
          ) : (
            <>
              {selectedRows.length >= 2 && (
                <Card>
                  <CardHeader>
                    <CardTitle>Head-to-Head</CardTitle>
                    <CardDescription>
                      Summed matchup record against every other selected team
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    {h2h ? (
                      <Table className="table-fixed">
                        <TableHeader>
                          <TableRow>
                            <TableHead
                              style={{ width: colWidthPct, top: stickyBarHeight }}
                              className="sticky z-20 whitespace-normal bg-card sm:whitespace-nowrap"
                            >
                              Stat
                            </TableHead>
                            {selectedRows.map((row) => (
                              <TableHead
                                key={row.Team}
                                style={{ width: colWidthPct, top: stickyBarHeight }}
                                className="sticky z-20 whitespace-normal bg-card text-right text-primary sm:whitespace-nowrap"
                              >
                                {row.Team}
                              </TableHead>
                            ))}
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {(() => {
                            const highlight = highlightH2H(h2h);
                            return (
                              <>
                                <TableRow>
                                  <TableCell className="whitespace-normal font-sans font-medium text-muted-foreground sm:whitespace-nowrap">
                                    H2H Record
                                  </TableCell>
                                  {selectedRows.map((row) => {
                                    const stat = h2h.find((r) => r.team === row.Team);
                                    return (
                                      <TableCell
                                        key={row.Team}
                                        className={cn(
                                          "whitespace-normal text-right sm:whitespace-nowrap",
                                          highlightClass[highlight[row.Team]],
                                        )}
                                      >
                                        {stat ? `${stat.wins}-${stat.losses}-${stat.ties}` : "—"}
                                      </TableCell>
                                    );
                                  })}
                                </TableRow>
                                <TableRow>
                                  <TableCell className="whitespace-normal font-sans font-bold text-base text-muted-foreground sm:whitespace-nowrap">
                                    H2H Win%
                                  </TableCell>
                                  {selectedRows.map((row) => {
                                    const stat = h2h.find((r) => r.team === row.Team);
                                    return (
                                      <TableCell
                                        key={row.Team}
                                        className={cn(
                                          "whitespace-normal text-right font-bold text-base sm:whitespace-nowrap",
                                          highlightClass[highlight[row.Team]],
                                        )}
                                      >
                                        {stat ? (stat.winPct * 100).toFixed(1) : "—"}%
                                      </TableCell>
                                    );
                                  })}
                                </TableRow>
                              </>
                            );
                          })()}
                        </TableBody>
                      </Table>
                    ) : (
                      <LoadingBasketballs label="Loading" />
                    )}
                  </CardContent>
                </Card>
              )}

              {COMPARISON_GROUPS.map((group) => {
                const fields = group.fields.filter((f) => comparisonFields.includes(f));
                if (fields.length === 0) return null;
                return (
                  <Card key={group.title}>
                    <CardHeader>
                      <CardTitle>{group.title}</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <Table className="table-fixed">
                        <TableHeader>
                          <TableRow>
                            <TableHead
                              style={{ width: colWidthPct, top: stickyBarHeight }}
                              className="sticky z-20 whitespace-normal bg-card sm:whitespace-nowrap"
                            >
                              Stat
                            </TableHead>
                            {selectedRows.map((row) => (
                              <TableHead
                                key={row.Team}
                                style={{ width: colWidthPct, top: stickyBarHeight }}
                                className="sticky z-20 whitespace-normal bg-card text-right text-primary sm:whitespace-nowrap"
                              >
                                {row.Team}
                              </TableHead>
                            ))}
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {fields.map((field) => {
                            const highlight = highlightFor(field, selectedRows);
                            const emphasized = EMPHASIZED_FIELDS.has(field);
                            return (
                              <TableRow key={field}>
                                <TableCell
                                  className={cn(
                                    "whitespace-normal font-sans font-medium text-muted-foreground sm:whitespace-nowrap",
                                    emphasized && "font-bold text-base",
                                  )}
                                >
                                  {field}
                                </TableCell>
                                {selectedRows.map((row) => (
                                  <TableCell
                                    key={row.Team}
                                    className={cn(
                                      "whitespace-normal text-right sm:whitespace-nowrap",
                                      highlightClass[highlight[row.Team]],
                                      emphasized && "font-bold text-base",
                                    )}
                                  >
                                    {formatValueWithYears(row, field)}
                                  </TableCell>
                                ))}
                              </TableRow>
                            );
                          })}
                        </TableBody>
                      </Table>
                    </CardContent>
                  </Card>
                );
              })}
            </>
          )}
        </>
      ) : (
        <>
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
                href={`/standings?year=${latestYear(profile["MVP Years"]) ?? meta.current_year}&view=ratings`}
              />
              <StatTile
                label="Best RS Rating"
                value={typeof profile["Best RS Rating"] === "number" ? profile["Best RS Rating"].toFixed(1) : "—"}
                sub={splitYears(profile["Best RS Rating Years"])}
                href={`/standings?year=${latestYear(profile["Best RS Rating Years"]) ?? meta.current_year}&view=ratings`}
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
        </>
      )}
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
