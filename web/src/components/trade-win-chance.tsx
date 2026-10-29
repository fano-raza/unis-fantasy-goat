"use client";

import { useEffect, useState } from "react";
import { ArrowRight, Crown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadingOverlay } from "@/components/loading-overlay";
import { CategoryOddsBars } from "@/components/roster-optimizer";
import { usePremium } from "@/components/premium";
import { ApiError, getTradeOdds, type TradeOdds, type TradeOddsSide } from "@/lib/api";
import { cn } from "@/lib/utils";

// Waits for a burst of clicks to settle before asking the server.
const DEBOUNCE_MS = 300;
const pct = (x: number) => `${Math.round(x * 100)}%`;

/**
 * Premium panel at the bottom of the Trade Hub: how the trade on screen
 * changes each team's weekly matchup win chance, overall and by category.
 * Needs a team on both sides. `drops`: who a team releases to make room,
 * as chosen by a recommendation (omitted -> the server picks the player
 * that team misses least).
 */
export function TradeWinChance({
  teamA,
  teamB,
  aSends,
  bSends,
  drops,
}: {
  teamA: string | null;
  teamB: string | null;
  aSends: string[];
  bSends: string[];
  drops: Record<string, string[]> | null;
}) {
  const premium = usePremium();
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Win chance
          <span className="flex items-center gap-1 font-sans text-xs font-semibold text-gold">
            <Crown className={premium.unlocked ? "size-3.5 fill-current" : "size-3.5"} aria-hidden />
            Premium
          </span>
        </CardTitle>
        <CardDescription>How often each team would win its weekly matchup, before and after this trade</CardDescription>
      </CardHeader>
      <CardContent>
        {!premium.unlocked || !premium.password ? (
          <LockedPreview onUnlock={() => premium.requireUnlock()} />
        ) : !teamA || !teamB ? (
          <p className="text-sm text-muted-foreground">Choose a team on both sides to see how the trade changes their chances.</p>
        ) : (
          <UnlockedOdds
            teamA={teamA}
            teamB={teamB}
            aSends={aSends}
            bSends={bSends}
            drops={drops}
            password={premium.password}
            onRejected={premium.lock}
          />
        )}
      </CardContent>
    </Card>
  );
}

function LockedPreview({ onUnlock }: { onUnlock: () => void }) {
  return (
    <div className="relative">
      <div className="grid gap-6 opacity-50 blur-[3px] select-none sm:grid-cols-2" aria-hidden>
        {[
          ["48%", "55%"],
          ["52%", "50%"],
        ].map(([a, b], i) => (
          <div key={i} className="flex flex-col gap-2">
            <span className="h-3 w-20 rounded bg-muted" />
            <span className="font-display text-3xl font-bold">
              {a} → {b}
            </span>
            <span className="h-2 w-full rounded-full bg-muted" />
            <span className="h-2 w-3/4 rounded-full bg-muted" />
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
  teamA,
  teamB,
  aSends,
  bSends,
  drops,
  password,
  onRejected,
}: {
  teamA: string;
  teamB: string;
  aSends: string[];
  bSends: string[];
  drops: Record<string, string[]> | null;
  password: string;
  onRejected: () => void;
}) {
  // The last answer, tagged with the trade it was for -- "loading" is
  // simply "what's on screen is for a different trade".
  const [result, setResult] = useState<{ key: string; odds: TradeOdds | null; error: string | null } | null>(null);
  const key = JSON.stringify([teamA, teamB, aSends, bSends, drops]);
  const loading = result?.key !== key;
  const odds = result?.odds ?? null;
  const error = result?.key === key ? result.error : null;

  useEffect(() => {
    let cancelled = false;
    const id = setTimeout(() => {
      const [a, b, as, bs, d] = JSON.parse(key) as [string, string, string[], string[], Record<string, string[]> | null];
      getTradeOdds({ password, team_a: a, team_b: b, a_sends: as, b_sends: bs, ...(d ? { drops: d } : {}) })
        .then((res) => {
          if (!cancelled) setResult({ key, odds: res, error: null });
        })
        .catch((err) => {
          if (cancelled) return;
          if (err instanceof ApiError && err.status === 401) {
            onRejected();
            return;
          }
          setResult((prev) => ({
            key,
            odds: prev?.odds ?? null,
            error:
              err instanceof ApiError && err.status === 404
                ? "One of these teams has no roster this season."
                : err instanceof ApiError && err.status === 422
                  ? "This trade can't be scored: a player is on both sides."
                  : "Couldn't load win chances. Try again in a moment.",
          }));
        });
    }, DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(id);
    };
  }, [key, password, onRejected]);

  if (error && !odds) return <p className="text-sm text-muted-foreground">{error}</p>;
  const traded = aSends.length > 0 || bSends.length > 0;

  return (
    <LoadingOverlay active={loading} hasContent={odds != null} label="Calculating win chances">
      {odds && (
        <div className="flex flex-col gap-4">
          {error && <p className="text-sm text-loss">{error}</p>}
          <div className="grid gap-6 sm:grid-cols-2">
            {odds.teams.map((side) => (
              <TeamOdds key={side.team} side={side} categories={odds.categories} traded={traded} />
            ))}
          </div>
          {(odds.uncounted.length > 0 || odds.unknown.length > 0) && (
            <p className="text-xs text-muted-foreground">
              {odds.uncounted.length > 0 && <>Not counted (on IR): {odds.uncounted.join(", ")}. </>}
              {odds.unknown.length > 0 && <>Not counted (no stats this season): {odds.unknown.join(", ")}.</>}
            </p>
          )}
          {!traded && <p className="text-xs text-muted-foreground">Pick players on either side to see how the trade would change these.</p>}
        </div>
      )}
    </LoadingOverlay>
  );
}

function TeamOdds({ side, categories, traded }: { side: TradeOddsSide; categories: TradeOdds["categories"]; traded: boolean }) {
  const delta = side.matchup_win - side.start_matchup_win;
  const short = side.active_after < side.active_before;
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-col gap-1">
        <span className="label">{side.team}</span>
        <span className="font-display text-3xl leading-none font-bold tabular-nums [font-variation-settings:'opsz'_36]">
          {pct(side.start_matchup_win)}
          {traded && (
            <>
              <ArrowRight className="mx-1.5 inline size-5 align-[-2px] text-muted-foreground" aria-label="to" />
              <span className={cn(delta > 0.0005 ? "text-win" : delta < -0.0005 ? "text-loss" : "text-foreground")}>{pct(side.matchup_win)}</span>
            </>
          )}
        </span>
      </div>
      <CategoryOddsBars categories={categories} strongest={[]} before={side.start} after={traded ? side.after : undefined} />
      {(side.drops.length > 0 || short) && (
        <p className="text-xs text-muted-foreground">
          {side.drops.length > 0 &&
            `${side.team} releases ${side.drops.join(" and ")} to make room${side.auto_drop ? " (the player it would miss least)" : ""}. `}
          {short && `${side.team} is left with an open roster spot; add a free agent to the other side's list to fill it.`}
        </p>
      )}
    </div>
  );
}
