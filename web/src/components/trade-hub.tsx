"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowLeftRight, Check, Crown, Plus, RotateCcw, X } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button, buttonVariants } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { LoadingOverlay } from "@/components/loading-overlay";
import { usePremium } from "@/components/premium";
import { TradeStatsComparison } from "@/components/trade-stats-table";
import { TradeWinChance } from "@/components/trade-win-chance";
import {
  ApiError,
  getPlayerStats,
  getRosterRanks,
  getTradeRecommendation,
  type LeagueMeta,
  type PlayerStat,
  type RosterRankRow,
  type TradeRecommendation,
} from "@/lib/api";
import { TRADE_SEARCH_PHRASES } from "@/lib/loading-phrases";
import { useSelectedTeam } from "@/lib/use-selected-team";
import { cn } from "@/lib/utils";

// Players each side can send (same cap the Trade Hub always had).
const TRADE_SIDE_CAP = 5;
// Select value for "no team" -- the side is then just a hand-picked group
// of players, like the old Team A / Team B comparison.
const NO_TEAM = "__none__";

type Side = "a" | "b";

/** Where a player is right now, for labels: "Rohil", "Free agent", "Rohil · IR". */
interface Owner {
  team: string | null;
  ir: boolean;
}

export function TradeHub({
  initialPlayers,
  meta,
}: {
  // Fetched server-side (see app/players/page.tsx); null -> client fetch.
  initialPlayers?: PlayerStat[] | null;
  meta: LeagueMeta | null;
}) {
  const premium = usePremium();
  const [players, setPlayers] = useState<PlayerStat[]>(initialPlayers ?? []);
  const [playersLoading, setPlayersLoading] = useState(!initialPlayers);
  const [rosterRows, setRosterRows] = useState<RosterRankRow[]>([]);
  // This season's teams (meta.members also lists past managers).
  const teams = useMemo(
    () => [...new Set(rosterRows.map((r) => r.FantasyTeam).filter((t): t is string => !!t))].sort(),
    [rosterRows],
  );

  const [remembered, setRemembered, hydrated] = useSelectedTeam(meta?.members[0] ?? "");
  const [teamA, setTeamA] = useState<string>(NO_TEAM);
  const [teamB, setTeamB] = useState<string>(NO_TEAM);
  const [sendA, setSendA] = useState<string[]>([]);
  const [sendB, setSendB] = useState<string[]>([]);

  // The last recommendation and the partner release it chose -- cleared as
  // soon as the user edits the trade (it no longer describes what's on screen).
  const [rec, setRec] = useState<TradeRecommendation | null>(null);
  const [recDrops, setRecDrops] = useState<Record<string, string[]> | null>(null);
  const [recommending, setRecommending] = useState(false);
  const [recError, setRecError] = useState<string | null>(null);
  const [recPicked, setRecPicked] = useState<string[]>([]);
  const [pickTeamOpen, setPickTeamOpen] = useState(false);

  useEffect(() => {
    if (initialPlayers) return;
    getPlayerStats()
      .then(setPlayers)
      .finally(() => setPlayersLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!meta) return;
    getRosterRanks({ year: meta.current_year }).then(setRosterRows).catch(() => setRosterRows([]));
  }, [meta]);

  // Side A opens on the team you last looked at elsewhere in the app
  // (remembered in localStorage, so only known after mount, and only valid
  // once this season's rosters are in).
  const rostersReady = teams.length > 0;
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (hydrated && rostersReady && teams.includes(remembered)) setTeamA((t) => (t === NO_TEAM ? remembered : t));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydrated, rostersReady]);

  const owners = useMemo(() => {
    const m = new Map<string, Owner>();
    for (const r of rosterRows) m.set(r.Player, { team: r.FantasyTeam || null, ir: r.LineupSlot === "IR" });
    return m;
  }, [rosterRows]);
  const rosterOf = (team: string) =>
    rosterRows.filter((r) => r.FantasyTeam === team).sort((x, y) => x.Rank - y.Rank);

  function edited() {
    setRec(null);
    setRecDrops(null);
    setRecError(null);
  }

  function setTeam(side: Side, team: string) {
    edited();
    if (side === "a") {
      setTeamA(team);
      setSendA([]);
      if (team !== NO_TEAM) setRemembered(team);
      if (team === teamB) {
        setTeamB(NO_TEAM);
        setSendB([]);
      }
    } else {
      setTeamB(team);
      setSendB([]);
      if (team === teamA) {
        setTeamA(NO_TEAM);
        setSendA([]);
      }
    }
  }

  function toggle(side: Side, name: string) {
    edited();
    const [list, set, other, setOther] = side === "a" ? [sendA, setSendA, sendB, setSendB] : [sendB, setSendB, sendA, setSendA];
    if (list.includes(name)) set(list.filter((n) => n !== name));
    else if (list.length < TRADE_SIDE_CAP) {
      set([...list, name]);
      // A player can only go one way.
      if (other.includes(name)) setOther(other.filter((n) => n !== name));
    }
  }

  async function recommend(forTeam: string) {
    if (!premium.password) return;
    setRecommending(true);
    setRecError(null);
    // Use the side-A players already picked from team A's own roster
    // (1 or 2) as the players to trade away; none -> search the roster.
    const own = new Set(rosterOf(forTeam).map((r) => r.Player));
    const picked = forTeam === teamA ? sendA.filter((n) => own.has(n)) : [];
    if (picked.length > 2) {
      setRecommending(false);
      setRecError("Pick 1 or 2 players to trade away, or none to search the whole roster.");
      return;
    }
    setRecPicked(picked);
    const partner = teamB !== NO_TEAM && teamB !== forTeam ? teamB : undefined;
    try {
      const res = await getTradeRecommendation({
        password: premium.password,
        team_a: forTeam,
        ...(partner ? { team_b: partner } : {}),
        ...(picked.length ? { give: picked } : {}),
      });
      setRec(res);
      if (res.trade) {
        setTeamA(forTeam);
        setRemembered(forTeam);
        setTeamB(res.trade.partner);
        setSendA(res.trade.give);
        // Side B's list is what team A receives -- including the free agent
        // who fills team A's open spot in a 2-for-1.
        setSendB([...res.trade.get, ...(res.trade.fa_add ? [res.trade.fa_add] : [])]);
        setRecDrops(res.trade.partner_drop ? { [res.trade.partner]: [res.trade.partner_drop] } : null);
      } else {
        setTeamA(forTeam);
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) premium.lock();
      else setRecError("Couldn't get a recommendation. Try again in a moment.");
    } finally {
      setRecommending(false);
    }
  }

  // Back to how the page opens: side A on the remembered team, side B
  // empty, nothing picked, no recommendation.
  const startTeamA = teams.includes(remembered) ? remembered : NO_TEAM;
  const isClear = teamA === startTeamA && teamB === NO_TEAM && sendA.length === 0 && sendB.length === 0 && !rec && !recError;
  function clearAll() {
    edited();
    setTeamA(startTeamA);
    setTeamB(NO_TEAM);
    setSendA([]);
    setSendB([]);
  }

  function onRecommendClick() {
    premium.requireUnlock(() => {
      if (teamA === NO_TEAM) setPickTeamOpen(true);
      else void recommend(teamA);
    });
  }

  const playersA = players.filter((p) => sendA.includes(p.Player));
  const playersB = players.filter((p) => sendB.includes(p.Player));
  const labelA = teamA !== NO_TEAM ? teamA : "Side A";
  const labelB = teamB !== NO_TEAM ? teamB : "Side B";
  const bothTeams = teamA !== NO_TEAM && teamB !== NO_TEAM;

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex flex-col gap-1">
            <CardTitle>Build a trade</CardTitle>
            <CardDescription>Pick each team, then tap players to send them to the other side.</CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" onClick={clearAll} disabled={isClear || recommending}>
              <RotateCcw className="size-4" aria-hidden />
              Clear
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={onRecommendClick}
              disabled={recommending || teams.length === 0}
              className="border-gold/60 text-gold hover:bg-gold/10 hover:text-gold"
            >
              <Crown className={premium.unlocked ? "size-4 fill-current" : "size-4"} aria-hidden />
              {recommending ? "Finding a trade…" : "Recommend trade"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {(rec || recError) && <RecommendationNote rec={rec} error={recError} picked={rec?.kind === "none" ? recPicked : []} />}
          <LoadingOverlay
            active={playersLoading || recommending}
            hasContent={players.length > 0}
            label={recommending ? "Finding a trade" : "Loading players"}
            phrases={recommending ? TRADE_SEARCH_PHRASES : undefined}
            intervalMs={recommending ? 1800 : undefined}
          >
            <div className="grid gap-4 md:grid-cols-[1fr_auto_1fr]">
              <TradeSide
                label="Side A"
                team={teamA}
                teams={teams}
                otherTeam={teamB}
                roster={teamA !== NO_TEAM ? rosterOf(teamA) : []}
                sending={sendA}
                players={players}
                owners={owners}
                onTeam={(t) => setTeam("a", t)}
                onToggle={(n) => toggle("a", n)}
              />
              <div className="hidden items-center justify-center md:flex" aria-hidden>
                <ArrowLeftRight className="size-5 text-muted-foreground" />
              </div>
              <TradeSide
                label="Side B"
                team={teamB}
                teams={teams}
                otherTeam={teamA}
                roster={teamB !== NO_TEAM ? rosterOf(teamB) : []}
                sending={sendB}
                players={players}
                owners={owners}
                onTeam={(t) => setTeam("b", t)}
                onToggle={(n) => toggle("b", n)}
              />
            </div>
          </LoadingOverlay>
        </CardContent>
      </Card>

      {(playersA.length > 0 || playersB.length > 0) && (
        <TradeStatsComparison playersA={playersA} playersB={playersB} labelA={`${labelA} sends`} labelB={`${labelB} sends`} />
      )}

      <TradeWinChance
        teamA={bothTeams ? teamA : null}
        teamB={bothTeams ? teamB : null}
        aSends={sendA}
        bSends={sendB}
        drops={recDrops}
        format={meta ? (meta.season_format[String(meta.current_year)] ?? "wl") : "wl"}
      />

      <Dialog open={pickTeamOpen} onOpenChange={setPickTeamOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Recommend a trade for…</DialogTitle>
            <DialogDescription>
              {teamB !== NO_TEAM
                ? `Searches trades with ${teamB}.`
                : "Searches trades with every team in the league. This can take up to 20 seconds the first time today."}
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-2">
            {teams
              .filter((t) => t !== teamB)
              .map((t) => (
                <Button
                  key={t}
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setPickTeamOpen(false);
                    setTeam("a", t);
                    void recommend(t);
                  }}
                >
                  {t}
                </Button>
              ))}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function RecommendationNote({
  rec,
  error,
  picked,
}: {
  rec: TradeRecommendation | null;
  error: string | null;
  // Players the search was limited to (team A's picks), if any.
  picked: string[];
}) {
  if (error) return <p className="rounded-md border border-loss/40 bg-loss/10 px-3 py-2 text-sm text-loss">{error}</p>;
  if (!rec) return null;
  const where = rec.team_b ? ` with ${rec.team_b}` : "";
  let text: string;
  if (rec.kind === "none" || !rec.trade) {
    const sending = picked.length ? ` that sends ${picked.join(" and ")}` : "";
    text = `No trade${where}${sending} helps ${rec.team_a} by at least 1 percentage point right now.${
      picked.length ? " Clear your picks to search the whole roster." : ""
    }`;
  } else if (rec.kind === "fair") {
    text = `Fair trade: ${rec.team_a} and ${rec.trade.partner} both come out ahead.`;
  } else {
    text = rec.team_b
      ? `No trade with ${rec.team_b} helps both teams. This one still helps ${rec.team_a} and costs ${rec.team_b} the least.`
      : `No trade in the league helps both teams. This one still helps ${rec.team_a} and costs ${rec.trade.partner} the least.`;
  }
  const extra =
    rec.trade?.fa_add || rec.trade?.partner_drop
      ? [
          rec.trade.fa_add && `${rec.team_a} picks up free agent ${rec.trade.fa_add} for the open spot`,
          rec.trade.partner_drop && `${rec.trade.partner} releases ${rec.trade.partner_drop} to make room`,
        ]
          .filter(Boolean)
          .join("; ") + "."
      : null;
  return (
    <div
      className={cn(
        "rounded-md border px-3 py-2 text-sm",
        rec.kind === "fair" ? "border-win/40 bg-win/10" : rec.kind === "none" ? "border-border bg-muted/40" : "border-gold/40 bg-gold/10",
      )}
      role="status"
    >
      <p className="font-medium">{text}</p>
      {extra && <p className="mt-0.5 text-muted-foreground">{extra}</p>}
    </div>
  );
}

