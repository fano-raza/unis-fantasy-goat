"use client";

import { useState, type FormEvent } from "react";
import { ArrowLeftRight, ArrowRight, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { SteppableSelect } from "@/components/steppable-select";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { cn } from "@/lib/utils";
import {
  ApiError,
  runRosterOptimizer,
  type OptimizerCategory,
  type OptimizerPlayer,
  type RosterOptimizerResult,
} from "@/lib/api";

// Kept for the browser session only, after the server has accepted it --
// the password itself is checked server-side (never shipped in the bundle).
const PASSWORD_KEY = "roster-optimizer-password";
// Category changes smaller than this (2 points of weekly win chance) aren't
// worth calling out in a swap's "helps / costs" line.
const NOTABLE = 0.02;

const pct = (x: number) => `${Math.round(x * 100)}%`;
const pts = (x: number) => `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(Math.round(x * 100))}`;

function readStoredPassword(): string {
  try {
    return sessionStorage.getItem(PASSWORD_KEY) ?? "";
  } catch {
    return "";
  }
}

function errorMessage(err: unknown): { text: string; badPassword: boolean } {
  if (err instanceof ApiError) {
    if (err.status === 401) return { text: "That password didn't work.", badPassword: true };
    let detail = "";
    try {
      detail = JSON.parse(err.message).detail ?? "";
    } catch {}
    if (err.status === 503) return { text: detail || "The optimizer isn't available right now.", badPassword: false };
    if (err.status === 404) return { text: detail || "No current roster found for this team.", badPassword: false };
  }
  return { text: "Couldn't reach the server. Try again in a moment.", badPassword: false };
}

/**
 * "Optimize roster" button for the Roster page (current season only): opens a
 * dialog that runs the backtested Roster Optimizer for `team` and shows this
 * week's recommended drop/add swaps. See _planning/roster-optimizer.md.
 */
export function RosterOptimizerButton({ team, rosterSize }: { team: string; rosterSize: number }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button type="button" size="sm" onClick={() => setOpen(true)} disabled={!team || rosterSize === 0}>
        <ArrowLeftRight className="size-4" />
        Optimize roster
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-2xl">
          {open && <OptimizerPanel team={team} rosterSize={rosterSize} />}
        </DialogContent>
      </Dialog>
    </>
  );
}

function OptimizerPanel({ team, rosterSize }: { team: string; rosterSize: number }) {
  // Lazy initializers are safe here: this panel only mounts after a click
  // (inside the opened dialog), never during server render/hydration.
  const [password, setPassword] = useState(readStoredPassword);
  const [rememberedPassword, setRememberedPassword] = useState(() => readStoredPassword() !== "");
  const [maxSwaps, setMaxSwaps] = useState(Math.min(3, rosterSize));
  const [result, setResult] = useState<RosterOptimizerResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(e?: FormEvent) {
    e?.preventDefault();
    if (!password) return;
    setLoading(true);
    setError(null);
    try {
      const res = await runRosterOptimizer({ team, password, max_swaps: maxSwaps });
      setResult(res);
      setRememberedPassword(true);
      try {
        sessionStorage.setItem(PASSWORD_KEY, password);
      } catch {}
    } catch (err) {
      const { text, badPassword } = errorMessage(err);
      setError(text);
      if (badPassword) {
        setRememberedPassword(false);
        setPassword("");
        try {
          sessionStorage.removeItem(PASSWORD_KEY);
        } catch {}
      }
    } finally {
      setLoading(false);
    }
  }

  const swapOptions = Array.from({ length: rosterSize }, (_, i) => i + 1);

  return (
    <div className="flex flex-col gap-5">
      <DialogHeader>
        <DialogTitle className="font-display text-2xl font-bold [font-variation-settings:'opsz'_36]">
          Optimize {team}&apos;s roster
        </DialogTitle>
        <DialogDescription>
          Finds the free-agent pickups that most raise this team&apos;s chances of winning its weekly matchups,
          based on projected production for the rest of the season. Run it once a week.
        </DialogDescription>
      </DialogHeader>

      <form onSubmit={run} className="flex flex-wrap items-end gap-4">
        {!rememberedPassword && (
          <label className="flex flex-col gap-1.5">
            <span className="label">Password</span>
            <span className="relative">
              <Lock className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                type="password"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  setError(null);
                }}
                autoFocus
                autoComplete="current-password"
                className="h-8 w-48 rounded-md border border-input bg-background pr-3 pl-8 text-sm outline-none focus-visible:border-ring"
              />
            </span>
          </label>
        )}
        <SteppableSelect label="Swaps" value={maxSwaps} onValueChange={setMaxSwaps} options={swapOptions} />
        <Button type="submit" size="sm" disabled={loading || !password}>
          {result ? "Run again" : "Find swaps"}
        </Button>
      </form>

      {error && <p className="text-sm text-loss">{error}</p>}

      {loading && (
        <div className="py-8">
          <LoadingBasketballs label="Weighing every swap" />
        </div>
      )}

      {!loading && result && <Results result={result} />}
    </div>
  );
}

