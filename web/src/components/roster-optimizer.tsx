"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import { ArrowLeft, ArrowLeftRight, ArrowRight, Crown, Minus, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SteppableSelect } from "@/components/steppable-select";
import { cn } from "@/lib/utils";
import { HeadlineOdds, type SeasonFormat } from "@/components/headline-odds";
import { ordinal } from "@/lib/team-summary-fields";
import { usePremium } from "@/components/premium";
import {
  ApiError,
  runRosterOptimizer,
  type OptimizerCategory,
  type RosterOptimizerResult,
  type RosterRankRow,
} from "@/lib/api";

// The optimizer itself answers in well under a second; holding the loading
// veil up this long lets a couple of OPTIMIZER_PHRASES actually be read.
const MIN_RUN_MS = 3000;
export const OPTIMIZER_PHRASE_MS = 1500;

const pct = (x: number) => `${Math.round(x * 100)}%`;
const pts = (x: number) => `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(Math.round(x * 100))}`;

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    let detail = "";
    try {
      detail = JSON.parse(err.message).detail ?? "";
    } catch {}
    if (err.status === 503) return detail || "The optimizer isn't available right now.";
    if (err.status === 404) return detail || "No current roster found for this team.";
    if (err.status === 422) return detail || "Check the teams you picked and try again.";
  }
  return "Couldn't reach the server. Try again in a moment.";
}

/**
 * "Optimize" button for the Roster page (current season only) -- a premium
 * feature: visible to everyone, but clicking it while premium is locked
 * opens the premium login first (components/premium.tsx), then continues
 * straight into this dialog. Two screens: how many players to swap out,
 * then which opponents to optimize against (all by default -- unchecked
 * ones are left out of the opponent average). Then it closes and runs the
 * backtested Roster Optimizer for `team` -- the page shows the loading
 * veil while `onRunningChange(true)` and the comparison once `onResult`
 * fires. See _planning/roster-optimizer.md.
 */
