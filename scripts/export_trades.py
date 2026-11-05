"""Every completed trade in league history -> Ref/trades.csv, for the Career
section's Trade Log page (user request 2026-11-04; completed trades only).

ESPN seasons (2019-2023, 2027+): ESPN's transaction log (view=mTransactions2,
one request per scoring period -- the filter header returns nothing for these
leagues). A completed trade is a TRADE_ACCEPT with status EXECUTED (checked
against 2019's day-by-day rosters: the players really moved). Accepted
trades that were vetoed or never processed aren't included.

Yahoo seasons (2024-2026): every successful trade in Yahoo's transaction
list.

Writes Ref/trades.csv:
  Year, Platform, TradeId, Date, Proposer, Partner, ProposerGives, PartnerGives
(Date = when the trade went through, ET YYYY-MM-DD; players joined with "; ";
Proposer = the team that offered it, when known). A trade reversed within a
day (same two teams, same players swapped back) is dropped along with its
reversal -- it doesn't count (user decision 2026-11-04).

Some completed ESPN trades (most of 2020, much of 2021) have no player list
left in any record. Those are rebuilt from ESPN's day-by-day rosters: players
who went straight from one fantasy team to another around the trade's day,
both ways (draft -> day 1 for pre-season trades). Three 2020 trades (days 78
and 108) show no such roster change and are left out. For rebuilt trades the
offering team isn't known; Proposer is just one of the two sides.

Past seasons never change, so the stat-updater re-exports only the current
season (hourly, daytime cycle) and keeps every other year's rows:
  python3 -m scripts.export_trades              # every season
  python3 -m scripts.export_trades --year 2027
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from constants import (  # noqa: E402
    currentYear,
    espnLeagueIDs,
    espn_s2,
    espn_swid,
    espnTeamIDs,
    seasonInfoDict,
    yGameIDs,
    yKey,
    yLeagueIDs,
    ySec,
    yTeamIDs,
)
from shared import trade_value as tv  # noqa: E402
from shared.atomic_write import atomic_write  # noqa: E402
from shared.runtime_config import REF_DIR  # noqa: E402

TRADES_PATH = REF_DIR / "trades.csv"
COLUMNS = ["Year", "Platform", "TradeId", "Date", "Proposer", "Partner", "ProposerGives", "PartnerGives",
           "ProposerValue", "PartnerValue", "Winner", "ProposerWinsAdded", "PartnerWinsAdded",
           "TopPlayer", "TopPlayerTeam", "TopPlayerWinsAdded", "ValueDetail"]
# ESPN lineup slots that don't score.
ESPN_BENCH_SLOTS = {12, 13}  # BE, IR
BENCH_SLOT_NAMES = {"BE", "IR"}
EASTERN = ZoneInfo("America/New_York")
ESPN_BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{year}"
ESPN_LEAGUE = ESPN_BASE + "/segments/0/leagues/{league}"


def _date(ms) -> str:
    if not ms:
        return ""
    return datetime.datetime.fromtimestamp(ms / 1000, EASTERN).date().isoformat()


def _session():
    import requests  # stat-updater venv only; tests stub this out

    s = requests.Session()
    s.cookies.update({"espn_s2": espn_s2, "SWID": espn_swid})
    return s


def _espn_trade_records(s, year: int) -> list[dict]:
    """Every TRADE_* record of the season, de-duplicated by id."""
    url = ESPN_LEAGUE.format(year=year, league=espnLeagueIDs[year])
    status = s.get(url, params={"view": "mStatus"}, timeout=30).json().get("status", {})
    last = int(status.get("latestScoringPeriod") or status.get("finalScoringPeriod") or 200)
    records: dict[str, dict] = {}
    for sp in range(0, last + 1):
        r = s.get(url, params={"view": "mTransactions2", "scoringPeriodId": sp}, timeout=30)
        r.raise_for_status()
        for t in r.json().get("transactions") or []:
            if str(t.get("type", "")).startswith("TRADE"):
                records[t["id"]] = t
    return list(records.values())


def _espn_roster(s, year: int, sp: int) -> dict[int, int]:
    """PlayerId -> fantasy team id on scoring period `sp` (ESPN keeps the
    day-by-day roster history, past seasons included)."""
    url = ESPN_LEAGUE.format(year=year, league=espnLeagueIDs[year])
    r = s.get(url, params={"view": "mRoster", "scoringPeriodId": sp}, timeout=30)
    r.raise_for_status()
    return {e["playerPoolEntry"]["player"]["id"]: team["id"]
            for team in r.json().get("teams", []) for e in team.get("roster", {}).get("entries", [])}


def _espn_draft(s, year: int) -> dict[int, int]:
    """PlayerId -> fantasy team id that drafted him."""
    url = ESPN_LEAGUE.format(year=year, league=espnLeagueIDs[year])
    r = s.get(url, params={"view": "mDraftDetail"}, timeout=30)
    r.raise_for_status()
    return {p["playerId"]: p["teamId"] for p in r.json().get("draftDetail", {}).get("picks", [])}


def _espn_roster_slots(s, year: int, sp: int) -> dict[int, tuple[int, bool]]:
    """PlayerId -> (fantasy team id, in the active lineup) on scoring period sp."""
    url = ESPN_LEAGUE.format(year=year, league=espnLeagueIDs[year])
    r = s.get(url, params={"view": "mRoster", "scoringPeriodId": sp}, timeout=30)
    r.raise_for_status()
    return {e["playerPoolEntry"]["player"]["id"]: (team["id"], e.get("lineupSlotId") not in ESPN_BENCH_SLOTS)
            for team in r.json().get("teams", []) for e in team.get("roster", {}).get("entries", [])}


def _trades_from_rosters(before: dict[int, int], after: dict[int, int], teams: dict) -> list[list[dict]]:
    """Players who went straight from one fantasy team to another between two
    days, grouped into one trade per pair of teams (as trade items)."""
    by_pair: dict[frozenset, list[dict]] = {}
    for pid, frm in before.items():
        to = after.get(pid)
        if to is not None and to != frm and frm in teams and to in teams:
            by_pair.setdefault(frozenset((frm, to)), []).append(
                {"type": "TRADE", "fromTeamId": frm, "toTeamId": to, "playerId": pid})
    # A real trade moves players both ways.
    return [items for items in by_pair.values() if len({i["fromTeamId"] for i in items}) == 2]


def _espn_player_names(s, year: int, ids: set[int]) -> dict[int, str]:
    names: dict[int, str] = {}
    ids = sorted(ids)
    for i in range(0, len(ids), 200):
        chunk = ids[i:i + 200]
        r = s.get(ESPN_BASE.format(year=year) + "/players", params={"view": "players_wl"},
                  headers={"x-fantasy-filter": json.dumps({"filterIds": {"value": chunk}})}, timeout=30)
        r.raise_for_status()
        names.update({p["id"]: p["fullName"] for p in r.json()})
    return names


REBUILD_DAYS_AFTER = 3  # a trade can sit in review for a day or two before it executes


def _rebuild_from_rosters(s, year: int, teams: dict, missing: dict[int, list[tuple[str, dict]]],
                          known: list[tuple[str, dict, list[dict]]]) -> list[tuple[str, dict, list[dict]]]:
    """Completed trades ESPN kept no player list for: day-to-day roster
    changes around each one's day (draft -> day 1 for pre-season trades)
    where players went straight from one fantasy team to another, both ways.
    One trade per (pair of teams, day); moves already covered by a trade with
    a player list are skipped, and a trade spotted from two nearby accepts
    (ESPN sometimes logs two) counts once."""
    rosters: dict[int, dict[int, int]] = {}

    def roster(day: int) -> dict[int, int]:
        if day not in rosters:
            rosters[day] = _espn_draft(s, year) if day == 0 else _espn_roster(s, year, day)
        return rosters[day]

    claimed = {(i["playerId"], i["fromTeamId"], i["toTeamId"]) for _, _, items in known for i in items}
    found: dict[tuple[frozenset, int], tuple[str, dict, list[dict]]] = {}
    for sp, accepts in sorted(missing.items()):
        before = max(sp - 1, 0)  # day 0 = the draft (day 0's own rosters are pre-draft)
        for day in range(before, sp + REBUILD_DAYS_AFTER):
            for items in _trades_from_rosters(roster(day), roster(day + 1), teams):
                if any((i["playerId"], i["fromTeamId"], i["toTeamId"]) in claimed for i in items):
                    continue
                key = (frozenset(i["fromTeamId"] for i in items), day)
                if key not in found:
                    root, accept = accepts[min(len(found), len(accepts) - 1)]
                    found[key] = (f"{root}:{day}", {**accept, "_sp": day + 1}, items)
                    claimed |= {(i["playerId"], i["fromTeamId"], i["toTeamId"]) for i in items}
    print(f"trades {year}: {sum(len(a) for a in missing.values())} executed accept(s) without players "
          f"-> {len(found)} trade(s) rebuilt from rosters", file=sys.stderr)
    return list(found.values())


def espn_trades(year: int) -> list[dict]:
    s = _session()
    records = _espn_trade_records(s, year)
    teams = espnTeamIDs[year]
    by_id = {t["id"]: t for t in records}

    def trade_items(t: dict) -> list[dict]:
        # Team-to-team player moves only (a trade can also drop a player to
        # free agency -- team id 0 -- to make roster room; not part of the deal).
        return [i for i in (t.get("items") or [])
                if i.get("type") == "TRADE" and i.get("fromTeamId") in teams and i.get("toTeamId") in teams]

    # A trade's records share a root id: the original proposal (its teamId =
    # the team that offered it), referenced by each accept's
    # relatedTransactionId. Completed = any accept with status EXECUTED.
    chains: dict[str, list[dict]] = {}
    for t in records:
        chains.setdefault(t.get("relatedTransactionId") or t["id"], []).append(t)
    executed: dict[str, dict] = {}
    for root, chain in chains.items():
        accept = next((t for t in chain if t["type"] == "TRADE_ACCEPT" and t.get("status") == "EXECUTED"), None)
        if accept is not None:
            executed[root] = accept

    # The executed accept often carries no player list; its sibling accept or
    # the proposal does. When none of them do (most of 2020), the players are
    # rebuilt from the rosters the day before vs. the day after.
    trades: list[tuple[str, dict, list[dict]]] = []
    missing: dict[int, list[tuple[str, dict]]] = {}
    for root, accept in executed.items():
        sources = [accept, *(t for t in chains[root] if t is not accept), by_id.get(root) or {}]
        items = next((trade_items(t) for t in sources if trade_items(t)), [])
        if items:
            trades.append((root, accept, items))
        else:
            missing.setdefault(int(accept.get("scoringPeriodId") or 0), []).append((root, accept))
    if missing:
        trades += _rebuild_from_rosters(s, year, teams, missing, trades)

    rows = []
    player_ids: set[int] = set()
    for root, accept, items in trades:
        player_ids |= {i["playerId"] for i in items}
        proposer_id = (by_id.get(root) or {}).get("teamId")
        if proposer_id not in teams:
            proposer_id = items[0]["fromTeamId"]
        partner_ids = sorted(({i["toTeamId"] for i in items} | {i["fromTeamId"] for i in items}) - {proposer_id})
        rows.append({
            "Year": year, "Platform": "ESPN", "TradeId": root,
            "Date": _date(accept.get("processDate") or accept.get("proposedDate")),
            "Proposer": teams[proposer_id], "Partner": "; ".join(teams[p] for p in partner_ids),
            "_proposer_ids": [i["playerId"] for i in items if i["fromTeamId"] == proposer_id],
            "_partner_ids": [i["playerId"] for i in items if i["fromTeamId"] != proposer_id],
            # For the trade's value: the scoring period it went through.
            "_sp": int(accept.get("_sp") or accept.get("scoringPeriodId") or 0),
        })

    names = _espn_player_names(s, year, player_ids) if player_ids else {}
    for row in rows:
        gave_a, gave_b = row.pop("_proposer_ids"), row.pop("_partner_ids")
        row["ProposerGives"] = "; ".join(names.get(p, str(p)) for p in gave_a)
        row["PartnerGives"] = "; ".join(names.get(p, str(p)) for p in gave_b)
        row["_got"] = {row["Proposer"]: [(names.get(p, str(p)), p) for p in gave_b],
                       row["Partner"]: [(names.get(p, str(p)), p) for p in gave_a]}
    _add_espn_values(s, year, rows)
    return rows


def yahoo_trades(year: int) -> list[dict]:
    from yfpy_fr.query import YahooFantasySportsQuery

    q = YahooFantasySportsQuery("", str(yLeagueIDs[year]), "nba", yGameIDs[year], False, False, yKey, ySec)
    teams = yTeamIDs[year]

    def member(team_key) -> str:
        # No team key = a free agent / waiver move.
        tail = str(team_key or "").rsplit(".t.", 1)[-1]
        return teams.get(int(tail), "") if tail.isdigit() else ""

    def day(ts) -> datetime.date:
        return datetime.datetime.fromtimestamp(int(ts), EASTERN).date()

    txs = [t for t in q.get_league_transactions() if t.status == "successful" and t.timestamp]
    rows = []
    for t in txs:
        if t.type != "trade":
            continue
        proposer, partner = member(t.trader_team_key), member(t.tradee_team_key)
        gives: dict[str, list[str]] = {proposer: [], partner: []}
        for p in t.players or []:
            gives.setdefault(member(p.transaction_data.source_team_key), []).append(p.name.full)
        # Each received player's stay on his new team ends at the first later
        # move off it (drop or trade away) -- Yahoo has no day-by-day rosters.
        got = {proposer: gives[partner], partner: gives[proposer]}
        left: dict[tuple[str, str], datetime.date] = {}
        for team, names in got.items():
            for name in names:
                later = [u for u in txs if int(u.timestamp) > int(t.timestamp) and any(
                    p.name.full == name and member(p.transaction_data.source_team_key) == team for p in u.players or [])]
                if later:
                    left[(team, name)] = day(min(int(u.timestamp) for u in later))
        rows.append({
            "Year": year, "Platform": "Yahoo", "TradeId": str(t.transaction_key), "Date": day(t.timestamp).isoformat(),
            "Proposer": proposer, "Partner": partner,
            "ProposerGives": "; ".join(gives[proposer]), "PartnerGives": "; ".join(gives[partner]),
            "_got": {team: [(n, None) for n in names] for team, names in got.items()},
            "_left": left,
        })
    _add_yahoo_values(year, rows)
    return rows


# ---------------------------------------------------------------------------
# Who won: value each side received (shared/trade_value.py)
# ---------------------------------------------------------------------------


def _opening(year: int) -> datetime.date:
    """Week 1's start = ESPN scoring period 1 (opening night)."""
    cal = pd.read_csv(REF_DIR / "week_calendar.csv")
    return datetime.date.fromisoformat(str(cal[(cal["Year"] == year) & (cal["Week"] == 1)]["StartDate"].iloc[0]))


