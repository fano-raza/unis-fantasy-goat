from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from constants import allMembers


DEFAULT_MAP_PATH = Path(__file__).resolve().parent / "discord_names.csv"


@dataclass(frozen=True)
class TeamMatch:
    team: Optional[str]
    source: str


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.strip().lower().split())


def _configured_map_path() -> Path:
    raw = os.getenv("DISCORD_USER_TEAM_MAP_CSV", "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_MAP_PATH


_CACHE: dict[str, object] = {
    "path": None,
    "mtime": None,
    "maps": ({}, {}),
}


def _load_maps() -> tuple[dict[str, str], dict[str, str]]:
    path = _configured_map_path()
    cache_path = _CACHE.get("path")
    cache_mtime = _CACHE.get("mtime")
    mtime = path.stat().st_mtime if path.exists() else None
    if cache_path == str(path) and cache_mtime == mtime:
        return _CACHE["maps"]  # type: ignore[return-value]

    by_user_id: dict[str, str] = {}
    by_name: dict[str, str] = {}

    if not path.exists():
        _CACHE["path"] = str(path)
        _CACHE["mtime"] = None
        _CACHE["maps"] = (by_user_id, by_name)
        return by_user_id, by_name

    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                team = (row.get("team") or "").strip()
                if team not in allMembers:
                    continue
                uid = (row.get("discord_user_id") or "").strip()
                dname = _normalize(row.get("discord_name"))
                if uid:
                    by_user_id[uid] = team
                if dname:
                    by_name[dname] = team
    except Exception:
        # Keep bot behavior safe if mapping file is malformed.
        return {}, {}

    _CACHE["path"] = str(path)
    _CACHE["mtime"] = mtime
    _CACHE["maps"] = (by_user_id, by_name)
    return by_user_id, by_name


def resolve_user_team(
    *,
    user_id: int | str | None,
    display_name: str | None,
    username: str | None,
) -> TeamMatch:
    by_user_id, by_name = _load_maps()

    uid = str(user_id).strip() if user_id is not None else ""
    if uid and uid in by_user_id:
        return TeamMatch(team=by_user_id[uid], source="csv:user_id")

    display_norm = _normalize(display_name)
    username_norm = _normalize(username)
    for name in (display_norm, username_norm):
        if name and name in by_name:
            return TeamMatch(team=by_name[name], source="csv:name")

    candidates = sorted(allMembers, key=len, reverse=True)
    joined = " ".join(filter(None, [display_norm, username_norm]))
    for team in candidates:
        if team.lower() in joined:
            return TeamMatch(team=team, source="auto:contains")

    return TeamMatch(team=None, source="none")
