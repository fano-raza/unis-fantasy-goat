"use client";

import { useEffect, useState } from "react";
import { Crown } from "lucide-react";
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
  getRosterWinProbabilities,
  type RosterWinProbabilities,
  type RosterWinProbabilityRow,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const pct = (x: number) => `${Math.round(x * 100)}%`;

// Decorative placeholder ranking for the locked preview -- roughly the
// shape of a real 10-team spread, nothing more.
const PREVIEW_PLACES = [0.71, 0.64, 0.58, 0.55, 0.51, 0.47, 0.43, 0.38, 0.32, 0.26];

/**
 * Roster Rankings' "Win probability" sub-tab (premium, user request): every
 * team ranked by its real roster's weekly matchup win probability instead of
 * average player rank. Same underlying number as the Roster Optimizer and
 * the "Win probability by category" card's start_matchup_win, just for the
 * whole league at once. Current season only -- it scores live rosters.
 */
export function RosterWinProbabilityTab({ team, format }: { team: string; format: SeasonFormat }) {
  const premium = usePremium();
  if (!premium.unlocked || !premium.password) {
    return <LockedPreview onUnlock={() => premium.requireUnlock()} />;
  }
  return (
    <UnlockedRanking team={team} format={format} password={premium.password} onRejected={premium.lock} />
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
  format,
  password,
  onRejected,
}: {
  team: string;
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

  if (error && !data) return <p className="text-sm text-muted-foreground">{error}</p>;

  const cats = format === "cats";
  const metric = (row: RosterWinProbabilityRow) => (cats ? expectedCategories(row.categories) : row.matchup_win);
  const fmt = (x: number) => (cats ? x.toFixed(1) : pct(x));
  const sorted = data ? [...data.teams].sort((a, b) => metric(b) - metric(a)) : [];

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
            {sorted.map((row, i) => (
              <TableRow key={row.team} className={cn(row.team === team && "bg-focus-row")}>
                <TableCell>{i + 1}</TableCell>
                <TableCell className="team-name">{row.team}</TableCell>
                <TableCell className="text-right font-mono tabular-nums">
                  {fmt(metric(row))}
                  {cats && <span className="ml-1 font-sans text-xs text-muted-foreground">of 9</span>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </LoadingOverlay>
  );
}
