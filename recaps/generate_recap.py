from __future__ import annotations

import argparse
from pathlib import Path

from constants import currentYear
from recaps.recap_utils import write_regular_season_recap


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate recap markdown files from league data."
    )
    parser.add_argument(
        "--year",
        type=int,
        default=currentYear,
        help=f"Season year to recap (default: {currentYear}).",
    )
    parser.add_argument(
        "--type",
        choices=["regular-season"],
        default="regular-season",
        help="Recap type to generate.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Optional output markdown path. Defaults to recaps/<year>_regular_season_recap.md",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_path = Path(args.output) if args.output else None

    if args.type == "regular-season":
        out = write_regular_season_recap(args.year, output_path=output_path)
        print(f"Generated recap: {out}")
        return 0

    raise ValueError(f"Unsupported recap type: {args.type}")


if __name__ == "__main__":
    raise SystemExit(main())
