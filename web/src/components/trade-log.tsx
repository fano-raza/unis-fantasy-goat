"use client";

import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LabeledSelect } from "@/components/labeled-select";
import { LoadingBasketballs } from "@/components/loading-basketballs";
import { cn } from "@/lib/utils";
import {
  getLeagueMeta,
  getTrades,
  type LeagueMeta,
  type TradeRow,
  type TradeStatus,
  type TradesResponse,
} from "@/lib/api";

const ALL = "__all__";

const STATUS_ORDER: TradeStatus[] = ["Completed", "Pending", "Declined", "Canceled", "Vetoed", "Not processed", "Expired"];

const STATUS_STYLE: Record<TradeStatus, string> = {
  Completed: "bg-win/15 text-win",
  Pending: "bg-primary/15 text-primary",
  Declined: "bg-loss/15 text-loss",
  Vetoed: "bg-loss/15 text-loss",
  Canceled: "bg-muted text-muted-foreground",
  "Not processed": "bg-muted text-muted-foreground",
  Expired: "bg-muted text-muted-foreground",
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// "2026-11-03" -> "Nov 3, 2026" (no Date parsing, so no timezone shift).
function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-").map(Number);
  return `${MONTHS[m - 1]} ${d}, ${y}`;
}

// A trade's own date: when it was resolved, else when it was offered.
const tradeDate = (t: TradeRow) => t.resolved_date ?? t.proposed_date;

// "2024, 2025 and 2026" / "2024-2026" for a consecutive run.
function yearList(years: number[]): string {
  if (years.length === 0) return "";
  const consecutive = years.every((y, i) => i === 0 || y === years[i - 1] + 1);
  if (consecutive && years.length > 2) return `${years[0]}–${years[years.length - 1]}`;
  return years.length === 1 ? String(years[0]) : `${years.slice(0, -1).join(", ")} and ${years[years.length - 1]}`;
}

