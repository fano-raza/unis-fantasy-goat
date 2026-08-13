"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import {
  Card,
  CardAction,
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
import { SourceLastUpdated } from "@/components/source-last-updated";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { getPlayerStats, MAIN_CATS, type Category, type PlayerStat, type StatWindow } from "@/lib/api";
import { compareCell, type Comparison } from "@/lib/highlight";
import { cn } from "@/lib/utils";

const TRADE_TEAM_CAP = 5;

const WINDOW_OPTIONS: { value: StatWindow; label: string }[] = [
  { value: "season", label: "Season" },
  { value: "d7", label: "7d" },
  { value: "d14", label: "14d" },
  { value: "d30", label: "30d" },
  { value: "d90", label: "90d" },
];

// Builds the {window}_{cat}_{total|avg} (or {window}_{cat} for FG%/FT%,
// which have no total/avg split -- see export_player_stats.py) key into a
// PlayerStat row. Returns null when that player has no games in the
// selected window (real during the NBA off-season, not a bug -- see the
// plan doc).
function getPlayerCatValue(player: PlayerStat, statWindow: StatWindow, cat: Category, mode: "totals" | "averages"): number | null {
  const key = cat === "FG%" || cat === "FT%" ? `${statWindow}_${cat}` : `${statWindow}_${cat}_${mode === "totals" ? "total" : "avg"}`;
  const value = player[key];
  return typeof value === "number" ? value : null;
}

function getPctComponents(player: PlayerStat, statWindow: StatWindow, cat: "FG%" | "FT%"): { made: number; att: number } | null {
  const made = player[`${statWindow}_${cat}_made`];
  const att = player[`${statWindow}_${cat}_att`];
  return typeof made === "number" && typeof att === "number" ? { made, att } : null;
}

// Aggregates a group of up to 5 players for one stat category. Counting
// categories sum or average normally; FG%/FT% use the real weighted ratio
// (sum of makes / sum of attempts across the group) rather than a naive
// average of each player's individual percentage, which would misweight
// players with very different attempt volumes -- same reasoning as
// StatTable's Score column elsewhere in this app.
function aggregate(players: PlayerStat[], statWindow: StatWindow, mode: "totals" | "averages"): Record<Category, number | null> {
  const result = {} as Record<Category, number | null>;
  for (const cat of MAIN_CATS) {
    if (cat === "FG%" || cat === "FT%") {
      const components = players.map((p) => getPctComponents(p, statWindow, cat)).filter((c): c is { made: number; att: number } => c !== null);
      const totalAtt = components.reduce((a, c) => a + c.att, 0);
      result[cat] = totalAtt > 0 ? components.reduce((a, c) => a + c.made, 0) / totalAtt : null;
      continue;
    }
    const values = players.map((p) => getPlayerCatValue(p, statWindow, cat, mode)).filter((v): v is number => v !== null);
    if (values.length === 0) {
      result[cat] = null;
      continue;
    }
    const sum = values.reduce((a, b) => a + b, 0);
    result[cat] = mode === "totals" ? sum : sum / values.length;
  }
  return result;
}

function formatStat(cat: Category, value: number | null): string {
  if (value === null) return "—";
  if (cat === "FG%" || cat === "FT%") return value.toFixed(3);
  return value.toFixed(1);
}

// Direct (not inverted) coloring: the Net column is Team A's own value
// relative to Team B, so Team A being "better" should read green here.
// `highlight.ts`'s `comparisonClass` is deliberately inverted for
// StatTable's different use case (a row colored relative to a separate
// focus-team baseline, not the row's own comparison) -- reusing it here
// was backwards, per the user's report.
const netClass: Record<Comparison, string> = {
  better: "bg-win/15 text-win",
  worse: "bg-loss/15 text-loss",
  neutral: "",
};

// FGM/FGA and FTM/FTA -- informational volume rows (made/attempted for the
// group). Rendered directly after their matching percentage row (FG% / FT%),
// not grouped separately. They do get a Net value (the made/attempted diff,
// same "X/Y" shape as the value cells), just never colored red/green --
// a made/attempted pair isn't a single win/loss comparison the way a plain
// stat total is, so there's no "better" direction to highlight.
const MADE_ATTEMPTED_BY_CAT: Partial<Record<Category, { label: string }>> = {
  "FG%": { label: "FGM/FGA" },
  "FT%": { label: "FTM/FTA" },
};

interface MadeAttempted {
  made: number;
  att: number;
}

// Totals: real summed made/attempted across the group. Averages: each
// player's own per-game made/attempted, averaged across the group -- same
// "average of each player's own rate" convention the rest of this table's
// Averages mode already uses for the 7 counting categories (see aggregate()
// above), kept consistent rather than switching to a team-wide made/games
// rate just for these two rows.
function madeAttemptedValue(
  players: PlayerStat[],
  statWindow: StatWindow,
  cat: "FG%" | "FT%",
  mode: "totals" | "averages",
): MadeAttempted | null {
  if (mode === "totals") {
    let made = 0;
    let att = 0;
    let any = false;
    for (const p of players) {
      const m = p[`${statWindow}_${cat}_made`];
      const a = p[`${statWindow}_${cat}_att`];
      if (typeof m === "number" && typeof a === "number") {
        made += m;
        att += a;
        any = true;
      }
    }
    return any ? { made, att } : null;
  }

  const madeRates: number[] = [];
  const attRates: number[] = [];
  for (const p of players) {
    const m = p[`${statWindow}_${cat}_made`];
    const a = p[`${statWindow}_${cat}_att`];
    const gp = p[`${statWindow}_GP`];
    if (typeof m === "number" && typeof a === "number" && typeof gp === "number" && gp > 0) {
      madeRates.push(m / gp);
      attRates.push(a / gp);
    }
  }
  if (madeRates.length === 0) return null;
  return {
    made: madeRates.reduce((sum, v) => sum + v, 0) / madeRates.length,
    att: attRates.reduce((sum, v) => sum + v, 0) / attRates.length,
  };
}