function Results({ result }: { result: RosterOptimizerResult }) {
  const improved = result.swaps.length > 0;
  return (
    <div className="flex flex-col gap-6">
      <section aria-label="Weekly matchup win chance" className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="label">Weekly matchup win chance</span>
        <span className="font-display text-3xl font-bold tabular-nums [font-variation-settings:'opsz'_36]">
          {pct(result.start_matchup_win)}
          {improved && (
            <>
              <ArrowRight className="mx-1.5 inline size-5 align-[-2px] text-muted-foreground" aria-label="to" />
              <span className="text-win">{pct(result.end_matchup_win)}</span>
            </>
          )}
        </span>
        {improved && (
          <span className="text-sm text-muted-foreground">
            with {result.swaps.length} {result.swaps.length === 1 ? "swap" : "swaps"}
          </span>
        )}
      </section>

      {improved ? (
        <ol className="flex flex-col gap-3">
          {result.swaps.map((sw, i) => {
            const changes = Object.entries(sw.category_change) as [OptimizerCategory, number][];
            const helps = changes.filter(([, d]) => d >= NOTABLE).sort((a, b) => b[1] - a[1]).map(([c]) => c);
            const costs = changes.filter(([, d]) => d <= -NOTABLE).sort((a, b) => a[1] - b[1]).map(([c]) => c);
            return (
              <li key={`${sw.drop.id}-${sw.add.id}`} className="rounded-lg bg-muted/60 p-3">
                <div className="flex items-start gap-3">
                  <span className="font-display text-lg leading-6 font-bold text-muted-foreground tabular-nums">
                    {i + 1}
                  </span>
                  <div className="grid min-w-0 flex-1 gap-2 sm:grid-cols-[1fr_auto_1fr] sm:items-start">
                    <PlayerLine verb="Drop" player={sw.drop} />
                    <ArrowRight className="hidden size-4 self-center text-muted-foreground sm:block" />
                    <PlayerLine verb="Add" player={sw.add} />
                  </div>
                </div>
                <p className="mt-2 pl-7 text-xs text-muted-foreground">
                  {helps.length > 0 && (
                    <>
                      Helps <span className="font-medium text-win">{helps.join(", ")}</span>
                    </>
                  )}
                  {helps.length > 0 && costs.length > 0 && " · "}
                  {costs.length > 0 && (
                    <>
                      costs <span className="font-medium text-loss">{costs.join(", ")}</span>
                    </>
                  )}
                  {sw.matchup_win_after != null && (
                    <>
                      {(helps.length > 0 || costs.length > 0) && " · "}
                      win chance after: {pct(sw.matchup_win_after)}
                    </>
                  )}
                </p>
              </li>
            );
          })}
        </ol>
      ) : (
        <p className="rounded-lg bg-muted/60 p-3 text-sm">
          No swap is worth making this week: none of the available players would raise this team&apos;s weekly win
          chance by at least 1 point. Check back next week.
        </p>
      )}

      <CategoryTable result={result} />

      <p className="text-xs text-muted-foreground">
        Win chances are against an average opponent in this league, and turnovers are left out. Stats as of{" "}
        {formatAsOf(result.data_as_of.player_stats)}; rosters and projections refresh daily.
      </p>
    </div>
  );
}

function PlayerLine({ verb, player }: { verb: "Drop" | "Add"; player: OptimizerPlayer }) {
  const g = player.per_game;
  const flagged = player.injury_status && player.injury_status !== "ACTIVE";
  return (
    <div className="min-w-0">
      <div className="flex items-baseline gap-1.5">
        <span className={cn("text-xs font-medium", verb === "Drop" ? "text-loss" : "text-win")}>{verb}</span>
        <span className="truncate font-semibold">{player.name}</span>
        {player.nba_team && <span className="text-xs text-muted-foreground">{player.nba_team}</span>}
      </div>
      <div className="text-xs text-muted-foreground tabular-nums">
        {g.PTS} pts · {g.REB} reb · {g.AST} ast · {g["3PTM"]} 3pm · {g.STL} stl · {g.BLK} blk
      </div>
      <div className="text-xs text-muted-foreground tabular-nums">
        Plays ~{pct(player.availability)} of games
        {flagged && <span className="text-loss"> · {player.injury_status!.replaceAll("_", " ").toLowerCase()}</span>}
      </div>
    </div>
  );
}

function CategoryTable({ result }: { result: RosterOptimizerResult }) {
  const improved = result.swaps.length > 0;
  return (
    <section aria-label="Win chance by category">
      <h3 className="mb-2 text-sm font-semibold">Win chance by category</h3>
      <div className="grid grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-1.5 text-sm">
        {result.categories.map((cat) => {
          const before = result.start[cat];
          const after = result.end[cat];
          const delta = after - before;
          return (
            <div key={cat} className="contents">
              <span className={cn("w-12 font-medium", result.strongest.includes(cat) && "text-primary")}>{cat}</span>
              <div className="relative h-2 overflow-hidden rounded-full bg-muted" aria-hidden>
                <div className="absolute inset-y-0 left-0 rounded-full bg-foreground/25" style={{ width: pct(before) }} />
                {improved && (
                  <div
                    className={cn("absolute inset-y-0 left-0 rounded-full", delta >= 0 ? "bg-win/80" : "bg-loss/80")}
                    style={{ width: pct(after), opacity: 0.85 }}
                  />
                )}
              </div>
              <span className="w-28 text-right tabular-nums">
                {improved ? (
                  <>
                    <span className="text-muted-foreground">{pct(before)}</span> → {pct(after)}{" "}
                    <span className={cn("text-xs", delta > 0.005 ? "text-win" : delta < -0.005 ? "text-loss" : "text-muted-foreground")}>
                      {pts(delta)}
                    </span>
                  </>
                ) : (
                  pct(before)
                )}
              </span>
            </div>
          );
        })}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        Blue categories are this team&apos;s current strengths. Bars show how often it would win each category in a
        typical week{improved ? ", before (grey) and after the swaps" : ""}.
      </p>
    </section>
  );
}

function formatAsOf(iso: string | null): string {
  if (!iso) return "an unknown time";
  return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}