def _sp(year: int, d: datetime.date) -> int:
    return (d - _opening(year)).days + 1


def _season_games(year: int) -> tuple[pd.DataFrame, dict[str, list[int]]]:
    """One season's per-game logs (PlayerId, ScoringPeriod, COMP, MIN) and a
    normalized-name -> PlayerIds map. The current season reads the daily
    exports; past seasons ESPN's public player endpoint (any season 2019+,
    the same source as scripts/export_espn_public_season.py)."""
    from scripts.export_espn_public_season import COMP, EXTRA, STATS, URL, norm

    if year == currentYear:
        games = pd.read_csv(REF_DIR / "player_game_logs.csv")
        people = pd.read_csv(REF_DIR / "player_stats.csv")[["PlayerId", "Player"]].drop_duplicates()
        names = list(zip(people["Player"], people["PlayerId"]))
    else:
        import requests

        r = requests.get(URL.format(year=year), params={"scoringPeriodId": 0, "view": "kona_player_info"},
                         headers={"X-Fantasy-Filter": json.dumps({"players": {"limit": 5000}})}, timeout=180)
        r.raise_for_status()
        rows, names = [], []
        for p in r.json():
            names.append((p.get("fullName", ""), p["id"]))
            for st in p.get("stats") or []:
                vals = st.get("stats") or {}
                if (st.get("seasonId") == year and st.get("statSourceId") == 0
                        and st.get("statSplitTypeId") == 5 and vals.get("42") == 1):
                    rows.append({"PlayerId": p["id"], "ScoringPeriod": int(st["scoringPeriodId"]),
                                 **{c: float(vals.get(k, 0.0)) for k, c in STATS.items()},
                                 **{c: float(vals.get(k, 0.0)) for k, c in EXTRA.items()}})
        games = pd.DataFrame(rows, columns=["PlayerId", "ScoringPeriod"] + COMP + list(EXTRA.values()))
    played = set(games["PlayerId"])
    by_name: dict[str, list[int]] = {}
    for name, pid in names:
        by_name.setdefault(norm(name), []).append(int(pid))
    # Same name twice (rare): the one who actually played this season first.
    by_name = {k: sorted(set(v), key=lambda i: i not in played) for k, v in by_name.items()}
    return games, by_name


