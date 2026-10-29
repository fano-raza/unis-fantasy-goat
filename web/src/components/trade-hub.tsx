"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowLeftRight, Crown, Plus, RotateCcw, TriangleAlert, Undo2, X } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
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
  type TradeOddsSide,
  type TradeRecommendation,
} from "@/lib/api";
import { expectedCategories, type SeasonFormat } from "@/components/headline-odds";
import { TRADE_SEARCH_PHRASES } from "@/lib/loading-phrases";
import { useSelectedTeam } from "@/lib/use-selected-team";
import { cn } from "@/lib/utils";

// Select value for "no team" -- the side is then just the players added to it.
const NO_TEAM = "__none__";

type Side = "a" | "b";

/** Where a player is right now, for labels: "Rohil", "Free agent", "Rohil · IR". */
interface Owner {
  team: string | null;
  ir: boolean;
}

/**
 * Trade Hub "Build a trade" (layout per the user, 2026-10-28): each side
 * shows its team's roster AFTER the trade. Clicking one of a team's players
 * trades him: crossed out on his side, added (highlighted) to the top of the
 * other side. "Add player" at the bottom of a roster adds any player to THAT
 * roster (a pickup, or a player from a third team). Drop releases a player.
 * Everything not crossed out and not on IR counts for that team's win
 * probability; a team left with too many players gets its least-missed
 * player auto-dropped (undoable), else a warning.
 */
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
  const format: SeasonFormat = meta ? (meta.season_format[String(meta.current_year)] ?? "wl") : "wl";

  const [remembered, setRemembered, hydrated] = useSelectedTeam(meta?.members[0] ?? "");
  const [teamA, setTeamA] = useState<string>(NO_TEAM);
  const [teamB, setTeamB] = useState<string>(NO_TEAM);
  // A team's own players it trades to the other side.
  const [tradeA, setTradeA] = useState<string[]>([]);
  const [tradeB, setTradeB] = useState<string[]>([]);
  // Players added to a team's roster with "Add player" (free agents or
  // players from a third team).
  const [addA, setAddA] = useState<string[]>([]);
  const [addB, setAddB] = useState<string[]>([]);
  // Players a team releases ("Drop"): off its roster, nobody gets them.
  const [dropA, setDropA] = useState<string[]>([]);
  const [dropB, setDropB] = useState<string[]>([]);
  // The subset of those drops made automatically because the team ended up
  // with too many players (the player it would miss least, suggested by the
  // server) -- shown as "Auto-dropped", undoable.
  const [autoA, setAutoA] = useState<string[]>([]);
  const [autoB, setAutoB] = useState<string[]>([]);
  // The user undid an auto-drop: leave the team over its limit (warning,
  // no win probability) instead of auto-dropping again, until the trade
  // itself changes.
  const [declinedA, setDeclinedA] = useState(false);
  const [declinedB, setDeclinedB] = useState(false);

  // The last recommendation -- cleared as soon as the user edits the trade
  // (it no longer describes what's on screen).
  const [rec, setRec] = useState<TradeRecommendation | null>(null);
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
    team === NO_TEAM ? [] : rosterRows.filter((r) => r.FantasyTeam === team).sort((x, y) => x.Rank - y.Rank);

  const S = {
    a: { team: teamA, trade: tradeA, setTrade: setTradeA, add: addA, setAdd: setAddA, drop: dropA, setDrop: setDropA, auto: autoA, setAuto: setAutoA, setDeclined: setDeclinedA },
    b: { team: teamB, trade: tradeB, setTrade: setTradeB, add: addB, setAdd: setAddB, drop: dropB, setDrop: setDropB, auto: autoB, setAuto: setAutoB, setDeclined: setDeclinedB },
  };
  const other = (side: Side): Side => (side === "a" ? "b" : "a");

  function edited() {
    setRec(null);
    setRecError(null);
  }

  // The trade's players changed: auto-drops were for the old trade -- undo
  // them (a new one is suggested if a team is still over) and forget any
  // declined auto-drop.
  function resetAutoDrops() {
    setDropA((d) => d.filter((n) => !autoA.includes(n)));
    setDropB((d) => d.filter((n) => !autoB.includes(n)));
    setAutoA([]);
    setAutoB([]);
    setDeclinedA(false);
    setDeclinedB(false);
  }

  function clearSide(side: Side) {
    S[side].setTrade([]);
    S[side].setAdd([]);
    S[side].setDrop([]);
    S[side].setAuto([]);
    S[side].setDeclined(false);
  }

  function setTeam(side: Side, team: string) {
    edited();
    resetAutoDrops();
    if (side === "a") {
      setTeamA(team);
      if (team !== NO_TEAM) setRemembered(team);
    } else setTeamB(team);
    clearSide(side);
    if (team === S[other(side)].team) {
      (side === "a" ? setTeamB : setTeamA)(NO_TEAM);
      clearSide(other(side));
    }
  }

  // Click one of a team's own players: trade him to the other side (or bring
  // him back). A traded player isn't also dropped.
  function toggleTrade(side: Side, name: string) {
    edited();
    resetAutoDrops();
    const s = S[side];
    if (s.trade.includes(name)) s.setTrade(s.trade.filter((n) => n !== name));
    else {
      s.setTrade([...s.trade, name]);
      if (s.drop.includes(name)) s.setDrop(s.drop.filter((n) => n !== name));
    }
  }

  // "Add player" on a side: the player joins THIS roster. A player from the
  // other side's roster is just a trade from that side.
  function addPlayer(side: Side, name: string) {
    edited();
    resetAutoDrops();
    const o = S[other(side)];
    if (o.team !== NO_TEAM && owners.get(name)?.team === o.team) {
      if (!o.trade.includes(name)) o.setTrade([...o.trade, name]);
      if (o.drop.includes(name)) o.setDrop(o.drop.filter((n) => n !== name));
      return;
    }
    const s = S[side];
    if (!s.add.includes(name)) s.setAdd([...s.add, name]);
    if (o.add.includes(name)) o.setAdd(o.add.filter((n) => n !== name));
  }

  function removeAdded(side: Side, name: string) {
    edited();
    resetAutoDrops();
    S[side].setAdd(S[side].add.filter((n) => n !== name));
  }

  function toggleDrop(side: Side, name: string) {
    edited();
    const s = S[side];
    if (s.drop.includes(name)) {
      s.setDrop(s.drop.filter((n) => n !== name));
      if (s.auto.includes(name)) {
        s.setAuto(s.auto.filter((n) => n !== name));
        s.setDeclined(true);
      }
    } else s.setDrop([...s.drop, name]);
  }

  async function recommend(forTeam: string) {
    if (!premium.password) return;
    setRecommending(true);
    setRecError(null);
    // Use the players already traded from team A (1 or 2) as the players to
    // trade away; none -> search the whole roster.
    const picked = forTeam === teamA ? tradeA : [];
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
        setTradeA(res.trade.give);
        setTradeB(res.trade.get);
        // The free agent who fills team A's open spot in a 2-for-1.
        setAddA(res.trade.fa_add ? [res.trade.fa_add] : []);
        setAddB([]);
        // The partner's release to make room shows as an auto-dropped row.
        setDropA([]);
        setDropB(res.trade.partner_drop ? [res.trade.partner_drop] : []);
        setAutoA([]);
        setAutoB(res.trade.partner_drop ? [res.trade.partner_drop] : []);
        setDeclinedA(false);
        setDeclinedB(false);
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
  // empty, nothing changed, no recommendation.
  const startTeamA = teams.includes(remembered) ? remembered : NO_TEAM;
  const isClear =
    teamA === startTeamA &&
    teamB === NO_TEAM &&
    tradeA.length + tradeB.length + addA.length + addB.length + dropA.length + dropB.length === 0 &&
    !rec &&
    !recError;
  function clearAll() {
    edited();
    setTeamA(startTeamA);
    setTeamB(NO_TEAM);
    clearSide("a");
    clearSide("b");
  }

  function onRecommendClick() {
    premium.requireUnlock(() => {
      if (teamA === NO_TEAM) setPickTeamOpen(true);
      else void recommend(teamA);
    });
  }

  // What each team gets: the other team's traded players + whoever was
  // added to its own roster. (In API terms, a_sends = everything going to
  // team B.)
  const toB = [...tradeA, ...addB];
  const toA = [...tradeB, ...addA];

  // How many players over its starting active roster each team ends up --
  // the same count the server uses: active (non-IR) players with stats this
  // season, minus who it trades away and drops, plus who it gets (players on
  // someone's IR or without stats don't count).
  const statNames = useMemo(() => new Set(players.map((p) => p.Player)), [players]);
  function overBy(team: string, leaves: string[], arrives: string[]): number {
    if (team === NO_TEAM) return 0;
    const active = new Set(
      rosterRows.filter((r) => r.FantasyTeam === team && r.LineupSlot !== "IR" && statNames.has(r.Player)).map((r) => r.Player),
    );
    const leaving = new Set(leaves.filter((n) => active.has(n)));
    const arriving = arrives.filter((n) => statNames.has(n) && !active.has(n) && !owners.get(n)?.ir);
    return Math.max(0, arriving.length - leaving.size);
  }
  const overA = overBy(teamA, [...tradeA, ...dropA], toA);
  const overB = overBy(teamB, [...tradeB, ...dropB], toB);

  // The win-probability panel found a team over its limit: drop the
  // player(s) the server suggests, visibly -- unless the user undid that.
  function applySuggestedDrops(team: string, names: string[]) {
    if (team === teamA && !declinedA) {
      setDropA((d) => [...d, ...names.filter((n) => !d.includes(n))]);
      setAutoA((a) => [...a, ...names.filter((n) => !a.includes(n))]);
    } else if (team === teamB && !declinedB) {
      setDropB((d) => [...d, ...names.filter((n) => !d.includes(n))]);
      setAutoB((a) => [...a, ...names.filter((n) => !a.includes(n))]);
    }
  }

  const playersToB = players.filter((p) => toB.includes(p.Player));
  const playersToA = players.filter((p) => toA.includes(p.Player));
  const labelA = teamA !== NO_TEAM ? teamA : "Side A";
  const labelB = teamB !== NO_TEAM ? teamB : "Side B";
  const bothTeams = teamA !== NO_TEAM && teamB !== NO_TEAM;

  const sideProps = (side: Side) => {
    const s = S[side];
    const o = S[other(side)];
    return {
      label: side === "a" ? "Side A" : "Side B",
      team: s.team,
      teams,
      otherTeam: o.team,
      roster: rosterOf(s.team),
      traded: s.trade,
      incoming: o.trade.map((n) => ({ name: n, from: o.team })),
      added: s.add,
      dropped: s.drop,
      autoDropped: s.auto,
      overBy: side === "a" ? overA : overB,
      // Unlocked premium resolves an over-size team with an auto-drop in a
      // moment; only warn when that won't happen.
      warn: (side === "a" ? overA : overB) > 0 && ((side === "a" ? declinedA : declinedB) || !premium.unlocked),
      players,
      owners,
      rosterRow: (name: string) => rosterRows.find((r) => r.Player === name),
      onTeam: (t: string) => setTeam(side, t),
      onTrade: (n: string) => toggleTrade(side, n),
      onUntradeIncoming: (n: string) => toggleTrade(other(side), n),
      onAdd: (n: string) => addPlayer(side, n),
      onRemoveAdded: (n: string) => removeAdded(side, n),
      onDrop: (n: string) => toggleDrop(side, n),
    };
  };

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex flex-col gap-1">
            <CardTitle>Build a trade</CardTitle>
            <CardDescription>
              Pick each team, then tap players to trade them. Each side shows its roster after the trade.
            </CardDescription>
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
          {(rec || recError) && (
            <RecommendationNote rec={rec} error={recError} picked={rec?.kind === "none" ? recPicked : []} format={format} />
          )}
          <LoadingOverlay
            active={playersLoading || recommending}
            hasContent={players.length > 0}
            label={recommending ? "Finding a trade" : "Loading players"}
            phrases={recommending ? TRADE_SEARCH_PHRASES : undefined}
            intervalMs={recommending ? 1800 : undefined}
          >
            {/* Two columns on phones too (user, 2026-10-28): compact rows
                below md -- "L. James", no NBA team/rank/tags. */}
            <div className="grid grid-cols-2 gap-2 md:grid-cols-[1fr_auto_1fr] md:gap-4">
              <TradeSide {...sideProps("a")} />
              <div className="hidden items-center justify-center md:flex" aria-hidden>
                <ArrowLeftRight className="size-5 text-muted-foreground" />
              </div>
              <TradeSide {...sideProps("b")} />
            </div>
          </LoadingOverlay>
        </CardContent>
      </Card>

      {(playersToB.length > 0 || playersToA.length > 0) && (
        <TradeStatsComparison playersA={playersToB} playersB={playersToA} labelA={`To ${labelB}`} labelB={`To ${labelA}`} />
      )}

      <TradeWinChance
        teamA={bothTeams ? teamA : null}
        teamB={bothTeams ? teamB : null}
        aSends={toB}
        bSends={toA}
        drops={bothTeams ? { [teamA]: dropA, [teamB]: dropB } : null}
        overLimit={[
          ...(overA > 0 && declinedA ? [{ team: teamA, overBy: overA }] : []),
          ...(overB > 0 && declinedB ? [{ team: teamB, overBy: overB }] : []),
        ]}
        onSuggestedDrops={applySuggestedDrops}
        format={format}
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

// A team's change in the headline number the win-probability panel shows:
// weekly matchup win probability (W/L) or expected categories won (Cats).
function shownChange(side: TradeOddsSide, format: SeasonFormat): number {
  return format === "cats" ? expectedCategories(side.after) - expectedCategories(side.start) : side.matchup_win - side.start_matchup_win;
}

function RecommendationNote({
  rec,
  error,
  picked,
  format,
}: {
  rec: TradeRecommendation | null;
  error: string | null;
  format: SeasonFormat;
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
    // Not "fair" means the partner doesn't gain at least 1 point on the
    // recommender's overall score -- but it may still gain a little, and
    // the panel below shows that. Word it by what the panel shows
    // (bug report 2026-10-28: "no trade helps both teams" next to both
    // teams' win probability going up).
    const partner = rec.odds?.teams[1];
    const change = partner != null ? shownChange(partner, format) : -1;
    const visible = format === "cats" ? 0.05 : 0.005;
    const where2 = rec.team_b ? `with ${rec.team_b}` : "in the league";
    text =
      change > visible
        ? `No trade ${where2} clearly helps both teams. This one helps ${rec.team_a} and only slightly helps ${rec.trade.partner}.`
        : change >= -visible
          ? `No trade ${where2} clearly helps both teams. This one helps ${rec.team_a} and leaves ${rec.trade.partner} about the same.`
          : `No trade ${where2} helps both teams. This one still helps ${rec.team_a} and costs ${rec.trade.partner} the least.`;
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
  traded,
  incoming,
  added,
  dropped,
  autoDropped,
  overBy,
  warn,
  players,
  owners,
  rosterRow,
  onTeam,
  onTrade,
  onUntradeIncoming,
  onAdd,
  onRemoveAdded,
  onDrop,
}: {
  label: string;
  team: string;
  teams: string[];
  otherTeam: string;
  // This team's current roster.
  roster: RosterRankRow[];
  // Its own players traded away (crossed out here, shown on the other side
  // in green at the top).
  traded: string[];
  // The other team's players traded to this team.
  incoming: { name: string; from: string }[];
  // Players added to this roster with "Add player".
  added: string[];
  dropped: string[];
  autoDropped: string[];
  overBy: number;
  warn: boolean;
  players: PlayerStat[];
  owners: Map<string, Owner>;
  rosterRow: (name: string) => RosterRankRow | undefined;
  onTeam: (team: string) => void;
  onTrade: (name: string) => void;
  onUntradeIncoming: (name: string) => void;
  onAdd: (name: string) => void;
  onRemoveAdded: (name: string) => void;
  onDrop: (name: string) => void;
}) {
  const options = [{ value: NO_TEAM, label: "Select team" }, ...teams.filter((t) => t !== otherTeam).map((t) => ({ value: t, label: t }))];
  const onRoster = new Set([...roster.map((r) => r.Player), ...incoming.map((i) => i.name), ...added]);
  const nbaTeamOf = (name: string) => {
    const r = rosterRow(name);
    if (r) return r.NBATeam;
    const p = players.find((x) => x.Player === name);
    return typeof p?.Team === "string" ? p.Team : "";
  };

  return (
    <section className="flex min-w-0 flex-col gap-2 md:gap-3" aria-label={team !== NO_TEAM ? team : label}>
      <div className="flex items-center gap-2">
        <span className="label hidden w-14 shrink-0 md:inline">{label}</span>
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
        {warn && (
          <span
            className="flex shrink-0 items-center gap-1 text-xs font-semibold text-gold"
            title={`${team} has ${overBy} too many player${overBy === 1 ? "" : "s"}: drop ${overBy === 1 ? "one" : overBy} to calculate the win probability`}
            role="img"
            aria-label={`${team} is ${overBy} over its roster limit`}
          >
            <TriangleAlert className="size-3.5" aria-hidden />
            <span className="hidden md:inline">{overBy} too many</span>
          </span>
        )}
      </div>

      <ul className="flex flex-col divide-y divide-border rounded-md border border-border">
        {incoming.map(({ name, from }) => {
          const r = rosterRow(name);
          return (
            <PlayerRow
              key={`in-${name}`}
              name={name}
              nbaTeam={nbaTeamOf(name)}
              rank={r?.Rank ?? null}
              tag={from !== NO_TEAM ? `From ${from}` : null}
              state="incoming"
              actionLabel={`Send ${name} back`}
              onClick={() => onUntradeIncoming(name)}
            />
          );
        })}
        {added.map((name) => {
          const o = owners.get(name);
          const r = rosterRow(name);
          return (
            <PlayerRow
              key={`add-${name}`}
              name={name}
              nbaTeam={nbaTeamOf(name)}
              rank={r?.Rank ?? null}
              tag={!o || !o.team ? "FA" : o.ir ? `${o.team} · IR` : `From ${o.team}`}
              state="incoming"
              actionLabel={`Remove ${name}`}
              onClick={() => onRemoveAdded(name)}
            />
          );
        })}
        {roster.map((r) => {
          const isTraded = traded.includes(r.Player);
          const isDropped = dropped.includes(r.Player);
          return (
            <PlayerRow
              key={r.Player}
              name={r.Player}
              nbaTeam={r.NBATeam}
              rank={r.Rank}
              tag={r.LineupSlot === "IR" ? "IR" : null}
              state={isTraded ? "traded" : isDropped ? (autoDropped.includes(r.Player) ? "autoDropped" : "dropped") : "kept"}
              actionLabel={isTraded ? `Keep ${r.Player}` : `Trade ${r.Player}`}
              onClick={() => onTrade(r.Player)}
              onDrop={isTraded ? undefined : () => onDrop(r.Player)}
            />
          );
        })}
        <li>
          <AddPlayerRow players={players} owners={owners} exclude={onRoster} onPick={onAdd} />
        </li>
      </ul>
    </section>
  );
}

type RowState = "kept" | "traded" | "dropped" | "autoDropped" | "incoming";

// "LeBron James" -> "L. James", "Jaren Jackson Jr." -> "J. Jackson Jr." --
// the compact phone layout.
function shortName(name: string): string {
  const parts = name.trim().split(/\s+/);
  return parts.length < 2 ? name : `${parts[0][0]}. ${parts.slice(1).join(" ")}`;
}

function PlayerRow({
  name,
  nbaTeam,
  rank,
  tag,
  state,
  actionLabel,
  onClick,
  onDrop,
}: {
  name: string;
  nbaTeam: string;
  rank: number | null;
  tag: string | null;
  state: RowState;
  actionLabel: string;
  onClick: () => void;
  // Omitted -> no drop button (traded or incoming players).
  onDrop?: () => void;
}) {
  const out = state === "traded" || state === "dropped" || state === "autoDropped";
  const dropped = state === "dropped" || state === "autoDropped";
  return (
    <li
      className={cn(
        "flex items-center",
        state === "incoming" && "bg-win/5",
        dropped && "bg-loss/5",
      )}
    >
      <button
        type="button"
        onClick={onClick}
        aria-label={actionLabel}
        title={actionLabel}
        className={cn(
          "flex min-w-0 flex-1 items-center gap-3 py-1.5 pl-2 text-left text-[13px] transition-colors focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ring md:py-2 md:pl-3 md:text-sm",
          state === "kept" && "hover:bg-muted/60",
          state === "incoming" && "hover:bg-win/10",
        )}
      >
        <span
          className={cn(
            "min-w-0 flex-1 truncate",
            state === "incoming" && "font-semibold",
            (out || tag === "IR") && "text-muted-foreground",
            out && "line-through",
          )}
        >
          <span className="hidden md:inline">{name}</span>
          <span className="md:hidden">{shortName(name)}</span>
        </span>
        {state === "traded" && (
          <span className="hidden rounded-sm bg-muted px-1.5 text-[11px] font-semibold text-muted-foreground md:inline">Traded</span>
        )}
        {dropped && (
          <span
            className="hidden rounded-sm bg-loss/15 px-1.5 text-[11px] font-semibold text-loss md:inline"
            title={state === "autoDropped" ? "Dropped to make room: the player this team would miss least. Undo to keep him." : undefined}
          >
            {state === "autoDropped" ? "Auto-dropped" : "Dropped"}
          </span>
        )}
        {tag && (
          <span
            className={cn(
              "hidden rounded-sm px-1.5 text-[11px] font-semibold md:inline",
              state === "incoming" ? "bg-win/15 text-win" : "bg-muted text-muted-foreground",
            )}
          >
            {tag}
          </span>
        )}
        <span className="hidden w-9 text-xs text-muted-foreground md:inline">{nbaTeam}</span>
        <span className="hidden w-10 text-right text-xs tabular-nums text-muted-foreground md:inline">{rank != null ? `#${rank}` : ""}</span>
      </button>
      {onDrop ? (
        <button
          type="button"
          onClick={onDrop}
          aria-label={dropped ? `Undo drop ${name}` : `Drop ${name}`}
          title={dropped ? "Undo drop" : "Drop"}
          className="mx-0.5 flex size-6 shrink-0 items-center justify-center rounded-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring md:mx-1 md:size-7"
        >
          {dropped ? <Undo2 className="size-3.5" aria-hidden /> : <X className="size-3.5" aria-hidden />}
        </button>
      ) : (
        <span className="mx-0.5 size-6 shrink-0 md:mx-1 md:size-7" aria-hidden />
      )}
    </li>
  );
}

function AddPlayerRow({
  players,
  owners,
  exclude,
  onPick,
}: {
  players: PlayerStat[];
  owners: Map<string, Owner>;
  exclude: Set<string>;
  onPick: (name: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const remaining = useMemo(() => players.filter((p) => !exclude.has(p.Player)), [players, exclude]);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger className="flex w-full items-center gap-2 px-2 py-1.5 text-left text-[13px] text-muted-foreground md:px-3 md:py-2 md:text-sm transition-colors hover:bg-muted/60 hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ring">
        <Plus className="size-4" aria-hidden />
        Add player
      </PopoverTrigger>
      <PopoverContent className="w-72 p-0" align="start">
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

function ownerLabel(o: Owner | undefined): string {
  if (!o || !o.team) return "Free agent";
  return o.ir ? `${o.team} · IR` : o.team;
}