function TradeSide({
  label,
  team,
  teams,
  otherTeam,
  roster,
  sending,
  players,
  owners,
  onTeam,
  onToggle,
}: {
  label: string;
  team: string;
  teams: string[];
  otherTeam: string;
  roster: RosterRankRow[];
  sending: string[];
  players: PlayerStat[];
  owners: Map<string, Owner>;
  onTeam: (team: string) => void;
  onToggle: (name: string) => void;
}) {
  const full = sending.length >= TRADE_SIDE_CAP;
  const options = [{ value: NO_TEAM, label: "No team (any players)" }, ...teams.filter((t) => t !== otherTeam).map((t) => ({ value: t, label: t }))];
  const ownNames = new Set(roster.map((r) => r.Player));
  // Picked players who aren't on this side's own roster (free agents, other
  // teams' players): listed as chips above the roster.
  const extras = sending.filter((n) => !ownNames.has(n));

  return (
    <section className="flex min-w-0 flex-col gap-3" aria-label={label}>
      <div className="flex items-center gap-2">
        <span className="label w-14 shrink-0">{label}</span>
        <Select value={team} onValueChange={(v) => v !== null && onTeam(v)}>
          <SelectTrigger size="sm" className="min-w-0 flex-1">
            <SelectValue>{(v: string) => options.find((o) => o.value === v)?.label ?? v}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            {options.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="font-medium">
          {team !== NO_TEAM ? `${team} sends` : "Sends"}{" "}
          <span className="tabular-nums text-muted-foreground">
            {sending.length}/{TRADE_SIDE_CAP}
          </span>
        </span>
        <AnyPlayerPicker players={players} owners={owners} exclude={sending} disabled={full} onPick={onToggle} />
      </div>

      {extras.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {extras.map((n) => (
            <li key={n} className="flex items-center gap-1.5 rounded-sm bg-secondary py-1 pr-1.5 pl-2.5 text-xs font-semibold text-secondary-foreground">
              {n}
              <span className="font-normal text-muted-foreground">{ownerLabel(owners.get(n))}</span>
              <button type="button" onClick={() => onToggle(n)} className="text-muted-foreground hover:text-foreground" aria-label={`Remove ${n}`}>
                <X className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}

      {team !== NO_TEAM ? (
        roster.length > 0 ? (
          <ul className="flex flex-col divide-y divide-border rounded-md border border-border">
            {roster.map((r) => {
              const on = sending.includes(r.Player);
              const ir = r.LineupSlot === "IR";
              return (
                <li key={r.Player}>
                  <button
                    type="button"
                    role="checkbox"
                    aria-checked={on}
                    disabled={!on && full}
                    onClick={() => onToggle(r.Player)}
                    className={cn(
                      "flex w-full items-center gap-3 px-3 py-2 text-left text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ring disabled:opacity-50",
                      on ? "bg-primary/10" : "hover:bg-muted/60",
                    )}
                  >
                    <span
                      className={cn(
                        "flex size-4 shrink-0 items-center justify-center rounded-[4px] border",
                        on ? "border-primary bg-primary text-primary-foreground" : "border-muted-foreground/50",
                      )}
                      aria-hidden
                    >
                      {on && <Check className="size-3" strokeWidth={3} />}
                    </span>
                    <span className={cn("min-w-0 flex-1 truncate", on && "font-semibold", ir && "text-muted-foreground")}>{r.Player}</span>
                    {ir && <span className="rounded-sm bg-muted px-1.5 text-[11px] font-semibold text-muted-foreground">IR</span>}
                    <span className="w-9 text-xs text-muted-foreground">{r.NBATeam}</span>
                    <span className="w-10 text-right text-xs tabular-nums text-muted-foreground">#{r.Rank}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">Loading {team}&apos;s roster…</p>
        )
      ) : (
        <p className="rounded-md border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
          Choose a team to pick from its roster, or add any player.
        </p>
      )}
    </section>
  );
}

function ownerLabel(o: Owner | undefined): string {
  if (!o || !o.team) return "Free agent";
  return o.ir ? `${o.team} · IR` : o.team;
}

function AnyPlayerPicker({
  players,
  owners,
  exclude,
  disabled,
  onPick,
}: {
  players: PlayerStat[];
  owners: Map<string, Owner>;
  exclude: string[];
  disabled: boolean;
  onPick: (name: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const remaining = useMemo(() => players.filter((p) => !exclude.includes(p.Player)), [players, exclude]);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger className={buttonVariants({ variant: "outline", size: "sm" })} disabled={disabled}>
        <Plus className="size-3.5" aria-hidden />
        Add any player
      </PopoverTrigger>
      <PopoverContent className="w-72 p-0" align="end">
        <Command>
          <CommandInput placeholder="Search any NBA player…" />
          <CommandList>
            <CommandEmpty>No players found.</CommandEmpty>
            <CommandGroup>
              {remaining.map((p) => (
                <CommandItem
                  key={p.PlayerId}
                  value={p.Player}
                  onSelect={() => {
                    onPick(p.Player);
                    setOpen(false);
                  }}
                >
                  <span className="flex-1 truncate">{p.Player}</span>
                  <span className="ml-2 text-xs text-muted-foreground">{ownerLabel(owners.get(p.Player))}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
