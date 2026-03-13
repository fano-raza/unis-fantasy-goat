#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from nltk.corpus import wordnet as wn


SEEDS: dict[str, list[str]] = {
    "PTS": ["points", "score", "scoring"],
    "REB": ["rebound", "boards"],
    "AST": ["assist", "passing", "playmaking"],
    "STL": ["steal", "takeaway"],
    "BLK": ["block", "rejection", "swat"],
    "TO": ["turnover", "giveaway", "mistake"],
    "3PTM": ["three", "triples", "threes"],
    "FG%": ["field_goal_percentage", "accuracy"],
    "FT%": ["free_throw_percentage", "accuracy"],
    "W": ["wins", "victory"],
    "L": ["loss", "defeat"],
    "D": ["tie", "draw"],
    "WIN_PCT": ["winning_percentage", "record"],
    "CAT_WIN_PCT": ["win_percentage", "category"],
    "AVG_RATING": ["rating", "average"],
    "AVG_OPP_RATING": ["opponent_strength", "schedule_strength"],
    "SOS_RANK": ["schedule_rank", "strength"],
    "RANK": ["rank", "ranking"],
    "WEIGHTED_RANK": ["weighted_rank", "rank"],
    "DRAFT_SCORE": ["draft", "value", "grade"],
    "DRAFT_SCORE_PER_PICK": ["draft_efficiency", "average"],
    "TOP1_WEEKS": ["first", "leader"],
    "TOP3_RATE": ["top_three", "rate"],
    "PLAYOFF_APPEARANCES": ["playoff", "appearance"],
    "PLAYOFF_APP_RATE": ["playoff_rate", "appearance_rate"],
    "FINALS": ["finals", "championship_round"],
    "CHIPS": ["championship", "title", "ring"],
    "FINALS_CONVERSION": ["conversion", "championship_rate"],
}


def _clean(token: str) -> str:
    s = token.replace("_", " ").replace("-", " ").strip().lower()
    s = re.sub(r"[^a-z0-9 %]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _ranked_wordnet_terms(seed: str) -> list[tuple[str, int]]:
    scores = defaultdict(int)
    for syn in wn.synsets(seed):
        for lemma in syn.lemmas():
            name = _clean(lemma.name())
            if not name:
                continue
            # Weighted by lemma count + mild boost for seed synsets.
            scores[name] += int(lemma.count() or 1) + 1
        for related in syn.hypernyms() + syn.hyponyms() + syn.similar_tos():
            for lemma in related.lemmas():
                name = _clean(lemma.name())
                if not name:
                    continue
                scores[name] += int(lemma.count() or 1)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


def build_aliases(top_k: int) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for metric, seeds in SEEDS.items():
        scores = defaultdict(int)
        for seed in seeds:
            for term, sc in _ranked_wordnet_terms(seed):
                scores[term] += sc
            scores[_clean(seed)] += 5
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        picked = []
        for term, _ in ranked:
            if len(picked) >= top_k:
                break
            if not term or term.isdigit():
                continue
            if term not in picked:
                picked.append(term)
        out[metric] = picked
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate WordNet alias list for metrics.")
    ap.add_argument("--top-k", type=int, default=25)
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("discord/metric_aliases_wordnet.json"),
    )
    args = ap.parse_args()

    aliases = build_aliases(max(1, args.top_k))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(aliases, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Wrote {args.out} with {len(aliases)} metrics (top_k={args.top_k}).")


if __name__ == "__main__":
    main()
