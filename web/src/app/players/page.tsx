"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
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
import { ArrowToggle } from "@/components/arrow-toggle";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { getDraftPicks, getLeagueMeta, MAIN_CATS, type Category, type DraftPick, type LeagueMeta } from "@/lib/api";
import { compareCell, comparisonClass } from "@/lib/highlight";
import { PLACEHOLDER_PLAYERS, toTotal, type PlaceholderPlayer } from "@/lib/placeholder-players";
import { cn } from "@/lib/utils";

type View = "draft" | "trade";
const VIEW_OPTIONS = [
  { value: "draft", label: "Draft Box" },
  { value: "trade", label: "Trade Box" },
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
      {view === "draft" ? <DraftBox meta={meta} /> : <TradeBox />}
    </div>
  );
}

type GroupBy = "none" | "team" | "player" | "year";
const PAGE_SIZE = 25;

function DraftBox({ meta }: { meta: LeagueMeta }) {
  const [years, setYears] = useState<number[]>(meta.years);
  const [teams, setTeams] = useState<string[]>(meta.members);
  const [groupBy, setGroupBy] = useState<GroupBy>("none");
  const [rows, setRows] = useState<DraftPick[]>([]);
  const [page, setPage] = useState(0);

  useEffect(() => {
    getDraftPicks({ years, teams }).then(setRows);
  }, [years, teams]);

  useEffect(() => {
    setPage(0);
  }, [years, teams, groupBy]);

  const groups = useMemo(() => {
    if (groupBy === "none") return [{ header: null as string | null, picks: rows }];
    const map = new Map<string, DraftPick[]>();
    for (const pick of rows) {
      const key = groupBy === "team" ? pick.Team : groupBy === "player" ? pick.Player : String(pick.Year);
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(pick);
    }
    const keys = [...map.keys()].sort((a, b) =>
      groupBy === "year" ? Number(b) - Number(a) : a.localeCompare(b),
    );
    return keys.map((key) => ({ header: key, picks: map.get(key)! }));
  }, [rows, groupBy]);

  type FlatItem = { type: "header"; label: string } | { type: "pick"; pick: DraftPick };
  const flat = useMemo(() => {
    const items: FlatItem[] = [];
    for (const g of groups) {
      if (g.header) items.push({ type: "header", label: g.header });
      for (const p of g.picks) items.push({ type: "pick", pick: p });
    }
    return items;
  }, [groups]);

  const pageCount = Math.max(1, Math.ceil(flat.length / PAGE_SIZE));
  const pageItems = flat.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div className="flex flex-col gap-4 sm:flex-row">
      <div className="flex flex-col gap-3 sm:w-64 sm:shrink-0">
        <ChecklistGroup label="Season" options={meta.years} selected={years} onChange={setYears} scrollable />
        <ChecklistGroup label="Team" options={meta.members} selected={teams} onChange={setTeams} scrollable />
      </div>

      <div className="flex flex-1 flex-col gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Draft Box</CardTitle>
            <CardDescription>Every draft pick across the selected seasons and teams, best draft score first</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center gap-3 text-[11px] font-bold tracking-wider uppercase">
            <span className="text-muted-foreground">Group by</span>
            {(["none", "team", "player", "year"] as GroupBy[]).map((g) => (
              <Button
                key={g}
                variant={groupBy === g ? "default" : "outline"}
                size="sm"
                onClick={() => setGroupBy(g)}
              >
                {g === "none" ? "None" : g[0].toUpperCase() + g.slice(1)}
              </Button>
            ))}
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
                      <TableHead>Player</TableHead>
                      <TableHead>Team</TableHead>
                      <TableHead className="text-right">Round</TableHead>
                      <TableHead className="text-right">Round Pick</TableHead>
                      <TableHead className="text-right">Overall Pick</TableHead>
                      <TableHead className="text-right">Draft Score</TableHead>
                      <TableHead className="text-right">Rank</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {pageItems.map((item, i) =>
                      item.type === "header" ? (
                        <TableRow key={`h-${item.label}-${i}`} className="bg-muted/40 hover:bg-muted/40">
                          <TableCell
                            colSpan={7}
                            className="font-sans text-[11px] font-bold tracking-wider text-muted-foreground uppercase"
                          >
                            {item.label}
                          </TableCell>
                        </TableRow>
                      ) : (
                        <TableRow key={`${item.pick.Year}-${item.pick.Overall}-${item.pick.Team}`}>
                          <TableCell className="font-sans font-semibold">{item.pick.Player}</TableCell>
                          <TableCell className="font-sans font-extrabold tracking-wide uppercase">
                            {item.pick.Team}
                          </TableCell>
                          <TableCell className="text-right">{item.pick.Round}</TableCell>
                          <TableCell className="text-right">{item.pick.Pick}</TableCell>
                          <TableCell className="text-right">{item.pick.Overall}</TableCell>
                          <TableCell className="text-right font-extrabold text-primary">
                            {item.pick.Score}
                          </TableCell>
                          <TableCell className="text-right text-muted-foreground">{item.pick.Rank}</TableCell>
                        </TableRow>
                      ),
                    )}
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

function TradeBox() {
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
          <CardTitle>Trade Box</CardTitle>
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
