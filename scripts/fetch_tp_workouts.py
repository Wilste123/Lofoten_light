#!/usr/bin/env python3
"""Fetch planned/completed workouts from TrainingPeaks API → JSON + CSV."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from tp_lib import get_workouts  # noqa: E402

_REPO = _SCRIPT_DIR.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", help="YYYY-MM-DD (default: 14 days ago)")
    parser.add_argument("--end", help="YYYY-MM-DD (default: today)")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=_REPO / "data/trainingpeaks/exports/tp-workouts.json",
    )
    args = parser.parse_args()
    end = date.fromisoformat(args.end) if args.end else date.today()
    start = (
        date.fromisoformat(args.start)
        if args.start
        else end - timedelta(days=14)
    )
    if (end - start).days > 45:
        print("Error: TP API max range is 45 days", file=sys.stderr)
        return 1

    workouts = get_workouts(start.isoformat(), end.isoformat())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(workouts, indent=2), encoding="utf-8")

    csv_path = args.output.with_suffix(".csv")
    fields = [
        "Id",
        "WorkoutDay",
        "WorkoutType",
        "Title",
        "TotalTime",
        "TssActual",
        "TssPlanned",
        "Distance",
        "Description",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in workouts:
            w.writerow({k: row.get(k, "") for k in fields})

    print(f"Wrote {len(workouts)} workouts to {args.output}")
    print(f"CSV: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
