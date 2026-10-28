#!/usr/bin/env python3
"""Fetch TrainingPeaks PMC (Fitness/Fatigue/Form) via tpapi performancedata."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from tp_lib import get_pmc_for_day, get_performance_data  # noqa: E402

_REPO = _SCRIPT_DIR.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", help="YYYY-MM-DD (default: 90 days before --end)")
    parser.add_argument("--end", help="YYYY-MM-DD (default: today)")
    parser.add_argument(
        "--day",
        help="Print single day PMC only (YYYY-MM-DD)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=_REPO / "data/trainingpeaks/exports/tp-pmc.json",
    )
    args = parser.parse_args()

    if args.day:
        row = get_pmc_for_day(args.day)
        print(
            f"{row['date']}: Fitness {row['fitness_ctl']:.0f}, "
            f"Fatigue {row['fatigue_atl']:.0f}, Form {row['form_tsb']:.0f}"
        )
        return 0

    end = date.fromisoformat(args.end) if args.end else date.today()
    start = (
        date.fromisoformat(args.start) if args.start else end - timedelta(days=90)
    )
    rows = get_performance_data(start.isoformat(), end.isoformat())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    if rows:
        last = rows[-1]
        d = (last.get("workoutDay") or "")[:10]
        print(
            f"Latest ({d}): Fitness {last.get('ctl', 0):.0f}, "
            f"Fatigue {last.get('atl', 0):.0f}, Form {last.get('tsb', 0):.0f}"
        )
    print(f"Wrote {len(rows)} days to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
