#!/usr/bin/env python3
"""Download Intervals.icu wellness (sleep, weight, HRV, readiness) as CSV."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from intervals_lib import api_key, fetch_wellness_csv  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Intervals.icu wellness.csv for a date range"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days ending on --newest (default 7)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write CSV here (default stdout)",
    )
    parser.add_argument(
        "--oldest",
        type=str,
        help="ISO date YYYY-MM-DD (overrides --days)",
    )
    parser.add_argument(
        "--newest",
        type=str,
        help="ISO date YYYY-MM-DD (default today)",
    )
    args = parser.parse_args()

    if not api_key():
        print(
            "Set INTERVALS_API or INTERVALS_API_KEY (Intervals Settings → Developer).",
            file=sys.stderr,
        )
        return 1

    newest = args.newest or date.today().isoformat()
    if args.oldest:
        oldest = args.oldest
    else:
        newest_d = date.fromisoformat(newest)
        oldest = (newest_d - timedelta(days=max(args.days, 1) - 1)).isoformat()

    body = fetch_wellness_csv(oldest, newest)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(body)
        print(f"Wrote {len(body)} bytes to {args.output}", file=sys.stderr)
        print(f"Range: {oldest} … {newest}", file=sys.stderr)
    else:
        sys.stdout.buffer.write(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
