"use client";

import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LabeledSelect } from "@/components/labeled-select";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { Star } from "lucide-react";
import { getLeagueMeta, getTrades, type LeagueMeta, type TradeRow } from "@/lib/api";
import { cn } from "@/lib/utils";

const ALL = "__all__";

// "2026-11-03" -> "11/03/2026" (no Date parsing, so no timezone shift).
function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${m}/${d}/${y}`;
}

// A season is named by the year it ends: 2025 -> "24/25".
const seasonLabel = (year: number) => `${String(year - 1).slice(-2)}/${String(year).slice(-2)}`;

// What one team got in a trade: the other side's players, each with the
// games he played for this team afterwards (when values are known).
function Got({ trade, team }: { trade: TradeRow; team: string }) {
  const names = team === trade.proposer ? trade.partner_gives : trade.proposer_gives;
  if (names.length === 0) return <span className="text-muted-foreground">—</span>;
  // `?? []`: a cached response from before values existed has no players.
  const info = new Map((trade.players ?? []).filter((p) => p.team === team).map((p) => [p.player, p]));
  return (
    <ul className="flex flex-col gap-1">
      {names.map((n) => {
        const p = info.get(n);
        const top = trade.top_player === n && trade.top_player_team === team;
        return (
          <li key={n} className="flex items-start justify-between gap-3">
            <span className="min-w-0">
              <span className={cn(top && "font-semibold text-gold")}>{n}</span>
              {top && <Star className="ml-1 inline size-3 fill-current align-[-1px] text-gold" aria-label="Added the most wins" />}
              {p && (
                <span className="block text-xs text-muted-foreground tabular-nums">
                  {p.games} {p.games === 1 ? "game" : "games"}
                </span>
              )}
            </span>
            {p?.wins_added != null && (
              <span className="flex shrink-0 gap-2 pt-0.5 text-xs tabular-nums">
                <Delta value={p.wins_added} unit="W" title="Matchup wins added" />
                {p.cat_wins_added != null && <Delta value={p.cat_wins_added} unit="C" title="Category wins added" />}
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

const winsOf = (t: TradeRow, team: string) => (team === t.proposer ? t.proposer_wins_added : t.partner_wins_added);

// A player's wins added, e.g. "+1.3 W" / "−2.0 C": green up, red down.
function Delta({ value, unit, title }: { value: number; unit: string; title: string }) {
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return (
    <span
      title={title}
      className={cn("text-right font-semibold", value > 0 ? "text-win" : value < 0 ? "text-loss" : "text-muted-foreground")}
    >
      {sign}
      {Math.abs(value).toFixed(1)}
      <span className="ml-0.5 font-normal text-muted-foreground">{unit}</span>
    </span>
  );
}

// "+1.5 wins" / "−1 win" / "0 wins" (matchup wins).
function wins(x: number): string {
  const n = Number.isInteger(x) ? String(Math.abs(x)) : Math.abs(x).toFixed(1);
  const sign = x > 0 ? "+" : x < 0 ? "−" : "";
  return `${sign}${n} ${Math.abs(x) === 1 ? "win" : "wins"}`;
}

// Team name, marked when it won the trade, with the value it got.
function TeamSide({ trade, team }: { trade: TradeRow; team: string }) {
  const added = winsOf(trade, team);
  const won = trade.winner === team;
  return (
    <div className="flex flex-col gap-0.5">
      <span className="flex items-center gap-1.5">
        <span className="team-name">{team}</span>
        {won && <span className="rounded-sm bg-win/15 px-1 py-0.5 text-[10px] font-bold text-win">WON</span>}
      </span>
      {added != null && <span className="text-xs text-muted-foreground tabular-nums">{wins(added)}</span>}
    </div>
  );
}

/**
 * Career > Trade Log: every completed trade in league history, newest
 * first, filterable by season and team.
 */
export function TradeLog({
  initialMeta,
  initialTrades,
}: {
  initialMeta: LeagueMeta | null;
  initialTrades: TradeRow[] | null;
}) {
  const [meta, setMeta] = useState<LeagueMeta | null>(initialMeta);
  const [trades, setTrades] = useState<TradeRow[] | null>(initialTrades);
  const [error, setError] = useState<string | null>(null);
  const [season, setSeason] = useState(ALL);
  const [team, setTeam] = useState(ALL);

  // Client fallback when the server render couldn't reach the API.
  useEffect(() => {
    if (meta && trades) return;
    let cancelled = false;
    Promise.all([meta ? Promise.resolve(meta) : getLeagueMeta(), trades ? Promise.resolve(trades) : getTrades()])
      .then(([m, t]) => {
        if (cancelled) return;
        setMeta(m);
        setTrades(t);
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : "Couldn't load trades"));
    return () => {
      cancelled = true;
    };
  }, [meta, trades]);

  const filtered = useMemo(
    () =>
      (trades ?? []).filter(
        (t) =>
          (season === ALL || t.year === Number(season)) &&
          (team === ALL || t.proposer === team || t.partner.split("; ").includes(team)),
      ),
    [trades, season, team],
  );

  if (error) {
    return (
      <Card>
        <CardContent>
          <p className="text-sm text-muted-foreground">Couldn&apos;t load the trade log: {error}</p>
        </CardContent>
      </Card>
    );
  }
  if (!meta || !trades) return <LoadingBasketballs label="Loading trades" />;

  const years = [...new Set(trades.map((t) => t.year))].sort((a, b) => b - a);

  return (
    <div className="flex flex-col gap-4">
      <Card variant="plain">
        <CardContent className="flex flex-wrap items-center gap-6 max-sm:items-end max-sm:gap-4">
          <LabeledSelect
            stackOnMobile
            label="Season"
            value={season}
            onValueChange={setSeason}
            options={[{ value: ALL, label: "All" }, ...years.map((y) => ({ value: String(y), label: seasonLabel(y) }))]}
          />
          <LabeledSelect
            stackOnMobile
            label="Team"
            value={team}
            onValueChange={setTeam}
            options={[{ value: ALL, label: "All" }, ...meta.members.map((m) => ({ value: m, label: m }))]}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Trade Log</CardTitle>
          <CardDescription>
            {filtered.length} completed {filtered.length === 1 ? "trade" : "trades"} · W = matchup wins, C = category wins
          </CardDescription>
        </CardHeader>
        <CardContent>
          {filtered.length === 0 ? (
            <p className="text-sm text-muted-foreground">No trades match these filters.</p>
          ) : (
            <>
              {/* Desktop: one row per trade. */}
              <Table className="max-sm:hidden">
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead>Team</TableHead>
                    <TableHead>Got</TableHead>
                    <TableHead>Team</TableHead>
                    <TableHead>Got</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((t) => (
                    <TableRow key={`${t.year}-${t.id}`} className="align-top">
                      <TableCell className="whitespace-nowrap tabular-nums">
                        {formatDate(t.date)}
                        <span className="block text-xs text-muted-foreground">{seasonLabel(t.year)}</span>
                      </TableCell>
                      <TableCell>
                        <TeamSide trade={t} team={t.proposer} />
                      </TableCell>
                      <TableCell>
                        <Got trade={t} team={t.proposer} />
                      </TableCell>
                      <TableCell>
                        <TeamSide trade={t} team={t.partner} />
                      </TableCell>
                      <TableCell>
                        <Got trade={t} team={t.partner} />
                      </TableCell>

                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {/* Phones: each trade stacked, the two sides side by side. */}
              <ul className="flex flex-col divide-y divide-border sm:hidden">
                {filtered.map((t) => (
                  <li key={`${t.year}-${t.id}`} className="flex flex-col gap-2 py-3 first:pt-0">
                    <span className="flex items-center justify-between gap-2 text-xs text-muted-foreground tabular-nums">
                      <span>
                        {formatDate(t.date)} · {seasonLabel(t.year)}
                      </span>
                      {t.winner === "Even" && <span>Even</span>}
                    </span>
                    <div className="flex flex-col gap-3 text-sm">
                      {[t.proposer, t.partner].map((team) => (
                        <div key={team} className="flex flex-col gap-1">
                          <TeamSide trade={t} team={team} />
                          <span className="label">Got</span>
                          <Got trade={t} team={team} />
                        </div>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
