"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, X } from "lucide-react";
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
import { Button, buttonVariants } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ChecklistGroup } from "@/components/filter-panel";
import { GenericFilterDrawer } from "@/components/generic-filter-drawer";
import { ArrowToggle } from "@/components/arrow-toggle";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { getDraftPicks, getLeagueMeta, MAIN_CATS, type Category, type DraftPick, type LeagueMeta } from "@/lib/api";
import { compareCell, comparisonClass } from "@/lib/highlight";
import { PLACEHOLDER_PLAYERS, toTotal, type PlaceholderPlayer } from "@/lib/placeholder-players";
import { cn } from "@/lib/utils";

type View = "draft" | "trade";
const VIEW_OPTIONS = [
  { value: "draft", label: "Draft Hub" },
  { value: "trade", label: "Trade Hub" },
];

export default function PlayersPage() {
  const [meta, setMeta] = useState<LeagueMeta | null>(null);
  const [view, setView] = useState<View>("draft");

  useEffect(() => {
    getLeagueMeta().then(setMeta);
  }, []);

  if (!meta) return <LoadingBasketballs label="Loading" />;

  return (
    <div className="flex flex-col gap-4">
      <div className="sticky top-0 z-30 flex items-center gap-3 rounded-sm border border-border bg-card px-3 py-2 shadow-sm">
        <ArrowToggle options={VIEW_OPTIONS} value={view} onChange={(v) => setView(v as View)} />
      </div>
      {view === "draft" ? <DraftHub meta={meta} /> : <TradeHub />}
    </div>
  );
}

// Unselecting every dimension IS "None" -- no separate None button/state
// (per the user's explicit ask). Player is mutually exclusive with Team/
// Year (not spec'd as combinable -- toggling one clears the other, see
// toggleGroupBy below) since a single player's identity already implies
// one row; combining it with Team/Year grouping has no defined column
// behavior in the spec this was built from.
interface DraftGroupBy {
  team: boolean;
  player: boolean;
  year: boolean;
}
const DEFAULT_GROUP_BY: DraftGroupBy = { team: false, player: false, year: false };

interface DraftFilters {
  years: number[];
  teams: string[];
}

interface DraftDisplayRow {
  key: string;
  year: number | null;
  player: string | null;
  team: string | null;
  round: number | null;
  roundPick: number | null;
  overallPick: number | null;
  draftScore: number;
  rank: number | null;
}

function parseRank(rank: string): number | null {
  const n = Number(rank);
  return Number.isFinite(n) ? n : null;
}

function average(values: number[]): number | null {
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
}