function StatusChip({ trade }: { trade: TradeRow }) {
  return (
    <span className={cn("inline-block rounded-sm px-1.5 py-0.5 text-xs font-semibold whitespace-nowrap", STATUS_STYLE[trade.status])}>
      {trade.status}
      {trade.veto_votes > 0 && (
        <span className="font-normal opacity-80">
          {" "}
          ({trade.veto_votes} veto {trade.veto_votes === 1 ? "vote" : "votes"})
        </span>
      )}
    </span>
  );
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

const MISSING_DETAILS = "ESPN didn't keep this offer's players";

export function TradeLog({
  initialMeta,
  initialTrades,
}: {
  initialMeta: LeagueMeta | null;
  initialTrades: TradesResponse | null;
}) {
  const [meta, setMeta] = useState<LeagueMeta | null>(initialMeta);
  const [data, setData] = useState<TradesResponse | null>(initialTrades);
  const [error, setError] = useState<string | null>(null);
  const [season, setSeason] = useState(ALL);
  const [team, setTeam] = useState(ALL);
  const [status, setStatus] = useState(ALL);

  // Client fallback when the server render couldn't reach the API.
  useEffect(() => {
    if (meta && data) return;
    let cancelled = false;
    Promise.all([meta ? Promise.resolve(meta) : getLeagueMeta(), data ? Promise.resolve(data) : getTrades()])
      .then(([m, t]) => {
        if (cancelled) return;
        setMeta(m);
        setData(t);
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : "Couldn't load trades"));
    return () => {
      cancelled = true;
    };
  }, [meta, data]);

  const trades = useMemo(() => data?.trades ?? [], [data]);

  const filtered = useMemo(
    () =>
      trades.filter(
        (t) =>
          (season === ALL || t.year === Number(season)) &&
          (status === ALL || t.status === status) &&
          (team === ALL || t.proposer === team || (t.partner ?? "").split("; ").includes(team)),
      ),
    [trades, season, team, status],
  );

  const counts = useMemo(() => {
    const c = new Map<TradeStatus, number>();
    for (const t of filtered) c.set(t.status, (c.get(t.status) ?? 0) + 1);
    return STATUS_ORDER.filter((s) => c.has(s)).map((s) => ({ status: s, n: c.get(s)! }));
  }, [filtered]);

  if (error) {
    return (
      <Card>
        <CardContent>
          <p className="text-sm text-muted-foreground">Couldn&apos;t load the trade log: {error}</p>
        </CardContent>
      </Card>
    );
  }
  if (!meta || !data) return <LoadingBasketballs label="Loading trades" />;

  const years = [...new Set(trades.map((t) => t.year))].sort((a, b) => b - a);
  const statuses = STATUS_ORDER.filter((s) => trades.some((t) => t.status === s));
  const yahooYears = data.no_rejected_data_years;
  const selectedYearHasNoRejected = season !== ALL && yahooYears.includes(Number(season));

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
          <LabeledSelect
            stackOnMobile
            label="Status"
            value={status}
            onValueChange={setStatus}
            options={[{ value: ALL, label: "All" }, ...statuses.map((s) => ({ value: s, label: s }))]}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Trade Log</CardTitle>
          <CardDescription>
            {filtered.length} {filtered.length === 1 ? "offer" : "offers"}
            {counts.length > 0 && <> · {counts.map((c) => `${c.n} ${c.status.toLowerCase()}`).join(" · ")}</>}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {selectedYearHasNoRejected && (
            <p className="rounded-md border border-gold/40 bg-gold/[0.06] p-3 text-sm">
              {season} was played on Yahoo, which only keeps completed trades. Declined and canceled offers from this
              season aren&apos;t available.
            </p>
          )}

          {filtered.length === 0 ? (
            <p className="text-sm text-muted-foreground">No trades match these filters.</p>
          ) : (
            <>
              {/* Desktop: one row per offer. */}
              <Table className="max-sm:hidden">
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead>Season</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Offered by</TableHead>
                    <TableHead>Gives</TableHead>
                    <TableHead>To</TableHead>
                    <TableHead>Gives</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((t) => (
                    <TableRow key={`${t.year}-${t.id}`} className="align-top">
                      <TableCell className="whitespace-nowrap tabular-nums">{formatDate(tradeDate(t))}</TableCell>
                      <TableCell className="tabular-nums">{t.year}</TableCell>
                      <TableCell>
                        <StatusChip trade={t} />
                      </TableCell>
                      {t.details_available ? (
                        <>
                          <TableCell className="team-name">{t.proposer}</TableCell>
                          <TableCell>
                            <Players names={t.proposer_gives} />
                          </TableCell>
                          <TableCell className="team-name">{t.partner}</TableCell>
                          <TableCell>
                            <Players names={t.partner_gives} />
                          </TableCell>
                        </>
                      ) : (
                        <>
                          <TableCell className="text-muted-foreground">—</TableCell>
                          <TableCell className="text-muted-foreground italic">{MISSING_DETAILS}</TableCell>
                          <TableCell className="team-name">{t.partner ?? "—"}</TableCell>
                          <TableCell className="text-muted-foreground">—</TableCell>
                        </>
                      )}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {/* Phones: each offer stacked, the two sides side by side. */}
              <ul className="flex flex-col divide-y divide-border sm:hidden">
                {filtered.map((t) => (
                  <li key={`${t.year}-${t.id}`} className="flex flex-col gap-2 py-3 first:pt-0">
                    <div className="flex items-center justify-between gap-2">
                      <StatusChip trade={t} />
                      <span className="text-xs text-muted-foreground tabular-nums">{formatDate(tradeDate(t))}</span>
                    </div>
                    {t.details_available ? (
                      <div className="grid grid-cols-2 gap-3 text-sm">
                        <div className="flex flex-col gap-1">
                          <span className="team-name">{t.proposer}</span>
                          <span className="label">Offered</span>
                          <Players names={t.proposer_gives} />
                        </div>
                        <div className="flex flex-col gap-1">
                          <span className="team-name">{t.partner}</span>
                          <span className="label">For</span>
                          <Players names={t.partner_gives} />
                        </div>
                      </div>
                    ) : (
                      <p className="text-sm">
                        <span className="text-muted-foreground">Offer to</span>{" "}
                        <span className="team-name">{t.partner ?? "—"}</span>
                        <span className="block text-muted-foreground italic">{MISSING_DETAILS}</span>
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}

          <div className="flex flex-col gap-1 text-xs text-muted-foreground">
            {yahooYears.length > 0 && (
              <p>
                {yearList(yahooYears)} {yahooYears.length === 1 ? "was" : "were"} played on Yahoo, which only keeps
                completed trades, so declined and canceled offers from {yahooYears.length === 1 ? "that season" : "those seasons"}{" "}
                aren&apos;t included.
              </p>
            )}
            <p>
              ESPN deletes most declined offers and only keeps who declined them, so many declined rows have no players.
              From the {meta.current_year} season on, offers are saved while they&apos;re still open, so most will keep
              their players.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
