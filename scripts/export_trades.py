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
Proposer = the team that offered it, when known).

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
from shared.atomic_write import atomic_write  # noqa: E402
from shared.runtime_config import REF_DIR  # noqa: E402

TRADES_PATH = REF_DIR / "trades.csv"
COLUMNS = ["Year", "Platform", "TradeId", "Date", "Proposer", "Partner", "ProposerGives", "PartnerGives"]
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
                    found[key] = (f"{root}:{day}", accept, items)
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
        })

    names = _espn_player_names(s, year, player_ids) if player_ids else {}
    for row in rows:
        row["ProposerGives"] = "; ".join(names.get(p, str(p)) for p in row.pop("_proposer_ids"))
        row["PartnerGives"] = "; ".join(names.get(p, str(p)) for p in row.pop("_partner_ids"))
    return rows


def yahoo_trades(year: int) -> list[dict]:
    from yfpy_fr.query import YahooFantasySportsQuery

    q = YahooFantasySportsQuery("", str(yLeagueIDs[year]), "nba", yGameIDs[year], False, False, yKey, ySec)
    teams = yTeamIDs[year]

    def member(team_key: str) -> str:
        return teams.get(int(str(team_key).rsplit(".t.", 1)[-1]), "")

    rows = []
    for t in q.get_league_transactions():
        if t.type != "trade" or t.status != "successful":
            continue
        proposer, partner = member(t.trader_team_key), member(t.tradee_team_key)
        gives: dict[str, list[str]] = {proposer: [], partner: []}
        for p in t.players or []:
            gives.setdefault(member(p.transaction_data.source_team_key), []).append(p.name.full)
        when = datetime.datetime.fromtimestamp(int(t.timestamp), EASTERN).date().isoformat() if t.timestamp else ""
        rows.append({
            "Year": year, "Platform": "Yahoo", "TradeId": str(t.transaction_key), "Date": when,
            "Proposer": proposer, "Partner": partner,
            "ProposerGives": "; ".join(gives[proposer]), "PartnerGives": "; ".join(gives[partner]),
        })
    return rows


def season_trades(year: int) -> list[dict]:
    return espn_trades(year) if seasonInfoDict[year]["is_espn"] else yahoo_trades(year)


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
