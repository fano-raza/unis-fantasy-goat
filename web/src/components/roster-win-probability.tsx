"use client";

import { useEffect, useState } from "react";
import { ArrowDown, ArrowUp, Crown } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { LoadingOverlay } from "@/components/loading-overlay";
import { expectedCategories, type SeasonFormat } from "@/components/headline-odds";
import { usePremium } from "@/components/premium";
import {
  ApiError,
  getRosterCategoryOdds,
  getRosterWinProbabilities,
  type RosterCategoryOdds,
  type RosterWinProbabilities,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const pct = (x: number) => `${Math.round(x * 100)}%`;

// Waits for a burst of manual swaps to settle before asking the server --
// same reasoning and value as the "Win probability by category" card.
const DEBOUNCE_MS = 300;

// Decorative placeholder ranking for the locked preview -- roughly the
// shape of a real 10-team spread, nothing more.
const PREVIEW_PLACES = [0.71, 0.64, 0.58, 0.55, 0.51, 0.47, 0.43, 0.38, 0.32, 0.26];

/**
 * Roster Rankings' "Win probability" sub-tab (premium, user request): every
 * team ranked by weekly matchup win probability instead of average player
 * rank. Every team but the one on screen reads the daily cached snapshot
 * (Ref/roster_win_probability.csv); the on-screen team's own number is
 * recomputed live when the Roster page has an active what-if (swaps,
 * removals, players brought back from IR) -- same one-sided simulation as
 * the Average Rank sub-tab, just slower to settle since it's a live call
 * instead of a client-side recompute. `roster`: the simulated ACTIVE
 * roster's names, or null for no what-if.
 */
export function RosterWinProbabilityTab({
  team,
  roster,
  format,
}: {
  team: string;
  roster: string[] | null;
  format: SeasonFormat;
}) {
  const premium = usePremium();
  if (!premium.unlocked || !premium.password) {
    return <LockedPreview onUnlock={() => premium.requireUnlock()} />;
  }
  return (
    <UnlockedRanking team={team} roster={roster} format={format} password={premium.password} onRejected={premium.lock} />
  );
}

function LockedPreview({ onUnlock }: { onUnlock: () => void }) {
  return (
    <div className="relative">
      <div className="flex flex-col gap-2 opacity-50 blur-[3px] select-none" aria-hidden>
        {PREVIEW_PLACES.map((p, i) => (
          <div key={i} className="flex items-center gap-3 text-sm">
            <span className="w-5 font-mono tabular-nums text-muted-foreground">{i + 1}</span>
            <span className="team-name flex-1">Team {i + 1}</span>
            <span className="w-12 text-right font-mono tabular-nums">{pct(p)}</span>
          </div>
        ))}
      </div>
      <div className="absolute inset-0 flex items-center justify-center">
        <Button
          type="button"
          variant="outline"
          onClick={onUnlock}
          className="border-gold/60 bg-card text-gold hover:bg-gold/10 hover:text-gold"
        >
          <Crown className="size-4" aria-hidden />
          Unlock with Premium
        </Button>
      </div>
    </div>
  );
}

function UnlockedRanking({
  team,
  roster,
  format,
  password,
  onRejected,
}: {
  team: string;
  roster: string[] | null;
  format: SeasonFormat;
  password: string;
  onRejected: () => void;
}) {
  const [data, setData] = useState<RosterWinProbabilities | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getRosterWinProbabilities({ password })
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          onRejected(); // password changed since this session unlocked
          return;
        }
        setError("Couldn't load win probabilities. Try again in a moment.");
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [password, onRejected]);

  // This team's own live recompute while a what-if is active. Every other
  // team keeps its cached number -- a one-sided simulation, same as the
  // Average Rank sub-tab.
  const [simOdds, setSimOdds] = useState<RosterCategoryOdds | null>(null);
  const [simLoading, setSimLoading] = useState(false);
  const simulating = roster != null;
  const rosterKey = JSON.stringify(roster);

  useEffect(() => {
    if (!simulating) {
      setSimOdds(null);
      setSimLoading(false);
      return;
    }
    let cancelled = false;
    setSimLoading(true);
    const id = setTimeout(() => {
      const names: string[] = JSON.parse(rosterKey);
      getRosterCategoryOdds({ team, password, roster: names })
        .then((res) => {
          if (cancelled) return;
          setSimOdds(res);
        })
        .catch((err) => {
          if (cancelled) return;
          if (err instanceof ApiError && err.status === 401) onRejected();
        })
        .finally(() => !cancelled && setSimLoading(false));
    }, DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(id);
    };
  }, [simulating, rosterKey, team, password, onRejected]);

  if (error && !data) return <p className="text-sm text-muted-foreground">{error}</p>;

  const cats = format === "cats";
  const fmt = (x: number) => (cats ? x.toFixed(1) : pct(x));
  const metric = (matchupWin: number, categories: Record<string, number>) =>
    cats ? expectedCategories(categories) : matchupWin;

  const rows = data
    ? data.teams.map((row) => {
        const realValue = metric(row.matchup_win, row.categories);
        if (row.team !== team || !simOdds) return { team: row.team, value: realValue, realValue };
        return { team: row.team, value: metric(simOdds.current_matchup_win, simOdds.current), realValue };
      })
    : [];
  const sorted = [...rows].sort((a, b) => b.value - a.value);

  return (
    <LoadingOverlay active={loading} hasContent={data != null} label="Calculating win probabilities">
      {data && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Place</TableHead>
              <TableHead>Team</TableHead>
              <TableHead className="text-right">{cats ? "Exp. Categories" : "Win Probability"}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((row, i) => {
              const onTeam = simulating && row.team === team;
              return (
                <TableRow key={row.team} className={cn(row.team === team && "bg-focus-row")}>
                  <TableCell>{i + 1}</TableCell>
                  <TableCell className={cn("team-name", onTeam && "text-yellow-500")}>{row.team}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {onTeam && simLoading && (
                      <span className="mr-2 font-sans text-xs text-muted-foreground">recalculating…</span>
                    )}
                    {onTeam && simOdds && (
                      <span className="mr-2 font-sans text-xs text-muted-foreground">was {fmt(row.realValue)}</span>
                    )}
                    {onTeam && simOdds && row.value !== row.realValue && (
                      // Higher win probability is better, so a rise is an improvement.
                      row.value > row.realValue ? (
                        <ArrowUp className="mr-1 inline size-3.5 align-[-2px] text-win" aria-label="Improved" />
                      ) : (
                        <ArrowDown className="mr-1 inline size-3.5 align-[-2px] text-loss" aria-label="Worse" />
                      )
                    )}
                    {fmt(row.value)}
                    {cats && <span className="ml-1 font-sans text-xs text-muted-foreground">of 9</span>}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}
    </LoadingOverlay>
  );
}