// Real aggregation, not visual grouping -- one row per group value, with
// each column's meaning redefined per the user's exact spec:
// - Ungrouped: every pick is its own row, real values throughout.
// - Player group: Player = the player; Team/Round Pick/Year = N/A; Round
//   and Overall Pick = averaged (a player drafted more than once can have a
//   meaningful "typically picked around here"); Draft Score = total/average
//   (toggle); Rank = average.
// - Team and/or Year group: Team = team if Team selected else N/A; Year =
//   year if Year selected else N/A; Player/Round/Round Pick/Overall Pick =
//   N/A (no single coherent value across many different picks); Draft
//   Score = total/average; Rank = average.
function aggregateDraftPicks(
  picks: DraftPick[],
  groupBy: DraftGroupBy,
  statMode: "totals" | "averages",
): DraftDisplayRow[] {
  const isGrouped = groupBy.team || groupBy.player || groupBy.year;

  if (!isGrouped) {
    return picks.map((p) => ({
      key: `${p.Year}-${p.Overall}-${p.Team}`,
      year: p.Year,
      player: p.Player,
      team: p.Team,
      round: p.Round,
      roundPick: p.Pick,
      overallPick: p.Overall,
      draftScore: p.Score,
      rank: parseRank(p.Rank),
    }));
  }

  const groups = new Map<string, DraftPick[]>();
  for (const p of picks) {
    const key = groupBy.player ? `player:${p.Player}` : `team:${groupBy.team ? p.Team : ""}|year:${groupBy.year ? p.Year : ""}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(p);
  }

  const rows: DraftDisplayRow[] = [];
  for (const [key, groupPicks] of groups) {
    const scores = groupPicks.map((p) => p.Score);
    const scoreSum = scores.reduce((a, b) => a + b, 0);
    const draftScore = statMode === "totals" ? scoreSum : scoreSum / scores.length;
    const rank = average(groupPicks.map((p) => parseRank(p.Rank)).filter((r): r is number => r !== null));

    if (groupBy.player) {
      rows.push({
        key,
        year: null,
        player: groupPicks[0].Player,
        team: null,
        round: average(groupPicks.map((p) => p.Round)),
        roundPick: null,
        overallPick: average(groupPicks.map((p) => p.Overall)),
        draftScore,
        rank,
      });
    } else {
      rows.push({
        key,
        year: groupBy.year ? groupPicks[0].Year : null,
        player: null,
        team: groupBy.team ? groupPicks[0].Team : null,
        round: null,
        roundPick: null,
        overallPick: null,
        draftScore,
        rank,
      });
    }
  }
  return rows;
}

function formatNum(value: number | null): string {
  if (value === null) return "—";
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

type SortKey = "year" | "player" | "team" | "round" | "roundPick" | "overallPick" | "draftScore" | "rank";
type SortDir = "desc" | "asc";
interface SortState {
  key: SortKey;
  dir: SortDir;
}

function DraftSortHead({
  sortKey,
  sort,
  onToggle,
  className,
  children,
}: {
  sortKey: SortKey;
  sort: SortState;
  onToggle: (key: SortKey) => void;
  className?: string;
  children: ReactNode;
}) {
  const active = sort.key === sortKey;
  return (
    <TableHead className={className}>
      <button
        type="button"
        onClick={() => onToggle(sortKey)}
        className={cn("inline-flex items-center gap-0.5 hover:text-foreground", active && "text-foreground")}
      >
        {children}
        {active && (sort.dir === "desc" ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" />)}
      </button>
    </TableHead>
  );
}

const PAGE_SIZE = 25;

function DraftHub({ meta }: { meta: LeagueMeta }) {
  const [filters, setFilters] = useState<DraftFilters>({ years: meta.years, teams: meta.members });
  const [groupBy, setGroupBy] = useState<DraftGroupBy>(DEFAULT_GROUP_BY);
  const [statMode, setStatMode] = useState<"totals" | "averages">("totals");
  const [picks, setPicks] = useState<DraftPick[]>([]);
  const [sort, setSort] = useState<SortState>({ key: "draftScore", dir: "desc" });
  const [page, setPage] = useState(0);

  useEffect(() => {
    getDraftPicks({ years: filters.years, teams: filters.teams }).then(setPicks);
  }, [filters]);

  useEffect(() => {
    setPage(0);
  }, [filters, groupBy, statMode]);

  const isGrouped = groupBy.team || groupBy.player || groupBy.year;

  function toggleGroupBy(dim: keyof DraftGroupBy) {
    setGroupBy((g) => {
      if (dim === "player") return g.player ? DEFAULT_GROUP_BY : { team: false, player: true, year: false };
      return { ...g, player: false, [dim]: !g[dim] };
    });
  }

  function toggleSort(key: SortKey) {
    setSort((prev) => (prev.key === key ? { key, dir: prev.dir === "desc" ? "asc" : "desc" } : { key, dir: "desc" }));
  }

  const rows = useMemo(() => aggregateDraftPicks(picks, groupBy, statMode), [picks, groupBy, statMode]);

  const sortedRows = useMemo(() => {
    const { key, dir } = sort;
    function value(row: DraftDisplayRow): number | string | null {
      if (key === "player") return row.player;
      if (key === "team") return row.team;
      return row[key];
    }
    return [...rows].sort((a, b) => {
      const av = value(a);
      const bv = value(b);
      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;
      if (typeof av === "string" || typeof bv === "string") {
        const cmp = String(av).localeCompare(String(bv));
        return dir === "asc" ? cmp : -cmp;
      }
      return dir === "asc" ? av - bv : bv - av;
    });
  }, [rows, sort]);

  const pageCount = Math.max(1, Math.ceil(sortedRows.length / PAGE_SIZE));
  const pageRows = sortedRows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div className="flex flex-col gap-4 sm:flex-row">
      <div className="hidden sm:flex sm:w-64 sm:shrink-0 sm:flex-col sm:gap-3">
        <ChecklistGroup
          label="Season"
          options={meta.years}
          selected={filters.years}
          onChange={(years) => setFilters((f) => ({ ...f, years }))}
          scrollable
        />
        <ChecklistGroup
          label="Team"
          options={meta.members}
          selected={filters.teams}
          onChange={(teams) => setFilters((f) => ({ ...f, teams }))}
          scrollable
        />
      </div>

      <div className="flex flex-1 flex-col gap-4">
        <div className="sm:hidden">
          <GenericFilterDrawer
            value={filters}
            onChange={setFilters}
            renderContent={(draft, setDraft) => (
              <div className="flex flex-col gap-3">
                <ChecklistGroup
                  label="Season"
                  options={meta.years}
                  selected={draft.years}
                  onChange={(years) => setDraft({ ...draft, years })}
                  scrollable
                />
                <ChecklistGroup
                  label="Team"
                  options={meta.members}
                  selected={draft.teams}
                  onChange={(teams) => setDraft({ ...draft, teams })}
                  scrollable
                />
              </div>
            )}
          />
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Draft Hub</CardTitle>
            <CardDescription>
              Every draft pick across the selected seasons and teams -- group by to aggregate, click any column to sort
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center gap-6">
            <div className="flex items-center gap-2 text-[11px] font-bold tracking-wider uppercase">
              <span className="text-muted-foreground">Group by</span>
              {(["team", "player", "year"] as const).map((dim) => (
                <Button
                  key={dim}
                  variant={groupBy[dim] ? "default" : "outline"}
                  size="sm"
                  onClick={() => toggleGroupBy(dim)}
                >
                  {dim[0].toUpperCase() + dim.slice(1)}
                </Button>
              ))}
            </div>
            <label
              className={cn(
                "flex items-center gap-2 text-[11px] font-bold tracking-wider uppercase",
                !isGrouped && "opacity-50",
              )}
            >
              <span className="text-muted-foreground">Total</span>
              <Switch
                disabled={!isGrouped}
                checked={statMode === "averages"}
                onCheckedChange={(checked) => setStatMode(checked ? "averages" : "totals")}
              />
              <span className="text-muted-foreground">Average</span>
            </label>
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            {rows.length === 0 ? (
              <p className="text-sm text-muted-foreground">No picks for the current filters.</p>
            ) : (
              <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <DraftSortHead sortKey="year" sort={sort} onToggle={toggleSort}>
                        Year
                      </DraftSortHead>
                      <DraftSortHead sortKey="player" sort={sort} onToggle={toggleSort}>
                        Player
                      </DraftSortHead>
                      <DraftSortHead sortKey="team" sort={sort} onToggle={toggleSort}>
                        Team
                      </DraftSortHead>
                      <DraftSortHead sortKey="round" sort={sort} onToggle={toggleSort} className="text-right">
                        Round
                      </DraftSortHead>
                      <DraftSortHead sortKey="roundPick" sort={sort} onToggle={toggleSort} className="text-right">
                        Round Pick
                      </DraftSortHead>
                      <DraftSortHead sortKey="overallPick" sort={sort} onToggle={toggleSort} className="text-right">
                        Overall Pick
                      </DraftSortHead>
                      <DraftSortHead sortKey="draftScore" sort={sort} onToggle={toggleSort} className="text-right">
                        Draft Score
                      </DraftSortHead>
                      <DraftSortHead sortKey="rank" sort={sort} onToggle={toggleSort} className="text-right">
                        Rank
                      </DraftSortHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {pageRows.map((row) => (
                      <TableRow key={row.key}>
                        <TableCell className="text-muted-foreground">{row.year ?? "—"}</TableCell>
                        <TableCell className="font-sans font-semibold">{row.player ?? "—"}</TableCell>
                        <TableCell className="font-sans font-extrabold tracking-wide uppercase">
                          {row.team ?? "—"}
                        </TableCell>
                        <TableCell className="text-right">{formatNum(row.round)}</TableCell>
                        <TableCell className="text-right">{formatNum(row.roundPick)}</TableCell>
                        <TableCell className="text-right">{formatNum(row.overallPick)}</TableCell>
                        <TableCell className="text-right font-extrabold text-primary">
                          {formatNum(row.draftScore)}
                        </TableCell>
                        <TableCell className="text-right text-muted-foreground">{formatNum(row.rank)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>

                <div className="mt-4 flex items-center justify-center gap-3">
                  <Button
                    variant="outline"
                    size="icon-sm"
                    disabled={page === 0}
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    aria-label="Previous page"
                  >
                    <ChevronLeft className="size-4" />
                  </Button>
                  <span className="text-xs text-muted-foreground">
                    Page {page + 1} of {pageCount}
                  </span>
                  <Button
                    variant="outline"
                    size="icon-sm"
                    disabled={page >= pageCount - 1}
                    onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
                    aria-label="Next page"
                  >
                    <ChevronRight className="size-4" />
                  </Button>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

const TRADE_TEAM_CAP = 5;

function aggregate(
  players: PlaceholderPlayer[],
  mode: "totals" | "averages",
  dataset: "past" | "predicted",
): Record<Category, number> {
  const result = {} as Record<Category, number>;
  for (const cat of MAIN_CATS) {
    const values = players.map((p) => {
      const avg = dataset === "past" ? p.pastAvg : p.predictedAvg;
      const games = dataset === "past" ? p.pastGames : p.predictedGames;
      return mode === "totals" ? (toTotal(avg, games)[cat] ?? 0) : (avg[cat] ?? 0);
    });
    const sum = values.reduce((a, b) => a + b, 0);
    result[cat] = mode === "totals" || values.length === 0 ? sum : sum / values.length;
  }
  return result;
}

function formatStat(cat: Category, value: number): string {
  if (cat === "FG%" || cat === "FT%") return value.toFixed(3);
  return value.toFixed(1);
}

function PlayerPicker({
  label,
  selected,
  onChange,
  available,
}: {
  label: string;
  selected: string[];
  onChange: (next: string[]) => void;
  available: PlaceholderPlayer[];
}) {
  const [open, setOpen] = useState(false);
  const remaining = available.filter((p) => !selected.includes(p.name));
  return (
    <div className="flex flex-1 flex-col gap-2">
      <span className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase">{label}</span>
      <div className="flex flex-wrap items-center gap-2">
        {selected.map((name) => (
          <span
            key={name}
            className="flex items-center gap-1.5 rounded-sm bg-secondary px-3 py-1 text-xs font-bold tracking-wide text-secondary-foreground"
          >
            {name}
            <button
              type="button"
              onClick={() => onChange(selected.filter((n) => n !== name))}
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="size-3.5" />
            </button>
          </span>
        ))}
        {selected.length < TRADE_TEAM_CAP && (
          <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger className={buttonVariants({ variant: "outline", size: "sm" })}>
              + Add player
            </PopoverTrigger>
            <PopoverContent className="w-56 p-0">
              <Command>
                <CommandInput placeholder="Search players..." />
                <CommandList>
                  <CommandEmpty>No players found.</CommandEmpty>
                  <CommandGroup>
                    {remaining.map((p) => (
                      <CommandItem
                        key={p.name}
                        onSelect={() => {
                          onChange([...selected, p.name]);
                          setOpen(false);
                        }}
                      >
                        {p.name}
                      </CommandItem>
                    ))}
                  </CommandGroup>
                </CommandList>
              </Command>
            </PopoverContent>
          </Popover>
        )}
      </div>
    </div>
  );
}

function TradeHub() {
  const [teamA, setTeamA] = useState<string[]>([]);
  const [teamB, setTeamB] = useState<string[]>([]);
  const [dataset, setDataset] = useState<"past" | "predicted">("past");
  const [mode, setMode] = useState<"totals" | "averages">("averages");

  const playersA = PLACEHOLDER_PLAYERS.filter((p) => teamA.includes(p.name));
  const playersB = PLACEHOLDER_PLAYERS.filter((p) => teamB.includes(p.name));
  const aggA = aggregate(playersA, mode, dataset);
  const aggB = aggregate(playersB, mode, dataset);

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Trade Hub</CardTitle>
          <CardDescription>
            Placeholder data -- this repo has no real player-stats source yet. Shape only, not real numbers.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-6">
            <PlayerPicker label="Team A (up to 5)" selected={teamA} onChange={setTeamA} available={PLACEHOLDER_PLAYERS} />
            <PlayerPicker label="Team B (up to 5)" selected={teamB} onChange={setTeamB} available={PLACEHOLDER_PLAYERS} />
          </div>
          <div className="flex flex-wrap items-center gap-6">
            <label className="flex items-center gap-2 text-[11px] font-bold tracking-wider uppercase">
              <span className="text-muted-foreground">Past</span>
              <Switch checked={dataset === "predicted"} onCheckedChange={(c) => setDataset(c ? "predicted" : "past")} />
              <span className="text-muted-foreground">Predicted</span>
            </label>
            <label className="flex items-center gap-2 text-[11px] font-bold tracking-wider uppercase">
              <span className="text-muted-foreground">Totals</span>
              <Switch checked={mode === "averages"} onCheckedChange={(c) => setMode(c ? "averages" : "totals")} />
              <span className="text-muted-foreground">Averages</span>
            </label>
          </div>
        </CardContent>
      </Card>

      {(playersA.length > 0 || playersB.length > 0) && (
        <Card>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Category</TableHead>
                  <TableHead className="text-right">Team A</TableHead>
                  <TableHead className="text-right">Team B</TableHead>
                  <TableHead className="text-right">Difference (A &minus; B)</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {MAIN_CATS.map((cat) => {
                  const a = aggA[cat];
                  const b = aggB[cat];
                  const diff = a - b;
                  const comparison = compareCell(a, b, cat);
                  return (
                    <TableRow key={cat}>
                      <TableCell className="font-sans font-medium text-muted-foreground">{cat}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{formatStat(cat, a)}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{formatStat(cat, b)}</TableCell>
                      <TableCell
                        className={cn("text-right font-mono font-extrabold tabular-nums", comparisonClass[comparison])}
                      >
                        {diff >= 0 ? "+" : ""}
                        {formatStat(cat, diff)}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
