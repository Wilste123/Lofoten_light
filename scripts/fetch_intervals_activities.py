#!/usr/bin/env python3
"""Download Intervals.icu activities as CSV for a date range (personal API key)."""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Intervals.icu activities.csv")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days ending today (default 7)",
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

    api_key = os.environ.get("INTERVALS_API_KEY", "").strip()
    if not api_key:
        print(
            "Set INTERVALS_API_KEY in the environment (Intervals Settings → Developer).",
            file=sys.stderr,
        )
        return 1

    newest = args.newest or date.today().isoformat()
    if args.oldest:
        oldest = args.oldest
    else:
        newest_d = date.fromisoformat(newest)
        oldest = (newest_d - timedelta(days=max(args.days, 1) - 1)).isoformat()

    url = (
        "https://intervals.icu/api/v1/athlete/0/activities.csv"
        f"?oldest={oldest}&newest={newest}"
    )
    req = urllib.request.Request(url)
    # Personal API key: Basic auth username API_KEY, password = key
    import base64

    token = base64.b64encode(f"API_KEY:{api_key}".encode()).decode()
    req.add_header("Authorization", f"Basic {token}")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        print(f"Intervals API error {e.code}: {e.read().decode()[:500]}", file=sys.stderr)
        return 1

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(body)
        print(f"Wrote {len(body)} bytes to {args.output}", file=sys.stderr)
    else:
        sys.stdout.buffer.write(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
