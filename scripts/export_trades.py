"""Every trade offer in league history -> Ref/trades.csv, for the Trade Log
page (user request 2026-11-04: completed AND rejected trades, teams, players).

ESPN seasons (2019-2023, 2027+): ESPN's transaction log (view=mTransactions2,
one request per scoring period -- the filter header returns nothing for these
leagues). Each offer is a chain of records sharing a root id: the
TRADE_PROPOSAL, then TRADE_ACCEPT / TRADE_DECLINE / a cancelled copy of the
proposal, and TRADE_VETO / TRADE_UPHOLD votes. Outcome:
  Completed      an ACCEPT with status EXECUTED (checked against 2019's
                 day-by-day rosters: the players really moved)
  Vetoed         accepted, never executed, at least one veto vote
  Not processed  accepted, never executed, no veto votes
  Declined       a DECLINE record
  Canceled       the proposal was cancelled (proposer withdrew, or ESPN
                 voided it, e.g. a player in it was dropped)
  Pending        current season, still open
  Expired        no response, past season or past its expiration date
ESPN deletes the proposal itself for most declined offers, leaving only the
decline record (who declined, when). Those rows have DetailsAvailable=False
and no proposer/players. From the 2027 season on, every raw record seen is
kept in Ref/trade_records_<year>.json, so an offer seen while still pending
keeps its details after ESPN drops them -- the stat-updater runs a full scan
hourly (daytime cycle) and a quick scan of the last few days every 10 minutes
during game hours. An offer made and declined between two scans still loses
its details.

Yahoo seasons (2024-2026): Yahoo's API only returns completed trades, so
there are no rejected/cancelled offers for those years (HasRejectedData=False
on every Yahoo row; the page says so).

Writes Ref/trades.csv:
  Year, Platform, TradeId, ProposedDate, ResolvedDate, Status, Proposer,
  Partner, ProposerGives, PartnerGives, VetoVotes, DetailsAvailable,
  HasRejectedData
(dates are ET YYYY-MM-DD; players joined with "; ").

Past seasons never change, so the stat-updater re-exports only the current
season and keeps every other year's rows:
  python3 -m scripts.export_trades                       # every season
  python3 -m scripts.export_trades --year 2027
  python3 -m scripts.export_trades --year 2027 --recent-days 2   # quick scan
"""
from __future__ import annotations

import argparse
import collections
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
from shared.atomic_write import atomic_write  # noqa: E402
from shared.runtime_config import REF_DIR  # noqa: E402

TRADES_PATH = REF_DIR / "trades.csv"
COLUMNS = [
    "Year", "Platform", "TradeId", "ProposedDate", "ResolvedDate", "Status",
    "Proposer", "Partner", "ProposerGives", "PartnerGives", "VetoVotes",
    "DetailsAvailable", "HasRejectedData",
]
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


def _records_cache_path(year: int) -> Path:
    return REF_DIR / f"trade_records_{year}.json"


def _espn_trade_records(s, year: int, recent_days: int | None = None) -> list[dict]:
    """Every TRADE_* record of the season, de-duplicated by id. For the
    current season, merged into (and saved back to) the raw-record cache, so
    records ESPN later deletes -- a declined offer's proposal -- are kept.
    recent_days: only scan the last N scoring periods (+ today)."""
    url = ESPN_LEAGUE.format(year=year, league=espnLeagueIDs[year])
    status = s.get(url, params={"view": "mStatus"}, timeout=30).json().get("status", {})
    last = int(status.get("latestScoringPeriod") or status.get("finalScoringPeriod") or 200)
    first = max(0, last - recent_days) if recent_days else 0
    cache_path = _records_cache_path(year)
    use_cache = year >= currentYear
    records: dict[str, dict] = {}
    if use_cache and cache_path.exists():
        records = json.loads(cache_path.read_text())
    for sp in range(first, last + 1):
        r = s.get(url, params={"view": "mTransactions2", "scoringPeriodId": sp}, timeout=30)
        r.raise_for_status()
        for t in r.json().get("transactions") or []:
            if str(t.get("type", "")).startswith("TRADE"):
                records[t["id"]] = t  # latest version wins (status changes)
    if use_cache:
        atomic_write(cache_path, lambda f: json.dump(records, f))
    return list(records.values())


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


