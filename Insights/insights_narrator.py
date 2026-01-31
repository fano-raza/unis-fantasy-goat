# Insights/insight_narrator.py
from __future__ import annotations

from typing import List, Dict, Any
from math import fabs

# Assumes Insight dataclass from your Insights/insight_detector.py (or insights_engine.py)
# If your Insight class lives elsewhere, update this import accordingly.
try:
    from Insights.insight_detector import Insight  # you said you saved it here
except Exception:
    # fallback if you run from a different working directory
    from insight_detector import Insight


def _ordinal(n: int) -> str:
    if n <= 0:
        return str(n)
    if 10 <= (n % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _streak_phrase(kind: str, n: int) -> str:
    if kind == "win":
        return f"{n} straight wins"
    if kind == "loss":
        return f"{n} straight losses"
    if kind == "undefeated":
        return f"{n} straight unbeaten (wins/ties)"
    return f"{n} straight"


def _rank_phrase(rank: int, tied: bool) -> str:
    if rank <= 0:
        return ""
    if tied:
        return f"tied for {_ordinal(rank)}"
    return f"{_ordinal(rank)}"


def _fmt_rating(x: Any) -> str:
    try:
        return f"{float(x):.2f}"
    except Exception:
        return str(x)


def narrate_insight(ins: Insight) -> str:
    """
    Deterministic, no-AI sentence generator.
    Uses ONLY the facts inside the Insight object.
    """
    t = ins.type
    f: Dict[str, Any] = ins.facts or {}
    team = ins.team
    opp = ins.opp

    # -----------------------------
    # Streaks
    # -----------------------------
    if t.startswith("streak."):
        kind = t.split(".", 1)[1]  # win/loss/undefeated
        cur = int(f.get("current_streak", 0) or 0)
        if cur <= 0:
            return ""

        season_rank = int(f.get("season_rank_dense", 0) or 0)
        season_tied = bool(f.get("season_tied", False))
        all_rank = int(f.get("all_time_rank_dense", 0) or 0)
        all_tied = bool(f.get("all_time_tied", False))

        streak_txt = _streak_phrase(kind, cur)

        # build headline
        parts = [f"{team} is on {streak_txt}"]

        # season note
        if season_rank == 1 and not season_tied:
            parts.append("— longest streak this season")
        elif season_rank == 1 and season_tied:
            parts.append("— tied for the longest streak this season")
        elif season_rank > 0 and season_rank <= 3:
            parts.append(f"— {_rank_phrase(season_rank, season_tied)} longest streak this season")

        # all-time note
        if all_rank > 0 and all_rank <= 3:
            parts.append(f"and {_rank_phrase(all_rank, all_tied)} longest in league history")

        return " ".join(parts) + "."

    # -----------------------------
    # Week superlatives
    # -----------------------------
    if t == "week.best_rating":
        return f"Peak week: {ins.team} posted the top week rating ({_fmt_rating(f.get('week_rating'))})."

    if t == "week.worst_rating":
        return f"Rough one: {ins.team} had the lowest week rating ({_fmt_rating(f.get('week_rating'))})."

    if t == "week.best_rank":
        return f"Most dominant this week: {ins.team} finished with the best weekly rank ({_fmt_rating(f.get('week_rank'))})."

    if t == "week.worst_rank":
        return f"Bottom of the pile: {ins.team} had the worst weekly rank ({_fmt_rating(f.get('week_rank'))})."

    # -----------------------------
    # Upsets
    # -----------------------------
    if t == "matchup.upset":
        gap = f.get("rating_gap")
        r_team = f.get("week_rating")
        r_opp = f.get("opp_week_rating")

        # cats summary if present
        cw = f.get("cat_wins")
        cl = f.get("cat_losses")
        ct = f.get("cat_ties")

        cat_str = ""
        if cw is not None and cl is not None and ct is not None:
            cat_str = f" ({int(cw)}–{int(cl)}–{int(ct)})"

        try:
            gap_abs = fabs(float(gap))
            gap_txt = f"{gap_abs:.2f}"
        except Exception:
            gap_txt = str(gap)

        if opp:
            return (
                f"Upset alert: {team} beat {opp}{cat_str} despite a worse week rating "
                f"({_fmt_rating(r_team)} vs {_fmt_rating(r_opp)}; gap {gap_txt})."
            )
        return f"Upset alert: {team} won despite a big rating disadvantage (gap {gap_txt})."

    # -----------------------------
    # Standings swings
    # -----------------------------
    if t == "standings.swing":
        prev_pos = int(f.get("prev_position", 0) or 0)
        cur_pos = int(f.get("cur_position", 0) or 0)
        delta = int(f.get("delta_positions", 0) or 0)
        rec_prev = f.get("record_prev")
        rec_cur = f.get("record_cur")

        if delta > 0:
            move = f"jumped {delta} spot" + ("s" if delta != 1 else "")
        elif delta < 0:
            move = f"dropped {abs(delta)} spot" + ("s" if abs(delta) != 1 else "")
        else:
            move = "held position"

        bits = [f"Standings shift: {team} {move} (from {_ordinal(prev_pos)} to {_ordinal(cur_pos)})."]
        if rec_prev and rec_cur and rec_prev != rec_cur:
            bits.append(f"Record moved from {rec_prev} to {rec_cur}.")
        return " ".join(bits)

    # Fallback (safe)
    return ""

    # -----------------------------
    # Cats standings swings
    # -----------------------------
    if t == "standings.swing_cats":
        prev_pos = int(f.get("prev_position", 0) or 0)
        cur_pos  = int(f.get("cur_position", 0) or 0)
        delta    = int(f.get("delta_positions", 0) or 0)
        cats_prev = f.get("cats_prev")
        cats_cur  = f.get("cats_cur")

        if delta > 0:
            move = f"jumped {delta} spot" + ("s" if delta != 1 else "")
        elif delta < 0:
            move = f"dropped {abs(delta)} spot" + ("s" if abs(delta) != 1 else "")
        else:
            move = "held position"

        bits = [f"Cats standings shift: {team} {move} (from {_ordinal(prev_pos)} to {_ordinal(cur_pos)})."]
        if cats_prev and cats_cur and cats_prev != cats_cur:
            bits.append(f"Cats record moved from {cats_prev} to {cats_cur}.")
        return " ".join(bits)

    # -----------------------------
    # Win% / Pct summary
    # -----------------------------
    if t == "pct.summary":
        s_wl = float(f.get("season_wl_pct", 0.0) or 0.0)
        s_c  = float(f.get("season_cats_pct", 0.0) or 0.0)
        c_wl = float(f.get("career_wl_pct", 0.0) or 0.0)
        c_c  = float(f.get("career_cats_pct", 0.0) or 0.0)

        s_wl_rank = int(f.get("season_wl_rank", 0) or 0)
        s_wl_tied = bool(f.get("season_wl_tied", False))
        s_c_rank  = int(f.get("season_cats_rank", 0) or 0)
        s_c_tied  = bool(f.get("season_cats_tied", False))

        c_wl_rank = int(f.get("career_wl_rank", 0) or 0)
        c_wl_tied = bool(f.get("career_wl_tied", False))
        c_c_rank  = int(f.get("career_cats_rank", 0) or 0)
        c_c_tied  = bool(f.get("career_cats_tied", False))

        h_wl_rank = int(f.get("hist_season_wl_rank", 0) or 0)
        h_wl_tied = bool(f.get("hist_season_wl_tied", False))
        h_c_rank  = int(f.get("hist_season_cats_rank", 0) or 0)
        h_c_tied  = bool(f.get("hist_season_cats_tied", False))

        parts = [f"Efficiency check: {team} is at {s_wl:.3f} WL% and {s_c:.3f} Cats% this season."]

        if s_wl_rank and s_wl_rank <= 3:
            parts.append(f"That’s {_rank_phrase(s_wl_rank, s_wl_tied)} in the league (WL%).")
        if s_c_rank and s_c_rank <= 3:
            parts.append(f"Also {_rank_phrase(s_c_rank, s_c_tied)} this season in Cats%.")
        if h_wl_rank and h_wl_rank <= 3:
            parts.append(f"And this WL% would be {_rank_phrase(h_wl_rank, h_wl_tied)} among all team-seasons ever.")
        if h_c_rank and h_c_rank <= 3:
            parts.append(f"This Cats% would be {_rank_phrase(h_c_rank, h_c_tied)} among all team-seasons ever.")

        # Career angle (your example)
        if c_wl_rank and c_wl_rank <= 3:
            parts.append(f"Career-wise: {team} has the {_rank_phrase(c_wl_rank, c_wl_tied)} best WL% all-time ({c_wl:.3f}).")
        if c_c_rank and c_c_rank <= 3:
            parts.append(f"Career-wise: {_rank_phrase(c_c_rank, c_c_tied)} best Cats% all-time ({c_c:.3f}).")

        return " ".join(parts)

    # -----------------------------
    # Totals W/L/T + Cats totals
    # -----------------------------
    if t == "totals.wlt":
        season_w = int(f.get("season_w", 0) or 0)
        season_l = int(f.get("season_l", 0) or 0)
        season_t = int(f.get("season_t", 0) or 0)
        season_cw = int(f.get("season_cw", 0) or 0)
        season_cl = int(f.get("season_cl", 0) or 0)
        season_ct = int(f.get("season_ct", 0) or 0)

        career_w = int(f.get("career_w", 0) or 0)
        career_l = int(f.get("career_l", 0) or 0)
        career_t = int(f.get("career_t", 0) or 0)

        career_w_rank = int(f.get("career_w_rank", 0) or 0)
        career_w_tied = bool(f.get("career_w_tied", False))
        career_l_rank = int(f.get("career_l_rank", 0) or 0)
        career_l_tied = bool(f.get("career_l_tied", False))

        parts = [f"Volume stats: {team} is {season_w}-{season_l}-{season_t} this season (Cats: {season_cw}-{season_cl}-{season_ct})."]
        if career_w_rank and career_w_rank <= 3:
            parts.append(f"All-time: {team} sits {_rank_phrase(career_w_rank, career_w_tied)} in total wins ({career_w}).")
        if career_l_rank and career_l_rank <= 3:
            parts.append(f"And {_rank_phrase(career_l_rank, career_l_tied)} in total losses ({career_l}).")

        # always include career record too
        parts.append(f"Career record: {career_w}-{career_l}-{career_t}.")
        return " ".join(parts)

    # -----------------------------
    # Head-to-head series
    # -----------------------------
    if t == "h2h.series":
        games = int(f.get("games", 0) or 0)
        team_wlt = f.get("team_wlt")
        team_cats = f.get("team_cats")
        if opp:
            return f"All-time H2H: {team} vs {opp} ({games} games) — WL: {team_wlt}, Cats: {team_cats}."
        return f"All-time H2H: {team} series record — WL: {team_wlt}, Cats: {team_cats}."

    # -----------------------------
    # 7-2 / 8-1 / 9-0 (and losses)
    # -----------------------------
    if t == "cats.blowout":
        bucket = str(f.get("bucket", ""))
        this_week_line = f.get("this_week_line")
        season_count = int(f.get("season_count", 0) or 0)
        career_count = int(f.get("career_count", 0) or 0)
        career_rank = int(f.get("career_rank", 0) or 0)
        career_tied = bool(f.get("career_tied", False))

        if bucket in ["9-0","8-1","7-2"]:
            intro = f"Statement win: {team} just posted a {bucket} (Cats: {this_week_line})"
        else:
            intro = f"Absolute disaster: {team} just got hit with a {bucket} (Cats: {this_week_line})"

        parts = [intro + "."]

        parts.append(f"That’s {season_count} time(s) this season and {career_count} all-time.")
        if career_rank and career_rank <= 3:
            parts.append(f"Which is {_rank_phrase(career_rank, career_tied)} most in league history for {bucket}.")
        return " ".join(parts)

    def _fmt_cat_value(cat: str, val: float) -> str:
        if cat in ["FG%", "FT%"]:
            # your data might already be 0-1 (e.g., 0.512) — show as %
            # if it's already 50+ (unlikely), this still works decently
            if val <= 1.5:
                return f"{val * 100:.1f}%"
            return f"{val:.1f}%"
        if abs(val) >= 1000:
            return f"{val:,.0f}"
        # integers as ints, otherwise 2dp
        return f"{val:.0f}" if float(val).is_integer() else f"{val:.2f}"

        # ...

        if t == "cat.week_extreme":
            cat = str(f.get("category"))
            val = float(f.get("value", 0.0) or 0.0)
            direction = str(f.get("direction", "higher_is_better"))
            flags = f.get("extreme_flags", []) or []

            s_best = int(f.get("season_best_rank", 0) or 0)
            s_best_tied = bool(f.get("season_best_tied", False))
            s_worst = int(f.get("season_worst_rank", 0) or 0)
            s_worst_tied = bool(f.get("season_worst_tied", False))

            a_best = int(f.get("all_time_best_rank", 0) or 0)
            a_best_tied = bool(f.get("all_time_best_tied", False))
            a_worst = int(f.get("all_time_worst_rank", 0) or 0)
            a_worst_tied = bool(f.get("all_time_worst_tied", False))

            vtxt = _fmt_cat_value(cat, val)

            # Decide whether to speak as "high" or "low" based on what triggered
            # (could be both season + all-time)
            parts = [f"Category watch: {team} just put up {vtxt} in {cat}."]

            # Season callout
            if ("season_high" in flags) or ("season_low" in flags):
                if direction == "higher_is_better":
                    if "season_high" in flags:
                        parts.append(
                            f"That’s {_rank_phrase(s_best, s_best_tied)} best {cat} performance of the season.")
                    if "season_low" in flags:
                        parts.append(
                            f"And {_rank_phrase(s_worst, s_worst_tied)} worst {cat} performance of the season.")
                else:
                    # lower is better (TO)
                    if "season_low" in flags:
                        parts.append(f"That’s {_rank_phrase(s_best, s_best_tied)} best (lowest) {cat} of the season.")
                    if "season_high" in flags:
                        parts.append(f"And {_rank_phrase(s_worst, s_worst_tied)} worst (highest) {cat} of the season.")

            # All-time callout
            if ("all_time_high" in flags) or ("all_time_low" in flags):
                if direction == "higher_is_better":
                    if "all_time_high" in flags and a_best:
                        parts.append(f"League history: {_rank_phrase(a_best, a_best_tied)} best {cat} week ever.")
                    if "all_time_low" in flags and a_worst:
                        parts.append(f"League history: {_rank_phrase(a_worst, a_worst_tied)} worst {cat} week ever.")
                else:
                    if "all_time_low" in flags and a_best:
                        parts.append(
                            f"League history: {_rank_phrase(a_best, a_best_tied)} best (lowest) {cat} week ever.")
                    if "all_time_high" in flags and a_worst:
                        parts.append(
                            f"League history: {_rank_phrase(a_worst, a_worst_tied)} worst (highest) {cat} week ever.")

            return " ".join(parts)


def narrate_insights(insights: List[Insight], *, drop_empty: bool = True) -> List[str]:
    """
    Converts a list of Insight objects into a list of readable blurbs.
    """
    out = []
    for ins in insights:
        s = narrate_insight(ins)
        if drop_empty and not s:
            continue
        out.append(s)
    return out


def group_blurbs_for_week(blurbs: List[str]) -> str:
    """
    Simple formatter for a "Week Recap" block of text.
    """
    if not blurbs:
        return "No notable insights detected."
    return "\n".join([f"- {b}" for b in blurbs])
