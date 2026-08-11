import Link from "next/link";
import { Trophy } from "lucide-react";
import { cn } from "@/lib/utils";
import type { PlayoffBracket, PlayoffMatchup, PlayoffRound } from "@/lib/api";

type RoundItem =
  | { type: "matchup"; matchup: PlayoffMatchup }
  | { type: "bye"; team: string };

// Orders a round's boxes so a bye visually funnels into the next round's
// matchup it feeds into -- e.g. a 6-team bracket's Quarterfinals column
// should read (top to bottom): #1 seed's bye, the #4v#5 matchup (whichever
// of the two feeds #1's semifinal), the #3v#6 matchup, #2 seed's bye.
// Falls back to byes-then-matchups (in seed order) when there's no
// decided next round to group against yet (an in-progress bracket) or the
// bye/matchup counts don't line up 1:1 (never happens with this league's
// real data -- always 0 or 2 byes -- but shouldn't crash if it ever did).
function orderRoundItems(
  round: PlayoffRound,
  nextRound: PlayoffRound | undefined,
  seedByTeam: Record<string, number>,
): RoundItem[] {
  const byeItems: RoundItem[] = [...round.byes]
    .sort((a, b) => (seedByTeam[a] ?? Infinity) - (seedByTeam[b] ?? Infinity))
    .map((team) => ({ type: "bye", team }));
  const matchupItems: RoundItem[] = round.matchups.map((matchup) => ({ type: "matchup", matchup }));

  if (byeItems.length === 0) return matchupItems;
  if (!nextRound || nextRound.matchups.length === 0 || byeItems.length !== matchupItems.length) {
    return [...byeItems, ...matchupItems];
  }

  const nextSlotForTeam: Record<string, number> = {};
  nextRound.matchups.forEach((m, i) => {
    nextSlotForTeam[m.team1] = i;
    nextSlotForTeam[m.team2] = i;
  });

  const groups: Record<number, { bye?: string; matchup?: PlayoffMatchup }> = {};
  let ok = true;
  for (const item of byeItems) {
    const team = (item as { type: "bye"; team: string }).team;
    const slot = nextSlotForTeam[team];
    if (slot === undefined) { ok = false; break; }
    groups[slot] = { ...groups[slot], bye: team };
  }
  if (ok) {
    for (const item of matchupItems) {
      const m = (item as { type: "matchup"; matchup: PlayoffMatchup }).matchup;
      const slot = m.winner != null ? nextSlotForTeam[m.winner] : undefined;
      if (slot === undefined) { ok = false; break; }
      groups[slot] = { ...groups[slot], matchup: m };
    }
  }
  const slotIndices = Object.keys(groups).map(Number);
  if (!ok || slotIndices.length !== byeItems.length) {
    return [...byeItems, ...matchupItems];
  }

  slotIndices.sort((a, b) => {
    const seedA = groups[a].bye ? (seedByTeam[groups[a].bye!] ?? Infinity) : Infinity;
    const seedB = groups[b].bye ? (seedByTeam[groups[b].bye!] ?? Infinity) : Infinity;
    return seedA - seedB;
  });

  const result: RoundItem[] = [];
  slotIndices.forEach((slot, i) => {
    const g = groups[slot];
    const items: RoundItem[] = [];
    if (g.bye) items.push({ type: "bye", team: g.bye });
    if (g.matchup) items.push({ type: "matchup", matchup: g.matchup });
    // First-half groups: bye leads, funneling down into its matchup.
    // Second-half groups: matchup leads, funneling up into its bye.
    const isFirstHalf = i < slotIndices.length / 2;
    result.push(...(isFirstHalf ? items : [...items].reverse()));
  });
  return result;
}

function TeamLink({
  team,
  className,
}: {
  team: string;
  className?: string;
}) {
  return (
    <Link
      href={`/profile?team=${encodeURIComponent(team)}`}
      className={cn("hover:underline", className)}
    >
      {team}
    </Link>
  );
}

function MatchupBox({ matchup, muted }: { matchup: PlayoffMatchup; muted?: boolean }) {
  const rows: { team: string; seed: number | null; won: boolean }[] = [
    { team: matchup.team1, seed: matchup.seed1, won: matchup.winner === matchup.team1 },
    { team: matchup.team2, seed: matchup.seed2, won: matchup.winner === matchup.team2 },
  ];
  return (
    <div
      className={cn(
        "flex flex-col gap-1 rounded-sm border border-border bg-card px-3 py-2",
        muted && "opacity-80",
      )}
    >
      {matchup.slot && (
        <span className="text-[10px] font-bold tracking-wider text-muted-foreground uppercase">
          {matchup.slot}
        </span>
      )}
      {rows.map((row) => (
        <div
          key={row.team}
          className={cn(
            "flex items-center justify-between gap-3 text-xs font-bold tracking-wide uppercase",
            row.won ? "text-primary" : "text-muted-foreground",
          )}
        >
          <span className="flex items-center gap-1.5">
            {row.seed != null && (
              <span className="font-mono text-[10px] text-muted-foreground">#{row.seed}</span>
            )}
            <TeamLink team={row.team} />
            {row.won && matchup.slot === "Final" && (
              <Trophy className="size-3 text-amber-400" />
            )}
          </span>
          <span className="font-mono text-[10px] tabular-nums">
            {row.team === matchup.team1
              ? `${matchup.wins}-${matchup.losses}${matchup.ties ? `-${matchup.ties}` : ""}`
              : `${matchup.losses}-${matchup.wins}${matchup.ties ? `-${matchup.ties}` : ""}`}
          </span>
        </div>
      ))}
      {matchup.tiebreak_applied && (
        <span className="text-[10px] text-muted-foreground italic">
          Tiebreak: {matchup.tiebreak_reason}
        </span>
      )}
    </div>
  );
}

function ByeBox({ team }: { team: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-sm border border-dashed border-border px-3 py-2 text-xs font-bold tracking-wide text-muted-foreground uppercase">
      <TeamLink team={team} />
      <span className="text-[10px]">Bye</span>
    </div>
  );
}

export function PlayoffTree({ bracket, year }: { bracket: PlayoffBracket | undefined; year: number }) {
  if (!bracket) {
    return (
      <p className="text-sm text-muted-foreground">
        No playoff bracket data for {year}.
      </p>
    );
  }

  const seedByTeam: Record<string, number> = {};
  for (const [seed, team] of Object.entries(bracket.seeding)) {
    seedByTeam[team] = Number(seed);
  }

  return (
    <div className="flex flex-col gap-4">
      {bracket.champion && (
        <div className="flex items-center gap-2 text-sm font-bold tracking-wide uppercase">
          <Trophy className="size-4 text-amber-400" />
          <span className="text-muted-foreground">Champion:</span>
          <TeamLink team={bracket.champion} className="text-primary" />
        </div>
      )}
      <div className="flex gap-6 overflow-x-auto pb-2">
        {bracket.rounds.map((round, roundIdx) => {
          const items = orderRoundItems(round, bracket.rounds[roundIdx + 1], seedByTeam);
          return (
            <div key={round.week} className="flex min-w-[220px] flex-1 flex-col gap-3">
              <span className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase">
                {round.label}
              </span>
              <div className="flex h-full flex-col justify-around gap-3">
                {items.map((item, i) =>
                  item.type === "matchup" ? (
                    <MatchupBox
                      key={`${round.week}-m-${i}`}
                      matchup={item.matchup}
                      muted={item.matchup.slot === "3rd Place"}
                    />
                  ) : (
                    <ByeBox key={`${round.week}-b-${item.team}`} team={item.team} />
                  ),
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
