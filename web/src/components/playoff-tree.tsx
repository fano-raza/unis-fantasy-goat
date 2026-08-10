import Link from "next/link";
import { Trophy } from "lucide-react";
import { cn } from "@/lib/utils";
import type { PlayoffBracket, PlayoffMatchup } from "@/lib/api";

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
        {bracket.rounds.map((round) => (
          <div key={round.week} className="flex min-w-[220px] flex-1 flex-col gap-3">
            <span className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase">
              {round.label}
            </span>
            <div className="flex h-full flex-col justify-around gap-3">
              {round.matchups.map((m, i) => (
                <MatchupBox key={`${round.week}-${i}`} matchup={m} muted={m.slot === "3rd Place"} />
              ))}
              {round.byes.map((team) => (
                <ByeBox key={team} team={team} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
