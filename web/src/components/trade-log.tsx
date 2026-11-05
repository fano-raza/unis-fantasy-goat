"use client";

import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LabeledSelect } from "@/components/labeled-select";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { getLeagueMeta, getTrades, type LeagueMeta, type TradeRow } from "@/lib/api";

const ALL = "__all__";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// "2026-11-03" -> "Nov 3, 2026" (no Date parsing, so no timezone shift).
function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-").map(Number);
  return `${MONTHS[m - 1]} ${d}, ${y}`;
}

function Players({ names }: { names: string[] }) {
  if (names.length === 0) return <span className="text-muted-foreground">—</span>;
  return (
    <ul className="flex flex-col gap-0.5">
      {names.map((n) => (
        <li key={n}>{n}</li>
      ))}
    </ul>
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
            options={[{ value: ALL, label: "All" }, ...years.map((y) => ({ value: String(y), label: String(y) }))]}
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
            {filtered.length} completed {filtered.length === 1 ? "trade" : "trades"}
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
                    <TableHead>Season</TableHead>
                    <TableHead>Team</TableHead>
                    <TableHead>Gave</TableHead>
                    <TableHead>Team</TableHead>
                    <TableHead>Gave</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((t) => (
                    <TableRow key={`${t.year}-${t.id}`} className="align-top">
                      <TableCell className="whitespace-nowrap tabular-nums">{formatDate(t.date)}</TableCell>
                      <TableCell className="tabular-nums">{t.year}</TableCell>
                      <TableCell className="team-name">{t.proposer}</TableCell>
                      <TableCell>
                        <Players names={t.proposer_gives} />
                      </TableCell>
                      <TableCell className="team-name">{t.partner}</TableCell>
                      <TableCell>
                        <Players names={t.partner_gives} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {/* Phones: each trade stacked, the two sides side by side. */}
              <ul className="flex flex-col divide-y divide-border sm:hidden">
                {filtered.map((t) => (
                  <li key={`${t.year}-${t.id}`} className="flex flex-col gap-2 py-3 first:pt-0">
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {formatDate(t.date)} · {t.year} season
                    </span>
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      <div className="flex flex-col gap-1">
                        <span className="team-name">{t.proposer}</span>
                        <span className="label">Gave</span>
                        <Players names={t.proposer_gives} />
                      </div>
                      <div className="flex flex-col gap-1">
                        <span className="team-name">{t.partner}</span>
                        <span className="label">Gave</span>
                        <Players names={t.partner_gives} />
                      </div>
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