class SeasonWeeks:
    """A season's real matchups (Ref/<year>_CompStats.csv, real games only)
    and the scoring period -> matchup week map (Ref/week_calendar.csv)."""

    def __init__(self, year: int):
        cal = pd.read_csv(REF_DIR / "week_calendar.csv")
        cal = cal[cal["Year"] == year]
        self.opening = _opening(year)
        self.spans = [(datetime.date.fromisoformat(str(r.StartDate)), datetime.date.fromisoformat(str(r.EndDate)),
                       int(r.Week)) for r in cal.itertuples()]
        comp = pd.read_csv(REF_DIR / f"{year}_CompStats.csv")
        comp = comp[comp["Count"].astype(str).str.lower().eq("true") & ~comp["Opp"].isin(["BYE", ""])]
        self.rows = {(r["Team"], int(r["Week"])): r for r in comp.to_dict(orient="records")}

    def week(self, sp: int) -> int | None:
        d = self.opening + datetime.timedelta(days=int(sp) - 1)
        return next((w for start, end, w in self.spans if start <= d <= end), None)

    def matchups(self, team: str, active: pd.DataFrame) -> list[tuple[dict, dict, dict]]:
        """(team week, opponent week, player's totals that week) for every
        real matchup week the player's active games fall in."""
        if active.empty:
            return []
        g = active.copy()
        g["Week"] = [self.week(sp) for sp in (g.index if "ScoringPeriod" not in g else g["ScoringPeriod"])]
        out = []
        for week, wk in g.dropna(subset=["Week"]).groupby("Week"):
            own = self.rows.get((team, int(week)))
            if own is None or (own["Opp"], int(week)) not in self.rows:
                continue
            opp = self.rows[(own["Opp"], int(week))]
            out.append((tv.week_line(own), tv.week_line(opp), wk[tv.COMP].sum().to_dict()))
        return out


