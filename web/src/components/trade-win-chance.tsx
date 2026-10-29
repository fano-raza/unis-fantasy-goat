"use client";

import { useEffect, useState } from "react";
import { Crown, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadingOverlay } from "@/components/loading-overlay";
import { CategoryOddsBars } from "@/components/roster-optimizer";
import { usePremium } from "@/components/premium";
import { ApiError, getTradeOdds, type TradeOdds, type TradeOddsSide } from "@/lib/api";
import { HeadlineOdds, type SeasonFormat } from "@/components/headline-odds";

// Waits for a burst of clicks to settle before asking the server.
const DEBOUNCE_MS = 300;

/**
 * Premium panel at the bottom of the Trade Hub: how the trade on screen
 * changes each team's weekly matchup win probability, overall and by category.
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
  overLimit = [],
  onSuggestedDrops,
  format = "wl",
}: {
  teamA: string | null;
  teamB: string | null;
  aSends: string[];
  bSends: string[];
  drops: Record<string, string[]> | null;
  // Teams left over their roster limit on purpose (the user undid an
  // auto-drop): no win probability until they drop someone.
  overLimit?: { team: string; overBy: number }[];
  // A team ended up with too many players: the server's pick(s) for who it
  // would release, for the page to drop visibly ("Auto-dropped").
  onSuggestedDrops?: (team: string, names: string[]) => void;
  // The season's standings format -- picks the headline number.
  format?: SeasonFormat;
}) {
  const premium = usePremium();
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Win probability
          <span className="flex items-center gap-1 font-sans text-xs font-semibold text-gold">
            <Crown className={premium.unlocked ? "size-3.5 fill-current" : "size-3.5"} aria-hidden />
            Premium
          </span>
        </CardTitle>
        <CardDescription>
          {format === "cats"
            ? "How many categories each team would win in a typical week, before and after this trade"
            : "How often each team would win its weekly matchup, before and after this trade"}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {!premium.unlocked || !premium.password ? (
          <LockedPreview onUnlock={() => premium.requireUnlock()} />
        ) : !teamA || !teamB ? (
          <p className="text-sm text-muted-foreground">Choose a team on both sides to see how the trade changes their win probabilities.</p>
        ) : overLimit.length > 0 ? (
          <OverLimitMessage teams={overLimit} />
        ) : (
          <UnlockedOdds
            teamA={teamA}
            teamB={teamB}
            aSends={aSends}
            bSends={bSends}
            drops={drops}
            format={format}
            password={premium.password}
            onRejected={premium.lock}
            onSuggestedDrops={onSuggestedDrops}
          />
        )}
      </CardContent>
    </Card>
  );
}

function OverLimitMessage({ teams }: { teams: { team: string; overBy: number }[] }) {
  return (
    <div className="flex flex-col gap-1.5 rounded-md border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
      {teams.map(({ team, overBy }) => (
        <p key={team} className="flex items-start gap-2">
          <TriangleAlert className="mt-0.5 size-4 shrink-0 text-gold" aria-hidden />
          <span>
            {team} has too many players on its roster and must drop {overBy === 1 ? "one" : overBy} to calculate the win
            probability.
          </span>
        </p>
      ))}
    </div>
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
  format,
  password,
  onRejected,
  onSuggestedDrops,
}: {
  teamA: string;
  teamB: string;
  aSends: string[];
  bSends: string[];
  drops: Record<string, string[]> | null;
  format: SeasonFormat;
  password: string;
  onRejected: () => void;
  onSuggestedDrops?: (team: string, names: string[]) => void;
}) {
  // The last answer, tagged with the trade it was for -- "loading" is
  // simply "what's on screen is for a different trade".
  const [result, setResult] = useState<{ key: string; odds: TradeOdds | null; error: string | null } | null>(null);
  const key = JSON.stringify([teamA, teamB, aSends, bSends, drops]);
  // An answer for an over-limit roster isn't shown: the page drops the
  // suggested player and asks again (keep the last complete numbers up).
  const [shown, setShown] = useState<TradeOdds | null>(null);
  const loading = result?.key !== key || (result?.odds != null && !result.odds.complete);
  const odds = result?.odds?.complete ? result.odds : shown;
  const error = result?.key === key ? result.error : null;
  // Over the limit but the server had nobody to suggest (e.g. every player
  // the team has left was just received) -- explain instead of waiting.
  const stuck =
    result?.key === key && result.odds != null && !result.odds.complete
      ? result.odds.teams.filter((t) => t.over_by > 0 && t.suggested_drops.length === 0)
      : [];

  useEffect(() => {
    let cancelled = false;
    const id = setTimeout(() => {
      const [a, b, as, bs, d] = JSON.parse(key) as [string, string, string[], string[], Record<string, string[]> | null];
      getTradeOdds({ password, team_a: a, team_b: b, a_sends: as, b_sends: bs, ...(d ? { drops: d } : {}), auto_release: false })
        .then((res) => {
          if (cancelled) return;
          setResult({ key, odds: res, error: null });
          if (res.complete) setShown(res);
          else
            for (const side of res.teams) {
              if (side.over_by > 0 && side.suggested_drops.length > 0) onSuggestedDrops?.(side.team, side.suggested_drops);
            }
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
                  : "Couldn't load win probabilities. Try again in a moment.",
          }));
        });
    }, DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(id);
    };
    // onSuggestedDrops is a fresh closure each render; the request only
    // depends on the trade itself.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, password, onRejected]);

  if (stuck.length > 0) return <OverLimitMessage teams={stuck.map((t) => ({ team: t.team, overBy: t.over_by }))} />;
  if (error && !odds) return <p className="text-sm text-muted-foreground">{error}</p>;
  const traded = aSends.length > 0 || bSends.length > 0;

  return (
    <LoadingOverlay active={loading} hasContent={odds != null} label="Calculating win probabilities">
      {odds && (
        <div className="flex flex-col gap-4">
          {error && <p className="text-sm text-loss">{error}</p>}
          <div className="grid gap-6 sm:grid-cols-2">
            {odds.teams.map((side) => (
              <TeamOdds key={side.team} side={side} categories={odds.categories} traded={traded} format={format} />
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

function TeamOdds({
  side,
  categories,
  traded,
  format,
}: {
  side: TradeOddsSide;
  categories: TradeOdds["categories"];
  traded: boolean;
  format: SeasonFormat;
}) {
  const short = side.active_after < side.active_before;
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-col gap-1.5">
        <span className="font-semibold">{side.team}</span>
        <HeadlineOdds
          format={format}
          startWin={side.start_matchup_win}
          startCats={side.start}
          after={traded ? { win: side.matchup_win, cats: side.after } : undefined}
        />
      </div>
      <CategoryOddsBars categories={categories} strongest={[]} before={side.start} after={traded ? side.after : undefined} />
      {(side.drops.length > 0 || short) && (
        <p className="text-xs text-muted-foreground">
          {side.drops.length > 0 &&
            (side.auto_drop
              ? `${side.team} releases ${side.drops.join(" and ")} to make room (the player it would miss least). `
              : `${side.team} drops ${side.drops.join(" and ")}. `)}
          {short && `${side.team} is left with an open roster spot; add a free agent to the other side's list to fill it.`}
        </p>
      )}
    </div>
  );
}
