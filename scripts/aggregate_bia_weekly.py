#!/usr/bin/env python3
"""Compute 7-day BIA averages from intervals-bia-daily.csv → ukesnitt row."""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean

_REPO = Path(__file__).resolve().parents[1]
DAILY = _REPO / "plans/csv/intervals-bia-daily.csv"
WEEKLY = _REPO / "plans/csv/intervals-bia-ukesnitt.csv"


def _float(s: str) -> float | None:
    s = (s or "").strip()
    if not s or s.startswith("#"):
        return None
    return float(s.replace(",", "."))


def load_daily(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if not row.get("date") or str(row["date"]).startswith("#"):
                continue
            rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--week-ending",
        type=str,
        help="Sunday YYYY-MM-DD (default: last Sunday)",
    )
    parser.add_argument("--daily", type=Path, default=DAILY)
    parser.add_argument("--append", type=Path, default=WEEKLY)
    parser.add_argument("--print-only", action="store_true")
    args = parser.parse_args()

    if args.week_ending:
        end = date.fromisoformat(args.week_ending)
    else:
        today = date.today()
        end = today - timedelta(days=(today.weekday() + 1) % 7)
    start = end - timedelta(days=6)

    daily = load_daily(args.daily)
    in_week = []
    for r in daily:
        d = date.fromisoformat(r["date"][:10])
        if start <= d <= end:
            in_week.append(r)

    if not in_week:
        print(f"No daily rows {start} … {end}", file=sys.stderr)
        return 1

    def avg_col(col: str) -> str:
        vals = [_float(r.get(col, "")) for r in in_week]
        vals = [v for v in vals if v is not None]
        return f"{mean(vals):.2f}" if vals else ""

    out = {
        "week_ending": end.isoformat(),
        "weight_kg_7d_avg": avg_col("weight_kg"),
        "body_fat_pct_7d_avg": avg_col("body_fat_pct"),
        "body_water_pct_7d_avg": avg_col("body_water_pct"),
        "ffm_kg_7d_avg": avg_col("ffm_kg"),
        "muscle_kg_7d_avg": avg_col("muscle_kg"),
        "visceral_avg": avg_col("visceral"),
        "monthly_cap_kg": "",
        "strength_ok": "",
        "opv_line": "",
    }
    print(
        f"Week {start} … {end} ({len(in_week)} days): "
        f"wt {out['weight_kg_7d_avg']} fat {out['body_fat_pct_7d_avg']}%"
    )

    if args.print_only:
        print(out)
        return 0

    # Append to weekly CSV if not duplicate week_ending
    existing: list[dict] = []
    fieldnames = list(out.keys())
    if args.append.is_file():
        with args.append.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or fieldnames
            for row in reader:
                if row.get("week_ending") and not str(row["week_ending"]).startswith("#"):
                    existing.append(row)

    existing = [r for r in existing if r.get("week_ending") != out["week_ending"]]
    existing.append({k: out.get(k, "") for k in fieldnames})

    line = ",".join(str(out.get(k, "")) for k in fieldnames)
    text = args.append.read_text(encoding="utf-8") if args.append.is_file() else ""
    if out["week_ending"] in text:
        print("Week already in file; edit manually or remove row first.", file=sys.stderr)
        return 1
    with args.append.open("a", encoding="utf-8") as f:
        if not text.endswith("\n"):
            f.write("\n")
        f.write(line + "\n")
    print(f"Appended line to {args.append}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