def _finish_values(row: dict, counted: dict[str, list[tuple[str, pd.DataFrame, pd.DataFrame]]], scale: dict,
                   weeks: SeasonWeeks) -> None:
    """Fill the value/winner/wins columns from each received player's games
    ({team: [(player, games while on the team, games in its active lineup)]})."""
    detail, side, side_wins = [], {}, {}
    for team, players in counted.items():
        total = wins_total = 0.0
        for name, g, active in players:
            v = tv.stretch_value(g[tv.COMP].sum(), scale)
            w, cw = tv.wins_added(weeks.matchups(team, active))
            total += v
            wins_total += w
            detail.append({"player": name, "team": team, "games": int(len(g)), "value": round(v, 1),
                           "wins_added": round(w, 2), "cat_wins_added": round(cw, 2)})
        side[team], side_wins[team] = total, wins_total
    a, b = row["Proposer"], row["Partner"]
    row["ProposerValue"], row["PartnerValue"] = round(side.get(a, 0.0), 1), round(side.get(b, 0.0), 1)
    row["Winner"] = tv.winner(a, side.get(a, 0.0), b, side.get(b, 0.0))
    row["ProposerWinsAdded"], row["PartnerWinsAdded"] = round(side_wins.get(a, 0.0), 2), round(side_wins.get(b, 0.0), 2)
    # The player who added the most wins to his new team (category wins as
    # the tiebreak); none if nobody added any.
    top = max(detail, key=lambda d: (d["wins_added"], d["cat_wins_added"]), default=None)
    if top and (top["wins_added"] > 0 or top["cat_wins_added"] > 0):
        row["TopPlayer"], row["TopPlayerTeam"], row["TopPlayerWinsAdded"] = top["player"], top["team"], top["wins_added"]
    else:
        row["TopPlayer"] = row["TopPlayerTeam"] = row["TopPlayerWinsAdded"] = ""
    row["ValueDetail"] = json.dumps(detail)