def espn_trades(year: int, today: datetime.date | None = None, recent_days: int | None = None) -> list[dict]:
    s = _session()
    records = _espn_trade_records(s, year, recent_days)
    teams = espnTeamIDs[year]
    today = today or datetime.datetime.now(EASTERN).date()

    chains: dict[str, list[dict]] = collections.defaultdict(list)
    for t in records:
        chains[t.get("relatedTransactionId") or t["id"]].append(t)

    def trade_items(t: dict) -> list[dict]:
        # Team-to-team player moves only (a trade can also drop a player to
        # free agency -- team id 0 -- to make roster room; not part of the deal).
        return [i for i in (t.get("items") or [])
                if i.get("type") == "TRADE" and i.get("fromTeamId") in teams and i.get("toTeamId") in teams]

    rows = []
    player_ids: set[int] = set()
    for root, chain in chains.items():
        by_type = collections.defaultdict(list)
        for t in chain:
            by_type[t["type"]].append(t)
        proposals = by_type["TRADE_PROPOSAL"]
        accepts = by_type["TRADE_ACCEPT"]
        # Items: the original proposal when ESPN still has it, else its
        # cancelled copy, else the accept record.
        source = next((t for t in sorted(proposals, key=lambda t: t["id"] != root) + accepts if trade_items(t)), None)
        items = trade_items(source) if source else []
        player_ids |= {i["playerId"] for i in items}
        root_proposal = next((t for t in proposals if t["id"] == root), None)
        proposer_id = (root_proposal or source or {}).get("teamId")
        if proposer_id not in teams and items:
            proposer_id = items[0]["fromTeamId"]

        vetoes = len(by_type["TRADE_VETO"])
        proposed = min((t.get("proposedDate") or 0 for t in chain if t["type"] == "TRADE_PROPOSAL"), default=0)
        if any(a.get("status") == "EXECUTED" for a in accepts):
            status = "Completed"
            resolved = max(a.get("processDate") or a.get("proposedDate") or 0 for a in accepts)
        elif accepts:
            status = "Vetoed" if vetoes else "Not processed"
            resolved = max(a.get("processDate") or a.get("proposedDate") or 0 for a in accepts)
        elif by_type["TRADE_DECLINE"]:
            status = "Declined"
            resolved = by_type["TRADE_DECLINE"][0].get("proposedDate")
        elif any(p.get("status") == "CANCELED" for p in proposals):
            status = "Canceled"
            resolved = max(p.get("proposedDate") or 0 for p in proposals if p.get("status") == "CANCELED")
        elif not proposals:
            continue  # stray vote with nothing to attach it to
        else:
            expires = max((p.get("expirationDate") or 0 for p in proposals), default=0)
            open_now = year == currentYear and (not expires or _date(expires) >= today.isoformat())
            status = "Pending" if open_now else "Expired"
            resolved = None if open_now else expires

        if items:
            proposer = teams[proposer_id]
            partner_ids = sorted(({i["toTeamId"] for i in items} | {i["fromTeamId"] for i in items}) - {proposer_id})
            partner = "; ".join(teams[p] for p in partner_ids)
            gives = {"proposer": [i["playerId"] for i in items if i["fromTeamId"] == proposer_id],
                     "partner": [i["playerId"] for i in items if i["fromTeamId"] != proposer_id]}
            details = True
        else:
            # Only the decline record survives: who declined, and when.
            decliner = (by_type["TRADE_DECLINE"] or chain)[0].get("teamId")
            proposer = ""
            partner = teams.get(decliner, "") if decliner in teams else ""
            gives = {"proposer": [], "partner": []}
            details = False

        rows.append({
            "Year": year, "Platform": "ESPN", "TradeId": root,
            "ProposedDate": _date(proposed), "ResolvedDate": _date(resolved),
            "Status": status, "Proposer": proposer, "Partner": partner,
            "_proposer_ids": gives["proposer"], "_partner_ids": gives["partner"],
            "VetoVotes": vetoes, "DetailsAvailable": details, "HasRejectedData": True,
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
        if t.type != "trade":
            continue
        proposer, partner = member(t.trader_team_key), member(t.tradee_team_key)
        gives: dict[str, list[str]] = {proposer: [], partner: []}
        for p in t.players or []:
            src = member(p.transaction_data.source_team_key)
            gives.setdefault(src, []).append(p.name.full)
        when = datetime.datetime.fromtimestamp(int(t.timestamp), EASTERN).date().isoformat() if t.timestamp else ""
        rows.append({
            "Year": year, "Platform": "Yahoo", "TradeId": str(t.transaction_key),
            # Yahoo only gives the completion time.
            "ProposedDate": "", "ResolvedDate": when,
            "Status": "Completed" if t.status == "successful" else str(t.status).title(),
            "Proposer": proposer, "Partner": partner,
            "ProposerGives": "; ".join(gives[proposer]), "PartnerGives": "; ".join(gives[partner]),
            "VetoVotes": 0, "DetailsAvailable": True, "HasRejectedData": False,
        })
    return rows


def season_trades(year: int, recent_days: int | None = None) -> list[dict]:
    return espn_trades(year, recent_days=recent_days) if seasonInfoDict[year]["is_espn"] else yahoo_trades(year)


def main(years: list[int] | None = None, recent_days: int | None = None) -> pd.DataFrame:
    """Re-export `years` (default: every season) and keep the other years'
    stored rows. recent_days: quick scan (ESPN current season only; the
    raw-record cache still supplies everything older)."""
    years = years or sorted(seasonInfoDict)
    kept = pd.DataFrame(columns=COLUMNS)
    if TRADES_PATH.exists():
        kept = pd.read_csv(TRADES_PATH, dtype=str, keep_default_na=False)
        kept = kept[~kept["Year"].astype(int).isin(years)]
    fresh = [row for y in years for row in season_trades(y, recent_days if y >= currentYear else None)]
    out = pd.concat([kept, pd.DataFrame(fresh, columns=COLUMNS)], ignore_index=True)
    out["Year"] = out["Year"].astype(int)
    out = out.sort_values(["Year", "ResolvedDate", "ProposedDate"], ascending=[False, False, False], kind="stable")
    atomic_write(TRADES_PATH, lambda f: out[COLUMNS].to_csv(f, index=False))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, action="append", help="season(s) to re-export (default: all)")
    ap.add_argument("--recent-days", type=int, help="current season: only scan the last N days")
    args = ap.parse_args()
    df = main(args.year, args.recent_days)
    print(f"wrote {TRADES_PATH}: {len(df)} rows")
    print(df.groupby(["Year", "Status"]).size().unstack(fill_value=0))
