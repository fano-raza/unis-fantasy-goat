import json
import os
import math
from typing import Dict

import pandas as pd
import requests

# === Config ===

DISCORD_WEBHOOK_URL = os.getenv(
    "DISCORD_WEBHOOK_URL",
    "https://discord.com/api/webhooks/1442777568179785780/9Gh2uoE895-bbFJG4IIuqKd2w7zRBNMwFylxQOAsSfHR0sL11Z7EjTR3xykDmff-KHy-",
)
STATS_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1BTYpWILKa2xgUyB8VFvBxGFn9C5nxo1C0-2-QsJ7AD0/edit?gid=1346622527#gid=1346622527"
)

STATE_FILE = "milestone_state.json"


def _env_flag(name: str, default: bool = True) -> bool:
    raw = str(os.getenv(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}

# Milestone factors
# Per-category factors by stat name ("PTS", "REB", etc.)
# Example: FACTOR_BY_CATEGORY["PTS"] = 5000
DEFAULT_FACTOR = 1000
DEFAULT_BIG_FACTOR = 10000
FACTOR_BY_CATEGORY: Dict[str, int] = {
    "PTS": 10000,
    "REB": 1000,
    "AST": 1000,
    "STL": 500,
    "BLK": 500,
}
BIG_FACTOR_BY_CATEGORY: Dict[str, int] = {
    "PTS": 25000,
    "REB": 5000,
    "AST": 5000,
    "STL": 1000,
    "BLK": 1000,
}


# === State helpers ===

def _load_state() -> Dict[str, float]:
    """
    Generic key -> numeric value.
    Keys used:
      - MILESTONE|context|team|stat_name -> last [factor] milestone
      - RANK|context|team|stat_name      -> previous rank (1 = best)
      - VAL|context|team|stat_name       -> previous stat value
    """
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r") as f:
        return json.load(f)


def _save_state(state: Dict[str, float]) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def _is_missing(val) -> bool:
    """True for None / NaN / pandas missing."""
    return val is None or (isinstance(val, float) and math.isnan(val))


def _ordinal(n: int) -> str:
    """Turn 1 -> 1st, 2 -> 2nd, etc."""
    n = int(n)
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        last = n % 10
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(last, "th")
    return f"{n}{suffix}"


def _get_factor(stat_name: str) -> int:
    return FACTOR_BY_CATEGORY.get(stat_name, DEFAULT_FACTOR)


def _get_big_factor(stat_name: str) -> int:
    return BIG_FACTOR_BY_CATEGORY.get(stat_name, DEFAULT_BIG_FACTOR)


# === Core logic ===

def notify_milestones(dataframes: Dict[str, pd.DataFrame]) -> bool:
    """
    dataframes: dict mapping a context label -> DataFrame
      e.g. {"Career": career_df, "RS": rs_df, "PO": po_df}

    Each DataFrame must have:
      - column "Team"
      - one or more numeric stat columns (e.g. "PTS", "REB", etc)
      - for each stat column "PTS", a rank column "PTS_rank"
        where 1 = best (highest value).

    Behavior:
      1) Milestones:
         For each (context, team, stat), if the stat value has reached or
         surpassed a new multiple of the per-category factor since the last run, send:
           **Team** just reached **<milestone>** <context> <stat_name>!
         If that milestone is also a multiple of BIG_FACTOR (e.g. 25,000),
         send a special message with emojis + "BIG MILESTONE REACHED".

      2) Leaderboard moves:
         If a team's rank in a stat improves vs last run, and they have
         matched or overtaken a team that used to be ahead, send:
           [Team A] has [overtaken/tied] [Team B] in [context] [stat].
           They now sit at [Rank] place all time in [context] [stat].
    """
    if not _env_flag("DISCORD_ENABLE_MILESTONES", default=True):
        return False
    if not DISCORD_WEBHOOK_URL:
        return False

    state = _load_state()
    lines: list[str] = []

    # ---------- 1) Milestone alerts ----------
    for context, df in dataframes.items():
        if "Team" not in df.columns:
            continue

        # Stat columns are everything except "Team" and "*_rank"
        stat_cols = [
            col for col in df.columns
            if col != "Team" and not col.endswith("_rank")
        ]

        for _, row in df.iterrows():
            team_name = str(row["Team"])

            for stat_name in stat_cols:
                val = row[stat_name]
                if _is_missing(val):
                    continue

                try:
                    num_val = float(val)
                except (TypeError, ValueError):
                    continue

                if num_val <= 0:
                    continue

                factor = _get_factor(stat_name)
                big_factor = _get_big_factor(stat_name)

                # highest factor-multiple reached by this value
                new_milestone = int(num_val // factor) * factor
                if new_milestone <= 0:
                    continue

                m_key = f"MILESTONE|{context}|{team_name}|{stat_name}"
                last_milestone = int(state.get(m_key, 0))

                if new_milestone > last_milestone:
                    # inside: if new_milestone > last_milestone:

                    prev_big_tier = last_milestone // big_factor  # e.g. 0 if < 25k, 1 if 25k–49,999
                    curr_big_tier = new_milestone // big_factor

                    if curr_big_tier > prev_big_tier:
                        # They crossed at least one BIG_FACTOR threshold since last check
                        crossed_val = curr_big_tier * big_factor  # the highest BIG multiple they've now reached/passed
                        line = (
                            f"🎉🎉 **BIG MILESTONE REACHED** 🎉🎉\n"
                            f"**{team_name}** just reached **{new_milestone}** {context} {stat_name} "
                        )
                    else:
                        # regular milestone
                        line = (
                            f"**{team_name}** just reached "
                            f"**{new_milestone}** {context} {stat_name}!"
                        )
                    lines.append(line)
                    state[m_key] = new_milestone

    # ---------- 2) Leaderboard overtakes / ties ----------
    for context, df in dataframes.items():
        if "Team" not in df.columns:
            continue

        stat_cols = [
            col for col in df.columns
            if col != "Team" and not col.endswith("_rank")
        ]

        teams = [str(t) for t in df["Team"]]

        for stat_name in stat_cols:
            rank_col = f"{stat_name}_rank"
            if rank_col not in df.columns:
                # If rank column missing, skip this stat
                continue

            # Current values & ranks
            curr_vals: Dict[str, float] = {}
            curr_ranks: Dict[str, int] = {}

            for _, row in df[["Team", stat_name, rank_col]].iterrows():
                team_name = str(row["Team"])
                val = row[stat_name]
                if _is_missing(val):
                    continue
                try:
                    curr_vals[team_name] = float(val)
                    curr_ranks[team_name] = int(row[rank_col])
                except (TypeError, ValueError):
                    continue

            if not curr_vals:
                continue

            # Previous ranks from state (default to "worst+1" if missing)
            prev_ranks: Dict[str, int] = {}
            default_bad_rank = len(teams) + 1
            prev_vals: Dict[str, float] = {}

            for team_name in teams:
                r_key = f"RANK|{context}|{team_name}|{stat_name}"
                prev_ranks[team_name] = int(state.get(r_key, default_bad_rank))
                v_key = f"VAL|{context}|{team_name}|{stat_name}"
                # If we have no prior value in state, fall back to current value to avoid
                # false "overtake" events on first run after deploy/restart.
                prev_vals[team_name] = float(state.get(v_key, curr_vals.get(team_name, 0.0)))

            # Detect improvements
            for team_name in teams:
                if team_name not in curr_ranks:
                    continue  # no current data

                curr_rank = curr_ranks[team_name]
                prev_rank = prev_ranks.get(team_name, default_bad_rank)

                # Only consider teams whose rank improved (lower number = better)
                if curr_rank >= prev_rank:
                    continue

                # Find teams A truly crossed by value (not just rank bookkeeping):
                # - team was below other before
                # - team is now equal or above other
                candidates = []
                for other in teams:
                    if other == team_name:
                        continue

                    if other not in curr_vals:
                        continue

                    prev_self = prev_vals.get(team_name, curr_vals[team_name])
                    prev_other = prev_vals.get(other, curr_vals[other])
                    curr_self = curr_vals[team_name]
                    curr_other = curr_vals[other]

                    was_behind = prev_self < prev_other
                    now_tied_or_ahead = curr_self >= curr_other
                    if was_behind and now_tied_or_ahead:
                        candidates.append(other)

                if not candidates:
                    continue

                # Decide overtaken vs tied
                tie_candidates = [
                    other for other in candidates
                    if curr_vals.get(other, float("-inf")) == curr_vals[team_name]
                ]

                if tie_candidates:
                    verb = "tied"
                    # choose the one that was highest before
                    other_team = min(
                        tie_candidates,
                        key=lambda t: prev_ranks.get(t, default_bad_rank)
                    )
                else:
                    verb = "overtaken"
                    # choose the one that was just ahead before
                    other_team = min(
                        candidates,
                        key=lambda t: prev_ranks.get(t, default_bad_rank)
                    )

                rank_str = _ordinal(curr_rank)
                line = (
                    f"**{team_name}** has {verb} {other_team} in {context} {stat_name}. "
                    f"{team_name} now sits at **{rank_str} place** all time in {context} {stat_name}."
                )
                lines.append(line)

            # After checking rank changes for this stat, update stored ranks
            for team_name, r in curr_ranks.items():
                r_key = f"RANK|{context}|{team_name}|{stat_name}"
                state[r_key] = r
            for team_name, v in curr_vals.items():
                v_key = f"VAL|{context}|{team_name}|{stat_name}"
                state[v_key] = float(v)

    # ---------- send + save ----------
    _save_state(state)

    if not lines:
        return False

    content_parts = [
        "🚨 **Milestone Alert** 🚨",
        *lines,
        "",
        f"See more stats: [Open sheet]({STATS_URL})",
    ]

    payload = {"content": "\n".join(content_parts)}
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

    return True