def _add_espn_values(s, year: int, rows: list[dict]) -> None:
    """ESPN seasons: a received player counts for his new team's games from
    the day after the trade while he's on its roster (ESPN's day-by-day
    rosters; this season's come from Ref/lineup_history.csv), stopping the
    first day he isn't."""
    if not rows:
        return
    games, _ = _season_games(year)
    scale = tv.season_scale(games)
    last = int(games["ScoringPeriod"].max())
    by_player = {pid: g.set_index("ScoringPeriod") for pid, g in games.groupby("PlayerId")}
    teams = espnTeamIDs[year]
    weeks = SeasonWeeks(year)
    # day -> PlayerId -> (fantasy team, in the active lineup)
    rosters: dict[int, dict[int, tuple[str, bool]]] = {}
    if year == currentYear and (REF_DIR / "lineup_history.csv").exists():
        lh = pd.read_csv(REF_DIR / "lineup_history.csv")
        for sp, g in lh[lh["Year"] == year].groupby("ScoringPeriod"):
            rosters[int(sp)] = {int(p): (t, slot not in BENCH_SLOT_NAMES)
                                for p, t, slot in zip(g["PlayerId"], g["FantasyTeam"], g["LineupSlot"])}

    def roster(day: int) -> dict[int, tuple[str, bool]]:
        if day not in rosters:
            rosters[day] = {pid: (teams.get(t, ""), act) for pid, (t, act) in _espn_roster_slots(s, year, day).items()}
        return rosters[day]

    empty = pd.DataFrame(columns=tv.COMP)
    for row in rows:
        start = row.pop("_sp")
        counted: dict[str, list[tuple[str, pd.DataFrame, pd.DataFrame]]] = {}
        for team, received in row.pop("_got").items():
            counted[team] = []
            for name, pid in received:
                days, active_days = [], []
                for day in range(start + 1, last + 1):
                    owner, active = roster(day).get(pid, ("", False))
                    if owner == team:
                        days.append(day)
                        if active:
                            active_days.append(day)
                    elif day > start + 1:  # one day's grace for the roster to catch up
                        break
                g = by_player.get(pid)
                stretch = g.loc[g.index.isin(days)] if g is not None else empty
                active = g.loc[g.index.isin(active_days)] if g is not None else empty
                counted[team].append((name, stretch, active))
        _finish_values(row, counted, scale, weeks)


