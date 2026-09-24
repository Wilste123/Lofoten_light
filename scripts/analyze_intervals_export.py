#!/usr/bin/env python3
"""Summarize an Intervals.icu activities.csv export."""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from analyze_tp_export import find_column, parse_date, parse_float


def load_rows(path: Path) -> tuple[list[dict], list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")
        return list(reader), list(reader.fieldnames)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Intervals.icu activities CSV")
    parser.add_argument("csv_path", type=Path)
    args = parser.parse_args()
    if not args.csv_path.is_file():
        print(f"File not found: {args.csv_path}", file=sys.stderr)
        return 1

    rows, fields = load_rows(args.csv_path)
    date_col = find_column(
        fields,
        ["start_date_local", "date", "start_time", "workoutday", "day"],
    )
    load_col = find_column(
        fields,
        ["icu_training_load", "training_load", "load", "tss", "training stress"],
    )
    type_col = find_column(fields, ["type", "sport", "workouttype"])
    name_col = find_column(fields, ["name", "title", "activity"])
    dur_col = find_column(
        fields,
        ["elapsed_time", "moving_time", "duration", "timetotalinhours"],
    )
    if_col = find_column(fields, ["icu_intensity", "intensity", "if"])

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

    week_load: dict[str, float] = defaultdict(float)
    sport_load: dict[str, float] = defaultdict(float)
    total_load = 0.0
    total_hours = 0.0
    sessions = len(dated)

    for d, r in dated:
        load = parse_float(r.get(load_col, "")) if load_col else None
        if load is not None:
            total_load += load
            week_load[d.strftime("%G-W%V")] += load
        sport = (r.get(type_col, "") if type_col else "") or "unknown"
        sport_load[sport.strip() or "unknown"] += load or 0

        if dur_col:
            raw = r.get(dur_col, "")
            dur = parse_float(raw)
            if dur is not None:
                # Intervals often uses seconds for elapsed_time
                if dur_col and "time" in dur_col.lower() and dur > 24:
                    total_hours += dur / 3600.0
                elif dur < 15:  # likely already hours
                    total_hours += dur
                else:
                    total_hours += dur / 3600.0

    print("# Intervals.icu activities summary\n")
    print(f"File: {args.csv_path.name}")
    print(f"Sessions: {sessions} ({dated[0][0].date()} … {dated[-1][0].date()})")

    if load_col:
        print(f"Total training load (TSS-like): {total_load:.0f}")
        if week_load:
            print("\n## Weekly load")
            for w in sorted(week_load.keys()):
                print(f"- {w}: {week_load[w]:.0f}")
    else:
        print("No load/TSS column found — check export includes training load.")

    if total_hours:
        print(f"\nTotal duration (approx): {total_hours:.1f} h")

    if sport_load and load_col and total_load:
        print("\n## Load by type")
        for sport, val in sorted(sport_load.items(), key=lambda x: -x[1]):
            if val > 0:
                pct = 100 * val / total_load
                print(f"- {sport}: {val:.0f} ({pct:.0f}%)")

    if name_col:
        print("\n## Sessions")
        for d, r in dated:
            title = (r.get(name_col) or "").strip() or "(no name)"
            load = parse_float(r.get(load_col, "")) if load_col else None
            iff = parse_float(r.get(if_col, "")) if if_col else None
            bits = []
            if load is not None:
                bits.append(f"load {load:.0f}")
            if iff is not None:
                bits.append(f"IF {iff:.2f}")
            extra = f" | {', '.join(bits)}" if bits else ""
            print(f"- {d.date()} {title}{extra}")

    print("\n---\nAsk the Cursor agent for OPV ukesopp against your plan in plans/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
