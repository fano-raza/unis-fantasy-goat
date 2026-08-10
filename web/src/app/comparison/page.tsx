"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { X } from "lucide-react";
import { getTeamSummary, type TeamSummary } from "@/lib/api";
import {
  comparableFields,
  COMPARISON_EXCLUDED_FIELDS,
  DEEMPHASIZED_FIELDS,
  directionFor,
  EMPHASIZED_FIELDS,
  formatValue,
} from "@/lib/team-summary-fields";
import { cn } from "@/lib/utils";
import { useMediaQuery } from "@/lib/use-media-query";

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

export default function ComparisonPage() {
  const [allTeams, setAllTeams] = useState<TeamSummary[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const [hydrated, setHydrated] = useState(false);

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

  useEffect(() => {
    getTeamSummary({}).then(setAllTeams);
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

  const isMobile = useMediaQuery("(max-width: 639px)");
  // Cap the *display* at MOBILE_TEAM_CAP on mobile / DESKTOP_TEAM_CAP on
  // desktop without mutating `selected` itself, so a wider-viewport
  // selection persisted from desktop still fits on mobile without
  // horizontal scroll rather than being silently discarded.
  const cap = isMobile ? MOBILE_TEAM_CAP : DESKTOP_TEAM_CAP;
  const visibleSelected = selected.slice(0, cap);
  const canAddMore = selected.length < cap;

  const fields = comparableFields(allTeams).filter((f) => !COMPARISON_EXCLUDED_FIELDS.has(f));
  const selectedRows = visibleSelected
    .map((t) => allTeams.find((r) => r.Team === t))
    .filter((r): r is TeamSummary => !!r);
  const available = allTeams.filter((r) => !selected.includes(r.Team));
  // Equal-width columns (Stat column + one per selected team) on every
  // viewport -- computed as a percentage rather than a fixed Tailwind
  // fraction class since the team count varies (1-4 on desktop, 1-2 on
  // mobile).
  const colWidthPct = `${100 / (selectedRows.length + 1)}%`;

  return (
    <div className="flex flex-col gap-4">
      <div className="sticky top-0 z-30 flex flex-wrap items-center gap-2 rounded-sm border border-border bg-card px-3 py-2 shadow-sm">
        {visibleSelected.map((team) => (
          <span
            key={team}
            className="flex items-center gap-1.5 rounded-sm bg-secondary px-3 py-1 text-xs font-bold tracking-wide text-secondary-foreground uppercase"
          >
            {team}
            <button
              type="button"
              onClick={() => setSelected((s) => s.filter((t) => t !== team))}
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="size-3.5" />
            </button>
          </span>
        ))}
        {canAddMore && (
          <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger
              className={buttonVariants({ variant: "outline", size: "sm" })}
            >
              + Add team
            </PopoverTrigger>
            <PopoverContent className="w-56 p-0">
              <Command>
                <CommandInput placeholder="Search teams..." />
                <CommandList>
                  <CommandEmpty>No teams found.</CommandEmpty>
                  <CommandGroup>
                    {available.map((row) => (
                      <CommandItem
                        key={row.Team}
                        onSelect={() => {
                          setSelected((s) => [...s, row.Team]);
                          setOpen(false);
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

      <Card>
        <CardHeader>
          <CardTitle>Career Comparison</CardTitle>
          <CardDescription>
            Add teams to compare career profile stats side by side
          </CardDescription>
        </CardHeader>
      </Card>

      <Card>
        <CardContent>
          {selectedRows.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Add two or more teams to compare.
            </p>
          ) : (
            <Table className="table-fixed">
              <TableHeader>
                <TableRow>
                  <TableHead
                    style={{ width: colWidthPct }}
                    className="whitespace-normal sm:whitespace-nowrap"
                  >
                    Stat
                  </TableHead>
                  {selectedRows.map((row) => (
                    <TableHead
                      key={row.Team}
                      style={{ width: colWidthPct }}
                      className="whitespace-normal text-right text-primary sm:whitespace-nowrap"
                    >
                      <Link href={`/profile?team=${encodeURIComponent(row.Team)}`} className="hover:underline">
                        {row.Team}
                      </Link>
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {fields.map((field) => {
                  const highlight = highlightFor(field, selectedRows);
                  const emphasized = EMPHASIZED_FIELDS.has(field);
                  const deemphasized = DEEMPHASIZED_FIELDS.has(field);
                  return (
                    <TableRow key={field}>
                      <TableCell
                        className={cn(
                          "whitespace-normal font-sans font-medium text-muted-foreground sm:whitespace-nowrap",
                          emphasized && "font-bold text-base",
                          deemphasized && "text-muted-foreground/60",
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
                            deemphasized && "text-muted-foreground/60",
                          )}
                        >
                          {formatValue(row[field])}
                        </TableCell>
                      ))}
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
