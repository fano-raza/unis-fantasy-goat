"use client";

import { useEffect, useRef, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import { SourceLastUpdated } from "@/components/source-last-updated";
import { RoutedViewSwitcher } from "@/components/routed-view-switcher";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { X } from "lucide-react";
import {
  getHeadToHead,
  getLeagueMeta,
  getQuery,
  getTeamSummary,
  type LeagueMeta,
  type QueryRow,
  type TeamSummary,
} from "@/lib/api";
import {
  comparableFields,
  COMPARISON_EXCLUDED_FIELDS,
  directionFor,
  EMPHASIZED_FIELDS,
  formatValueWithYears,
} from "@/lib/team-summary-fields";
import { cn } from "@/lib/utils";
import { useMediaQuery } from "@/lib/use-media-query";
import { useElementHeight } from "@/lib/use-element-height";
import { useSelectedTeam } from "@/lib/use-selected-team";

const VIEW_OPTIONS = [
  { value: "profile", label: "Profile" },
  { value: "comparison", label: "Comparison" },
  { value: "roster", label: "Roster" },
];
const VIEW_PATHS = { profile: "/team/profile", comparison: "/team/comparison", roster: "/team/roster" };

const SELECTED_TEAMS_KEY = "comparison-selected-teams";
const MOBILE_TEAM_CAP = 2;
const DESKTOP_TEAM_CAP = 4;

type BestWorst = "best" | "worst" | "neutral";

// Aggregate head-to-head, summed across every *other* selected team -- winPct
// uses the app's standard 0.49 tie weight, same convention as every other
// W/L% field on the Profile/Comparison pages.
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

// The 3 /query-backed fields the Comparison table actually renders (Winning
// and Playoffs sections) -- a trimmed copy of Profile's own
// QUERY_TOTAL_FIELDS (which also fetches Losses/Reg-Season-only splits for
// League Top 3 ranking, not needed here).
interface QueryTotalField {
  label: string;
  metric: string;
  seasons?: string[];
}

const QUERY_TOTAL_FIELDS: QueryTotalField[] = [
  { label: "Matchup Wins", metric: "MATCHUP_WINS", seasons: ["RS", "PO"] },
  { label: "Category Wins", metric: "CAT_WINS", seasons: ["RS", "PO"] },
  { label: "Playoff Wins", metric: "MATCHUP_WINS", seasons: ["PO"] },
];

export default function ComparisonPage() {
  const [meta, setMeta] = useState<LeagueMeta | null>(null);
  const [allTeams, setAllTeams] = useState<TeamSummary[]>([]);
  const [queryTotals, setQueryTotals] = useState<Record<string, QueryRow[]>>({});
  const [team, setTeam] = useSelectedTeam("");

  const [selected, setSelected] = useState<string[]>([]);
  const [addOpen, setAddOpen] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const [h2h, setH2h] = useState<H2HRow[] | null>(null);

  useEffect(() => {
    getLeagueMeta().then(setMeta);
    getTeamSummary({}).then(setAllTeams);
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
  }, []);

  // Falls back to the league's first member if this is the very first-ever
  // visit to the app (no shared team ever selected yet, so useSelectedTeam's
  // own fallback of "" is still sitting there once meta loads).
  useEffect(() => {
    if (meta && !team) setTeam(meta.members[0] ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta]);

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

  // Seeds the list with whichever team is currently shared/synced across the
  // app, once, the first time this page has both hydrated its own
  // `selected` AND resolved a real `team` -- keeps a fresh visit to this
  // page from opening on an empty table. Only fires once (via the ref),
  // so manually clearing every team back to zero afterward stays empty.
  const seededRef = useRef(false);
  useEffect(() => {
    if (!hydrated || !team || seededRef.current) return;
    seededRef.current = true;
    if (selected.length === 0) setSelected([team]);
  }, [hydrated, team, selected]);

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

  const isMobile = useMediaQuery("(max-width: 639px)");
  // Measures the sticky top bar's real height so the Comparison table's own
  // header row can stick directly below it (see useElementHeight's comment
  // for why a hardcoded offset isn't reliable -- the bar's height changes
  // across viewport widths).
  const [stickyBarRef, stickyBarHeight] = useElementHeight<HTMLDivElement>();
  // Cap the *display* at MOBILE_TEAM_CAP on mobile / DESKTOP_TEAM_CAP on
  // desktop without mutating `selected` itself, so a wider-viewport
  // selection persisted from desktop still fits on mobile without
  // horizontal scroll rather than being silently discarded.
  const cap = isMobile ? MOBILE_TEAM_CAP : DESKTOP_TEAM_CAP;
  const visibleSelected = selected.slice(0, cap);
  const canAddMore = selected.length < cap;
  // "Matchup Wins"/"Category Wins" aren't team_summary.csv columns (they
  // come from the generic /query endpoint, same data Profile's League Top 3
  // uses) -- appended here so the Winning group's field list isn't filtered
  // out by comparisonFields.includes(f).
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

  if (!meta) return <LoadingBasketballs label="Loading" />;

  return (
    <div className="flex flex-col gap-4">
      <div
        ref={stickyBarRef}
        className="sticky top-0 z-30 flex flex-wrap items-center gap-3 rounded-sm border border-border bg-card px-3 py-2 shadow-sm"
      >
        <RoutedViewSwitcher options={VIEW_OPTIONS} current="comparison" paths={VIEW_PATHS} />

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

        <div className="ml-auto">
          <SourceLastUpdated source="team_summary" />
        </div>
      </div>

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
    </div>
  );
}