function formatMadeAttempted(value: MadeAttempted | null, mode: "totals" | "averages"): string {
  if (!value) return "—";
  const fmt = (n: number) => (mode === "totals" ? String(n) : n.toFixed(1));
  return `${fmt(value.made)}/${fmt(value.att)}`;
}

function formatMadeAttemptedNet(a: MadeAttempted | null, b: MadeAttempted | null, mode: "totals" | "averages"): string {
  if (!a || !b) return "—";
  const fmt = (n: number) => {
    const s = mode === "totals" ? String(n) : n.toFixed(1);
    return n >= 0 ? `+${s}` : s;
  };
  return `${fmt(a.made - b.made)}/${fmt(a.att - b.att)}`;
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
  available: PlayerStat[];
}) {
  const [open, setOpen] = useState(false);
  const remaining = available.filter((p) => !selected.includes(p.Player));
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
                        key={p.PlayerId}
                        onSelect={() => {
                          onChange([...selected, p.Player]);
                          setOpen(false);
                        }}
                      >
                        {p.Player} <span className="ml-1 text-muted-foreground">({p.Team})</span>
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

export function TradeHub() {
  const [players, setPlayers] = useState<PlayerStat[]>([]);
  const [playersLoading, setPlayersLoading] = useState(true);
  const [teamA, setTeamA] = useState<string[]>([]);
  const [teamB, setTeamB] = useState<string[]>([]);
  // Defaults to "season" -- during the NBA off-season the rolling windows
  // have no data at all (verified against the real export), so a rolling
  // statWindow default would open on an empty table.
  const [statWindow, setWindow] = useState<StatWindow>("season");
  const [mode, setMode] = useState<"totals" | "averages">("averages");

  useEffect(() => {
    getPlayerStats()
      .then(setPlayers)
      .finally(() => setPlayersLoading(false));
  }, []);

  const playersA = players.filter((p) => teamA.includes(p.Player));
  const playersB = players.filter((p) => teamB.includes(p.Player));
  const aggA = aggregate(playersA, statWindow, mode);
  const aggB = aggregate(playersB, statWindow, mode);

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Trade Hub</CardTitle>
          <CardDescription>
            Real NBA player stats (ESPN) -- compare up to 5 players a side
          </CardDescription>
          <CardAction>
            <SourceLastUpdated source="player_stats" />
          </CardAction>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {playersLoading ? (
            <LoadingBasketballs label="Loading players" />
          ) : (
            <div className="flex flex-wrap gap-6">
              <PlayerPicker label="Team A (up to 5)" selected={teamA} onChange={setTeamA} available={players} />
              <PlayerPicker label="Team B (up to 5)" selected={teamB} onChange={setTeamB} available={players} />
            </div>
          )}
          <div className="flex flex-wrap items-center gap-6">
            <div className="flex items-center gap-2 text-[11px] font-bold tracking-wider uppercase">
              <span className="text-muted-foreground">Window</span>
              {WINDOW_OPTIONS.map((opt) => (
                <Button
                  key={opt.value}
                  variant={statWindow === opt.value ? "default" : "outline"}
                  size="sm"
                  onClick={() => setWindow(opt.value)}
                >
                  {opt.label}
                </Button>
              ))}
            </div>
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
                  <TableHead className="text-right">Team A Net</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {MAIN_CATS.flatMap((cat) => {
                  const a = aggA[cat];
                  const b = aggB[cat];
                  const diff = a !== null && b !== null ? a - b : null;
                  const comparison = a !== null && b !== null ? compareCell(a, b, cat) : "neutral";
                  const rows = [
                    <TableRow key={cat}>
                      <TableCell className="font-sans font-medium text-muted-foreground">{cat}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{formatStat(cat, a)}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{formatStat(cat, b)}</TableCell>
                      <TableCell
                        className={cn("text-right font-mono font-extrabold tabular-nums", netClass[comparison])}
                      >
                        {diff !== null && diff >= 0 ? "+" : ""}
                        {formatStat(cat, diff)}
                      </TableCell>
                    </TableRow>,
                  ];
                  // FGM/FGA directly after FG%, FTM/FTA directly after FT%
                  // -- not grouped separately at the end.
                  const madeAttRow = MADE_ATTEMPTED_BY_CAT[cat];
                  if (madeAttRow) {
                    const maCat = cat as "FG%" | "FT%";
                    const aVal = madeAttemptedValue(playersA, statWindow, maCat, mode);
                    const bVal = madeAttemptedValue(playersB, statWindow, maCat, mode);
                    rows.push(
                      <TableRow key={madeAttRow.label}>
                        <TableCell className="font-sans font-medium text-muted-foreground">
                          {madeAttRow.label}
                        </TableCell>
                        <TableCell className="text-right font-mono tabular-nums">
                          {formatMadeAttempted(aVal, mode)}
                        </TableCell>
                        <TableCell className="text-right font-mono tabular-nums">
                          {formatMadeAttempted(bVal, mode)}
                        </TableCell>
                        {/* No red/green here (unlike the other Net cells) -- a
                            made/attempted pair has no single "better"
                            direction to highlight. */}
                        <TableCell className="text-right font-mono font-extrabold tabular-nums">
                          {formatMadeAttemptedNet(aVal, bVal, mode)}
                        </TableCell>
                      </TableRow>,
                    );
                  }
                  return rows;
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