export function RosterOptimizerButton({
  team,
  rosterSize,
  opponents,
  disabled,
  onRunningChange,
  onResult,
}: {
  team: string;
  rosterSize: number;
  // The season's other fantasy teams, in display order.
  opponents: string[];
  disabled?: boolean;
  onRunningChange: (running: boolean) => void;
  onResult: (result: RosterOptimizerResult) => void;
}) {
  const premium = usePremium();
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<"swaps" | "opponents">("swaps");
  const [maxSwaps, setMaxSwaps] = useState(3);
  const [error, setError] = useState<string | null>(null);
  // Unchecked opponents, remembered while the page stays on this team so a
  // re-run keeps the same picks; switching teams starts from "all" again.
  const [excluded, setExcluded] = useState<{ team: string; teams: ReadonlySet<string> }>({ team, teams: new Set() });
  const excludedTeams = excluded.team === team ? excluded.teams : new Set<string>();
  const selectedCount = opponents.filter((t) => !excludedTeams.has(t)).length;

  function setExcludedTeams(teams: ReadonlySet<string>) {
    setExcluded({ team, teams });
  }
  function toggleOpponent(t: string, checked: boolean) {
    const next = new Set(excludedTeams);
    if (checked) next.delete(t);
    else next.add(t);
    setExcludedTeams(next);
  }

  function openDialog() {
    premium.requireUnlock(() => {
      setMaxSwaps((n) => Math.max(1, Math.min(n, rosterSize)));
      setError(null);
      setStep("swaps");
      setOpen(true);
    });
  }

  function submitSwaps(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setStep("opponents");
  }

  async function submitOpponents(e: FormEvent) {
    e.preventDefault();
    if (!premium.password || selectedCount === 0) return;
    setOpen(false);
    onRunningChange(true);
    try {
      const [result] = await Promise.all([
        runRosterOptimizer({
          team,
          password: premium.password,
          max_swaps: maxSwaps,
          ignore_opponents: opponents.filter((t) => excludedTeams.has(t)),
        }),
        new Promise((resolve) => setTimeout(resolve, MIN_RUN_MS)),
      ]);
      onResult(result);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        // Password changed on the server since this session unlocked.
        premium.lock();
        premium.requireUnlock(() => setOpen(true));
      } else {
        setError(errorMessage(err));
        setOpen(true);
      }
    } finally {
      onRunningChange(false);
    }
  }

  const swapOptions = Array.from({ length: rosterSize }, (_, i) => i + 1);

  return (
    <>
      <Button type="button" size="sm" onClick={openDialog} disabled={disabled || !team || rosterSize === 0}>
        <ArrowLeftRight className="size-4" />
        Optimize
        <Crown className={cn("size-3.5 text-gold", premium.unlocked && "fill-current")} aria-label="Premium" />
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="font-display text-2xl font-bold [font-variation-settings:'opsz'_36]">
              Optimize {team}&apos;s roster
            </DialogTitle>
            <DialogDescription>
              Finds the free-agent pickups that most raise this team&apos;s probability of winning its weekly matchups,
              based on projected production for the rest of the season.
            </DialogDescription>
          </DialogHeader>
          {step === "swaps" ? (
            <form onSubmit={submitSwaps} className="flex flex-col gap-4">
              <p className="text-sm font-medium">How many players are you willing to swap out?</p>
              <div className="flex flex-wrap items-end gap-3">
                <SteppableSelect label="Up to" value={maxSwaps} onValueChange={setMaxSwaps} options={swapOptions} />
                <Button type="submit" size="sm">
                  Next
                  <ArrowRight className="size-4" />
                </Button>
              </div>
            </form>
          ) : (
            <form onSubmit={submitOpponents} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1">
                <p className="text-sm font-medium">Which teams do you want to optimize against?</p>
                <p className="text-xs text-muted-foreground">
                  The optimizer raises your win probability against the checked teams. Uncheck any you don&apos;t
                  want it to plan around.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Button type="button" variant="outline" size="xs" onClick={() => setExcludedTeams(new Set())}
                  disabled={selectedCount === opponents.length}>
                  Select all
                </Button>
                <Button type="button" variant="outline" size="xs" onClick={() => setExcludedTeams(new Set(opponents))}
                  disabled={selectedCount === 0}>
                  None
                </Button>
                <span className="ml-auto text-xs text-muted-foreground tabular-nums">
                  {selectedCount} of {opponents.length}
                </span>
              </div>
              <fieldset className="grid grid-cols-1 gap-x-4 gap-y-2.5 sm:grid-cols-2">
                <legend className="sr-only">Opponents</legend>
                {opponents.map((t) => (
                  <label key={t} className="flex cursor-pointer items-center gap-2.5 text-sm">
                    <Checkbox checked={!excludedTeams.has(t)} onCheckedChange={(checked) => toggleOpponent(t, checked)} />
                    <span className="team-name">{t}</span>
                  </label>
                ))}
              </fieldset>
              {selectedCount === 0 && <p className="text-xs text-loss">Pick at least one team.</p>}
              <div className="flex items-center gap-2">
                <Button type="button" variant="ghost" size="sm" onClick={() => setStep("swaps")}>
                  <ArrowLeft className="size-4" />
                  Back
                </Button>
                <Button type="submit" size="sm" className="ml-auto" disabled={selectedCount === 0}>
                  <ArrowLeftRight className="size-4" />
                  Optimize
                </Button>
              </div>
            </form>
          )}
          {error && <p className="text-sm text-loss">{error}</p>}
        </DialogContent>
      </Dialog>
    </>
  );
}

type RowStatus = "kept" | "out" | "in";
interface CompareRow {
  player: RosterRankRow;
  status: RowStatus;
}

function average(values: number[]): number | null {
  const finite = values.filter(Number.isFinite);
  return finite.length ? finite.reduce((a, b) => a + b, 0) / finite.length : null;
}

const byRank = (a: CompareRow, b: CompareRow) =>
  (Number.isFinite(a.player.Rank) ? a.player.Rank : Infinity) - (Number.isFinite(b.player.Rank) ? b.player.Rank : Infinity);