def _add_yahoo_values(year: int, rows: list[dict]) -> None:
    """Yahoo seasons: a received player counts from the day after the trade
    until the day he left his new team (first later drop/trade away), else
    the season's end. Yahoo names are matched to ESPN's game logs by
    normalized name."""
    from scripts.export_espn_public_season import norm

    if not rows:
        return
    games, by_name = _season_games(year)
    scale = tv.season_scale(games)
    weeks = SeasonWeeks(year)
    by_player = {pid: g for pid, g in games.groupby("PlayerId")}
    for row in rows:
        start = _sp(year, datetime.date.fromisoformat(row["Date"]))
        left = row.pop("_left")
        counted: dict[str, list[tuple[str, pd.DataFrame, pd.DataFrame]]] = {}
        for team, received in row.pop("_got").items():
            counted[team] = []
            for name, _ in received:
                ids = by_name.get(norm(name), [])
                g = by_player.get(ids[0]) if ids else None
                if not ids:
                    print(f"trades {year}: no ESPN game logs matched for {name!r}", file=sys.stderr)
                end = _sp(year, left[(team, name)]) if (team, name) in left else 10_000
                stretch = (g[(g["ScoringPeriod"] > start) & (g["ScoringPeriod"] < end)]
                           if g is not None else pd.DataFrame(columns=tv.COMP))
                # No lineup history on Yahoo: every game on the roster counts.
                counted[team].append((name, stretch, stretch))
        _finish_values(row, counted, scale, weeks)


