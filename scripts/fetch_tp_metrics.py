#!/usr/bin/env python3
"""Fetch wellness/body metrics from TrainingPeaks Partners API → JSON + CSV.

Requires JWT Bearer from api.trainingpeaks.com (not Production_tpAuth cookie).
For Garmin wellness with cookie-only auth, use fetch_intervals_wellness.py instead.
"""

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

from tp_lib import get_metrics, is_cookie_credential  # noqa: E402

_REPO = _SCRIPT_DIR.parent

CSV_FIELDS = [
    "Timestamp",
    "MetricType",
    "Value",
    "Units",
    "Notes",
]


def flatten_metrics(rows: list[dict]) -> list[dict]:
    """Best-effort flatten for Partners Metrics objects (shape varies by type)."""
    out: list[dict] = []
    for row in rows:
        ts = row.get("Timestamp") or row.get("timestamp") or row.get("Date") or ""
        mtype = row.get("Type") or row.get("type") or row.get("MetricType") or ""
        val = row.get("Value") or row.get("value")
        units = row.get("Units") or row.get("units") or ""
        notes = row.get("Notes") or row.get("notes") or ""
        if val is None and isinstance(row.get("Metrics"), list):
            for sub in row["Metrics"]:
                out.extend(flatten_metrics([sub]))
            continue
        out.append(
            {
                "Timestamp": ts,
                "MetricType": mtype,
                "Value": val,
                "Units": units,
                "Notes": notes,
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", help="YYYY-MM-DD (default: 14 days ago)")
    parser.add_argument("--end", help="YYYY-MM-DD (default: today)")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=_REPO / "data/trainingpeaks/exports/tp-metrics.json",
    )
    args = parser.parse_args()
    end = date.fromisoformat(args.end) if args.end else date.today()
    start = (
        date.fromisoformat(args.start) if args.start else end - timedelta(days=14)
    )
    if (end - start).days > 45:
        print("Error: TP API max range is 45 days", file=sys.stderr)
        return 1

    if is_cookie_credential():
        print(
            "Note: Production_tpAuth cookie cannot read TP /v2/metrics.\n"
            "  Wellness: python3 scripts/fetch_intervals_wellness.py --days 8\n"
            "  Or add a JWT Bearer from api.trainingpeaks.com for TP metrics.",
            file=sys.stderr,
        )
        return 2

    metrics = get_metrics(start.isoformat(), end.isoformat())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    flat = flatten_metrics(metrics)
    csv_path = args.output.with_suffix(".csv")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for row in flat:
            w.writerow(row)

    print(f"Wrote {len(metrics)} metric record(s) to {args.output}")
    print(f"CSV rows: {len(flat)} → {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