/**
 * The optimizer's answer, drawn over the Roster page's own columns (NBA
 * Team, Rank, Games Left). Desktop: the current roster (players leaving in
 * red) beside the roster after the swaps (players joining in green).
 * Narrower screens: one table, each player leaving followed directly by
 * the player replacing them.
 */
export function OptimizerResults({
  result,
  roster,
  allPlayers,
  gamesLeft,
  placementFor,
  onClose,
  format = "wl",
}: {
  result: RosterOptimizerResult;
  // The season's standings format -- picks the headline number.
  format?: SeasonFormat;
  // This team's real roster, as the Roster page shows it.
  roster: RosterRankRow[];
  // Every player that season (rostered or free agent), for the incoming
  // players' Rank/NBA team -- same names the optimizer joins on server-side.
  allPlayers: RosterRankRow[];
  gamesLeft: (row: RosterRankRow) => ReactNode;
  // This team's league placement if its average rank were `avgRank`.
  placementFor: (avgRank: number) => number | null;
  onClose: () => void;
}) {
  const improved = result.swaps.length > 0;
  const byName = new Map(allPlayers.map((r) => [r.Player, r]));
  const dropped = new Set(result.swaps.map((sw) => sw.drop.name));
  const incoming = (sw: RosterOptimizerResult["swaps"][number]): RosterRankRow =>
    byName.get(sw.add.name) ?? {
      Year: result.year,
      FantasyTeam: null,
      Player: sw.add.name,
      NBATeam: sw.add.nba_team ?? "",
      Rank: NaN,
    };

  const current: CompareRow[] = roster
    .map((player) => ({ player, status: dropped.has(player.Player) ? "out" : "kept" }) as CompareRow)
    .sort(byRank);
  const after: CompareRow[] = [
    ...current.filter((r) => r.status === "kept"),
    ...result.swaps.map((sw) => ({ player: incoming(sw), status: "in" }) as CompareRow),
  ].sort(byRank);
  // Mobile: the current order, with each replacement right under the
  // player it replaces.
  const replacementFor = new Map(result.swaps.map((sw) => [sw.drop.name, incoming(sw)]));
  const inline: CompareRow[] = current.flatMap((r) => {
    const add = replacementFor.get(r.player.Player);
    return add ? [r, { player: add, status: "in" as const }] : [r];
  });

  const beforeAvg = average(current.map((r) => r.player.Rank));
  const afterAvg = average(after.map((r) => r.player.Rank));

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <HeadlineOdds
          format={format}
          startWin={result.start_matchup_win}
          startCats={result.start}
          after={improved ? { win: result.end_matchup_win, cats: result.end } : undefined}
          extra={improved ? `with ${result.swaps.length} ${result.swaps.length === 1 ? "swap" : "swaps"}` : undefined}
        />
        <Button type="button" variant="outline" size="sm" onClick={onClose}>
          Back to roster
        </Button>
      </div>

      {improved ? (
        <>
          <div className="hidden gap-6 lg:grid lg:grid-cols-2">
            <section aria-label="Current roster">
              <h3 className="mb-2 text-sm font-semibold">Current roster</h3>
              <CompareTable rows={current} avgRank={beforeAvg} placement={beforeAvg != null ? placementFor(beforeAvg) : null} gamesLeft={gamesLeft} />
            </section>
            <section aria-label="Roster after swaps">
              <h3 className="mb-2 text-sm font-semibold">
                After {result.swaps.length} {result.swaps.length === 1 ? "swap" : "swaps"}
              </h3>
              <CompareTable rows={after} avgRank={afterAvg} placement={afterAvg != null ? placementFor(afterAvg) : null} gamesLeft={gamesLeft} />
            </section>
          </div>
          <div className="lg:hidden">
            <CompareTable
              rows={inline}
              avgRank={afterAvg}
              beforeAvgRank={beforeAvg}
              placement={afterAvg != null ? placementFor(afterAvg) : null}
              gamesLeft={gamesLeft}
            />
          </div>
          <CategoryDetails result={result} />
        </>
      ) : (
        <p className="rounded-lg bg-muted/60 p-3 text-sm">
          No swap is worth making this week: none of the available players would raise this team&apos;s weekly win
          probability by at least 1 point. Check back next week.
        </p>
      )}

      <p className="text-xs text-muted-foreground">
        {result.ignored_opponents?.length
          ? `Win probabilities are against an average of the teams you picked (leaving out ${listNames(result.ignored_opponents)}), and turnovers are left out.`
          : "Win probabilities are against an average opponent in this league, and turnovers are left out."}{" "}
        Stats as of{" "}
        {formatAsOf(result.data_as_of.player_stats)}; rosters and projections refresh daily.
      </p>
    </div>
  );
}

