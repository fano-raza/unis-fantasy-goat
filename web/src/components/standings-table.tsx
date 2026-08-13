"use client";

import Link from "next/link";
import { ArrowDown, ArrowUp } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { StandingsRow } from "@/lib/api";

// Games Behind: leader's score minus this row's score, score = wins + 0.5*ties
// (the user's own explicit formula -- note this is a plain half-point, not
// the 0.49 tie-weight fudge factor used for ranking tiebreaks elsewhere in
// this app). Leader shows "-" (standard sports-table convention for GB=0).
function gamesBehind(rows: StandingsRow[]): Map<string, number> {
  const score = (r: StandingsRow) => r.wins + 0.5 * r.ties;
  const leaderScore = Math.max(...rows.map(score));
  return new Map(rows.map((r) => [r.team, leaderScore - score(r)]));
}

function formatGB(value: number): string {
  if (value === 0) return "-";
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

// team -> rank, for the prior-week movement arrows.
export function toRankMap(rows: StandingsRow[]): Map<string, number> {
  return new Map(rows.map((r) => [r.team, r.rank]));
}

export function StandingsTable({
  rows,
  previousRanks,
}: {
  rows: StandingsRow[];
  // Rank as of one week earlier than the current week-range selection --
  // when present and different, renders a green/red movement arrow next to
  // Place. Omitted (no arrows) when the selected range is a single week.
  previousRanks?: Map<string, number>;
}) {
  const gb = gamesBehind(rows);
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Place</TableHead>
          <TableHead>Team</TableHead>
          <TableHead className="text-right">Record</TableHead>
          <TableHead className="text-right">GB</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => {
          const previousRank = previousRanks?.get(row.team);
          return (
            <TableRow key={row.team}>
              <TableCell>
                <span className="inline-flex items-center gap-1">
                  {row.rank}
                  {previousRank != null &&
                    previousRank !== row.rank &&
                    (row.rank < previousRank ? (
                      <ArrowUp className="size-3 text-win" />
                    ) : (
                      <ArrowDown className="size-3 text-loss" />
                    ))}
                </span>
              </TableCell>
              <TableCell className="font-sans font-extrabold tracking-wide uppercase">
                <Link href={`/team/profile?team=${encodeURIComponent(row.team)}`} className="hover:underline">
                  {row.team}
                </Link>
              </TableCell>
              <TableCell className="text-right">
                {row.wins}-{row.losses}-{row.ties}
              </TableCell>
              <TableCell className="text-right">{formatGB(gb.get(row.team) ?? 0)}</TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
