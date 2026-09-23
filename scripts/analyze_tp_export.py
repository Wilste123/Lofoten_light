#!/usr/bin/env python3
"""Summarize a TrainingPeaks CSV export (calendar or summary)."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def parse_date(raw: str) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw[: len(fmt.replace("%", "0"))], fmt)
        except ValueError:
            continue
    m = re.match(r"(\d{4}-\d{2}-\d{2})", raw)
    if m:
        return datetime.strptime(m.group(1), "%Y-%m-%d")
    return None


def parse_float(raw: str) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def find_column(fieldnames: list[str], candidates: list[str]) -> str | None:
    lower = {f.lower(): f for f in fieldnames}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    for f in fieldnames:
        fl = f.lower()
        for c in candidates:
            if c.lower() in fl:
                return f
    return None


def load_rows(path: Path) -> tuple[list[dict], list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")
        return list(reader), list(reader.fieldnames)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze TrainingPeaks CSV export")
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--weeks", type=int, default=12, help="Report window (default 12)")
    args = parser.parse_args()
    if not args.csv_path.is_file():
        print(f"File not found: {args.csv_path}", file=sys.stderr)
        return 1

    rows, fields = load_rows(args.csv_path)
    date_col = find_column(fields, ["workoutday", "date", "workout day", "day"])
    tss_col = find_column(fields, ["tss", "tssactual", "tss actual", "training stress score"])
    title_col = find_column(fields, ["title", "workout title", "description"])
    type_col = find_column(fields, ["workouttype", "type", "sport"])
    duration_col = find_column(fields, ["timetotalinhours", "duration", "elapsedtime", "time"])

    if not date_col:
        print("Could not find a date column. Headers:", ", ".join(fields), file=sys.stderr)
        return 1

    dated: list[tuple[datetime, dict]] = []
    for r in rows:
        d = parse_date(r.get(date_col, ""))
        if d:
            dated.append((d, r))
    if not dated:
        print("No parseable dates in export.", file=sys.stderr)
        return 1

    dated.sort(key=lambda x: x[0])
    latest = dated[-1][0]
    window_start = latest.replace(hour=0, minute=0, second=0, microsecond=0)
    # approximate window
    from datetime import timedelta

    cutoff = window_start - timedelta(weeks=args.weeks)

    week_tss: dict[str, float] = defaultdict(float)
    sport_tss: dict[str, float] = defaultdict(float)
    sessions = 0
    total_tss = 0.0
    total_hours = 0.0

    for d, r in dated:
        if d < cutoff:
            continue
        sessions += 1
        tss = parse_float(r.get(tss_col, "")) if tss_col else None
        if tss is not None:
            total_tss += tss
            iso_week = d.strftime("%G-W%V")
            week_tss[iso_week] += tss
        if duration_col:
            dur = parse_float(r.get(duration_col, ""))
            if dur is not None:
                total_hours += dur
        sport = (r.get(type_col, "") if type_col else "") or "unknown"
        sport_tss[sport.strip() or "unknown"] += tss or 0

    print(f"# TrainingPeaks export summary\n")
    print(f"File: {args.csv_path.name}")
    print(f"Rows in window: {sessions} (last {args.weeks} weeks ending ~{latest.date()})")
    if tss_col:
        print(f"Total TSS: {total_tss:.0f}")
        if week_tss:
            avg_week = total_tss / max(len(week_tss), 1)
            print(f"Weeks with data: {len(week_tss)} | Avg TSS/week: {avg_week:.0f}")
            print("\n## Weekly TSS")
            for w in sorted(week_tss.keys()):
                print(f"- {w}: {week_tss[w]:.0f}")
    else:
        print("No TSS column detected — export may need 'Training Stress Score' enabled.")

    if duration_col and total_hours:
        print(f"\nTotal duration (reported): {total_hours:.1f} h")

    if sport_tss and tss_col:
        print("\n## TSS by sport/type")
        for sport, val in sorted(sport_tss.items(), key=lambda x: -x[1]):
            if val > 0:
                pct = 100 * val / total_tss if total_tss else 0
                print(f"- {sport}: {val:.0f} TSS ({pct:.0f}%)")

    if title_col:
        print("\n## Sample recent sessions")
        for d, r in dated[-5:]:
            title = (r.get(title_col) or "").strip() or "(no title)"
            tss = parse_float(r.get(tss_col, "")) if tss_col else None
            extra = f" | TSS {tss:.0f}" if tss is not None else ""
            print(f"- {d.date()} {title}{extra}")

    print("\n---\nAsk the Cursor agent to interpret this in context of your plan and goals.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