const ROW_STYLE: Record<RowStatus, string> = {
  kept: "",
  out: "bg-loss/10 hover:bg-loss/15",
  in: "bg-win/10 hover:bg-win/15",
};
const EDGE_STYLE: Record<RowStatus, string> = {
  kept: "",
  out: "shadow-[inset_3px_0_0_var(--loss)]",
  in: "shadow-[inset_3px_0_0_var(--win)]",
};

function CompareTable({
  rows,
  avgRank,
  beforeAvgRank,
  placement,
  gamesLeft,
}: {
  rows: CompareRow[];
  avgRank: number | null;
  // When set, the Average Rank row reads "before → after" (mobile's single table).
  beforeAvgRank?: number | null;
  placement: number | null;
  gamesLeft: (row: RosterRankRow) => ReactNode;
}) {
  // Single-table (mobile) layout: shorter headers and wrapping names so
  // all four columns fit a phone's width.
  const compact = beforeAvgRank !== undefined;
  return (
    <Table>
      {compact && <caption className="sr-only">Team is the NBA team; Left is games left this week.</caption>}
      <TableHeader>
        <TableRow>
          <TableHead>Player</TableHead>
          <TableHead>{compact ? "Team" : "NBA Team"}</TableHead>
          <TableHead className="text-right">Rank</TableHead>
          <TableHead className="text-right">{compact ? "Left" : "Games Left"}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        <TableRow className="bg-focus-row">
          {compact ? (
            // Single-table (mobile) layout: one full-width row, so the
            // before -> after reading doesn't widen the Rank column.
            <TableCell colSpan={4}>
              <span className="flex items-baseline justify-between gap-3">
                <span className="team-name text-primary">Average Rank</span>
                <span className="font-mono font-extrabold whitespace-nowrap tabular-nums text-primary">
                  {beforeAvgRank != null && (
                    <span className="font-bold text-muted-foreground">
                      {beforeAvgRank.toFixed(1)}
                      <ArrowRight className="mx-1 inline size-3 align-[-1px]" aria-label="to" />
                    </span>
                  )}
                  {avgRank != null ? avgRank.toFixed(1) : "—"}
                  {placement != null && (
                    <span className="ml-1 font-sans text-xs font-bold text-muted-foreground">({ordinal(placement)})</span>
                  )}
                </span>
              </span>
            </TableCell>
          ) : (
            <>
              <TableCell className="team-name text-primary">Average Rank</TableCell>
              <TableCell />
              <TableCell className="text-right font-mono font-extrabold whitespace-nowrap tabular-nums text-primary">
                {avgRank != null ? avgRank.toFixed(1) : "—"}
                {placement != null && (
                  <span className="ml-1 font-sans text-xs font-bold text-muted-foreground">({ordinal(placement)})</span>
                )}
              </TableCell>
              <TableCell />
            </>
          )}
        </TableRow>
        {rows.map(({ player, status }) => (
          <TableRow key={`${status}-${player.Player}`} className={ROW_STYLE[status]}>
            <TableCell className={cn("font-sans font-semibold", compact && "whitespace-normal", EDGE_STYLE[status])}>
              <span className="flex items-center gap-1.5 leading-tight">
                {status === "out" && <Minus className="size-3.5 shrink-0 text-loss" aria-label="Leaving" />}
                {status === "in" && <Plus className="size-3.5 shrink-0 text-win" aria-label="Joining" />}
                <span className={cn(status === "out" && "text-loss", status === "in" && "text-win")}>{player.Player}</span>
              </span>
            </TableCell>
            <TableCell className="text-muted-foreground">{player.NBATeam || "—"}</TableCell>
            <TableCell className="text-right font-mono tabular-nums">
              {Number.isFinite(player.Rank) ? player.Rank : "—"}
            </TableCell>
            <TableCell className="text-right font-mono tabular-nums">{gamesLeft(player)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function CategoryDetails({ result }: { result: RosterOptimizerResult }) {
  return (
    <details className="group">
      <summary className="cursor-pointer text-sm font-semibold select-none">Win probability by category</summary>
      <div className="mt-3">
        <CategoryOddsBars
          categories={result.categories}
          strongest={result.strongest}
          before={result.start}
          after={result.end}
        />
      </div>
    </details>
  );
}

/**
 * Weekly win probability per category as bars: `before` alone, or `before`
 * (grey) with `after` drawn over it and the change in points. Shared by the
 * optimizer's results and the Roster page's premium category panel.
 */
export function CategoryOddsBars({
  categories,
  strongest,
  before,
  after,
}: {
  categories: OptimizerCategory[];
  strongest: OptimizerCategory[];
  before: Record<OptimizerCategory, number>;
  // Omitted (or identical to before) -> just the current chances.
  after?: Record<OptimizerCategory, number>;
}) {
  const changed = after != null && categories.some((c) => Math.abs(after[c] - before[c]) > 0.0005);
  return (
    <div>
      <div className="grid max-w-xl grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-1.5 text-sm">
        {categories.map((cat) => {
          const b = before[cat];
          const a = changed ? after![cat] : b;
          const delta = a - b;
          return (
            <div key={cat} className="contents">
              <span className={cn("w-12 font-medium", strongest.includes(cat) && "text-primary")}>{cat}</span>
              {/* Two bars from the left, layered by direction (user spec):
                  gain -> green bar = new value, grey "before" bar in front
                  of it, so the green sticking out is the improvement;
                  loss -> grey bar = old value behind, red bar = new
                  (shorter) value in front. Grey at 80% opacity. */}
              <div className="relative h-2 overflow-hidden rounded-full bg-muted" aria-hidden>
                {!changed || Math.abs(delta) <= 0.0005 ? (
                  <div
                    className={cn("absolute inset-y-0 left-0 rounded-full", changed ? "bg-muted-foreground opacity-80" : "bg-primary/70")}
                    style={{ width: pct(b) }}
                  />
                ) : delta > 0 ? (
                  <>
                    <div className="absolute inset-y-0 left-0 rounded-full bg-win" style={{ width: pct(a) }} />
                    {/* Track-colored backing so the 80% grey doesn't pick up a green tint. */}
                    <div className="absolute inset-y-0 left-0 rounded-full bg-muted" style={{ width: pct(b) }} />
                    <div className="absolute inset-y-0 left-0 rounded-full bg-muted-foreground opacity-80" style={{ width: pct(b) }} />
                  </>
                ) : (
                  <>
                    <div className="absolute inset-y-0 left-0 rounded-full bg-muted-foreground opacity-80" style={{ width: pct(b) }} />
                    <div className="absolute inset-y-0 left-0 rounded-full bg-loss" style={{ width: pct(a) }} />
                  </>
                )}
              </div>
              <span className="w-28 text-right tabular-nums">
                {changed ? (
                  <>
                    <span className="text-muted-foreground">{pct(b)}</span> → {pct(a)}{" "}
                    <span className={cn("text-xs", delta > 0.005 ? "text-win" : delta < -0.005 ? "text-loss" : "text-muted-foreground")}>
                      {pts(delta)}
                    </span>
                  </>
                ) : (
                  pct(b)
                )}
              </span>
            </div>
          );
        })}
      </div>
      {strongest.length > 0 && (
        <p className="mt-2 text-xs text-muted-foreground">
          Blue categories are this team&apos;s current strengths.
        </p>
      )}
    </div>
  );
}

function listNames(names: string[]): string {
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

function formatAsOf(iso: string | null): string {
  if (!iso) return "an unknown time";
  return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}