REVERSAL_MAX_DAYS = 1


def _sides(row: dict) -> dict[str, frozenset]:
    """Team -> players it gave (as a set) for one trade row."""
    return {row["Proposer"]: frozenset(p for p in row["ProposerGives"].split("; ") if p),
            row["Partner"]: frozenset(p for p in row["PartnerGives"].split("; ") if p)}


def drop_reversed(rows: list[dict]) -> list[dict]:
    """Drop a trade AND its reversal when the same two teams swap the exact
    same players back within REVERSAL_MAX_DAYS (user decision 2026-11-04:
    a trade undone within a day doesn't count). E.g. 2022: Gary Trent Jr.
    went Zahir -> Juan for Hamidou Diallo, and back the next day."""
    def day(row: dict) -> datetime.date | None:
        return datetime.date.fromisoformat(row["Date"]) if row["Date"] else None

    dropped: set[int] = set()
    for i, a in enumerate(rows):
        for j in range(i + 1, len(rows)):
            b = rows[j]
            if i in dropped or j in dropped or a["Year"] != b["Year"]:
                continue
            da, db = day(a), day(b)
            if da is None or db is None or abs((da - db).days) > REVERSAL_MAX_DAYS:
                continue
            sa, sb = _sides(a), _sides(b)
            if set(sa) != set(sb) or len(sa) != 2:
                continue
            t1, t2 = sorted(sa)
            # Reversal: what t1 gave in one is what t2 gave in the other.
            if sa[t1] == sb[t2] and sa[t2] == sb[t1]:
                dropped |= {i, j}
                print(f"trades {a['Year']}: dropped reversed trade {t1} <-> {t2} ({a['Date']}, {b['Date']})",
                      file=sys.stderr)
    return [r for k, r in enumerate(rows) if k not in dropped]


def season_trades(year: int) -> list[dict]:
    rows = espn_trades(year) if seasonInfoDict[year]["is_espn"] else yahoo_trades(year)
    return drop_reversed(rows)


def main(years: list[int] | None = None) -> pd.DataFrame:
    """Re-export `years` (default: every season) and keep the other years'
    stored rows."""
    years = years or sorted(seasonInfoDict)
    kept = pd.DataFrame(columns=COLUMNS)
    if TRADES_PATH.exists():
        kept = pd.read_csv(TRADES_PATH, dtype=str, keep_default_na=False)
        if list(kept.columns) != COLUMNS:  # older file layout -> rebuild every season
            kept, years = pd.DataFrame(columns=COLUMNS), sorted(seasonInfoDict)
        kept = kept[~kept["Year"].astype(int).isin(years)]
    fresh = [row for y in years for row in season_trades(y)]
    out = pd.concat([kept, pd.DataFrame(fresh, columns=COLUMNS)], ignore_index=True)
    out["Year"] = out["Year"].astype(int)
    out = out.sort_values(["Year", "Date"], ascending=[False, False], kind="stable")
    atomic_write(TRADES_PATH, lambda f: out[COLUMNS].to_csv(f, index=False))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, action="append", help="season(s) to re-export (default: all)")
    args = ap.parse_args()
    df = main(args.year)
    print(f"wrote {TRADES_PATH}: {len(df)} trades")
    print(df.groupby("Year").size().to_string())
