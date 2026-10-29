"use client";

import { useEffect, useState } from "react";
import { ArrowRight, Crown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadingOverlay } from "@/components/loading-overlay";
import { CategoryOddsBars } from "@/components/roster-optimizer";
import { usePremium } from "@/components/premium";
import { ApiError, getRosterCategoryOdds, type RosterCategoryOdds } from "@/lib/api";

// Waits for a burst of manual swaps to settle before asking the server.
const DEBOUNCE_MS = 300;

const pct = (x: number) => `${Math.round(x * 100)}%`;

// Placeholder bar lengths for the locked preview -- decorative only.
const PREVIEW = [
  ["FG%", 0.62],
  ["FT%", 0.38],
  ["3PTM", 0.55],
  ["REB", 0.71],
  ["AST", 0.44],
  ["STL", 0.58],
  ["BLK", 0.3],
  ["PTS", 0.66],
] as const;

/**
 * Premium panel on the Roster page (current season): this team's weekly win
 * chance in each category, and how the page's what-ifs (swaps, removals,
 * players brought back from IR) change it. IR players never count. Visible
 * to everyone; locked until premium mode is on. `roster` is the simulated
 * ACTIVE roster's names, or null for no what-if.
 */
export function RosterCategoryOddsCard({ team, roster }: { team: string; roster: string[] | null }) {
  const premium = usePremium();
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Win probability by category
          <span className="flex items-center gap-1 font-sans text-xs font-semibold text-gold">
            <Crown className={premium.unlocked ? "size-3.5 fill-current" : "size-3.5"} aria-hidden />
            Premium
          </span>
        </CardTitle>
        <CardDescription>How often {team} would win each category in a typical week, and how your swaps change it</CardDescription>
      </CardHeader>
      <CardContent>
        {premium.unlocked && premium.password ? (
          <UnlockedOdds team={team} roster={roster} password={premium.password} onRejected={premium.lock} />
        ) : (
          <LockedPreview onUnlock={() => premium.requireUnlock()} />
        )}
      </CardContent>
    </Card>
  );
}

function LockedPreview({ onUnlock }: { onUnlock: () => void }) {
  return (
    <div className="relative">
      <div className="grid max-w-xl grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-1.5 text-sm opacity-50 blur-[3px] select-none" aria-hidden>
        {PREVIEW.map(([cat, w]) => (
          <div key={cat} className="contents">
            <span className="w-12 font-medium">{cat}</span>
            <div className="relative h-2 overflow-hidden rounded-full bg-muted">
              <div className="absolute inset-y-0 left-0 rounded-full bg-primary/70" style={{ width: pct(w) }} />
            </div>
            <span className="w-28 text-right tabular-nums">{pct(w)}</span>
          </div>
        ))}
      </div>
      <div className="absolute inset-0 flex items-center justify-center">
        <Button type="button" variant="outline" onClick={onUnlock} className="border-gold/60 bg-card text-gold hover:bg-gold/10 hover:text-gold">
          <Crown className="size-4" aria-hidden />
          Unlock with Premium
        </Button>
      </div>
    </div>
  );
}

function UnlockedOdds({
  team,
  roster,
  password,
  onRejected,
}: {
  team: string;
  roster: string[] | null;
  password: string;
  onRejected: () => void;
}) {
  const [odds, setOdds] = useState<RosterCategoryOdds | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Stable dependency for the roster list (a new array every render upstream).
  const rosterKey = JSON.stringify(roster);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const id = setTimeout(() => {
      const simulated: string[] | null = JSON.parse(rosterKey);
      getRosterCategoryOdds({ team, password, ...(simulated ? { roster: simulated } : {}) })
        .then((res) => {
          if (cancelled) return;
          setOdds(res);
          setError(null);
        })
        .catch((err) => {
          if (cancelled) return;
          if (err instanceof ApiError && err.status === 401) {
            onRejected(); // password changed since this session unlocked
            return;
          }
          setError(
            err instanceof ApiError && err.status === 404
              ? `No current roster found for ${team}.`
              : err instanceof ApiError && err.status === 422
                ? "None of the players on this simulated roster have stats this season."
                : "Couldn't load win probabilities. Try again in a moment.",
          );
        })
        .finally(() => !cancelled && setLoading(false));
    }, DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(id);
    };
  }, [team, rosterKey, password, onRejected]);

  if (error && !odds) return <p className="text-sm text-muted-foreground">{error}</p>;

  const swapped = roster != null && odds != null;
  return (
    <LoadingOverlay active={loading} hasContent={odds != null} label="Calculating win probabilities">
      {odds && (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <span className="label">Weekly matchup win probability</span>
            <span className="font-display text-3xl leading-none font-bold tabular-nums [font-variation-settings:'opsz'_36]">
              {pct(odds.start_matchup_win)}
              {swapped && (
                <>
                  <ArrowRight className="mx-1.5 inline size-5 align-[-2px] text-muted-foreground" aria-label="to" />
                  <span className={odds.current_matchup_win >= odds.start_matchup_win ? "text-win" : "text-loss"}>
                    {pct(odds.current_matchup_win)}
                  </span>
                </>
              )}
            </span>
          </div>
          <CategoryOddsBars
            categories={odds.categories}
            strongest={odds.strongest}
            before={odds.start}
            after={odds.current}
          />
          <p className="text-xs text-muted-foreground">
            Counts {swapped ? odds.current_active_count : odds.start_active_count} active players; players on IR
            aren&apos;t counted.
            {!swapped && " Swap, remove, or bring back a player from IR above to see how each category would change."}
          </p>
          {odds.unknown.length > 0 && (
            <p className="text-xs text-muted-foreground">
              Not counted (no stats this season yet): {odds.unknown.join(", ")}.
            </p>
          )}
        </div>
      )}
    </LoadingOverlay>
  );
}
