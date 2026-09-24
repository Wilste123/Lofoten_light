#!/usr/bin/env python3
"""Summarize Intervals.icu wellness.csv for OPV coach review."""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from analyze_tp_export import find_column, parse_date, parse_float  # noqa: E402

WELLNESS_METRICS = [
    ("sleepSecs", "Søvn", "h", 3600.0),
    ("sleepScore", "Søvnscore", "", 1.0),
    ("restingHR", "Hvilepuls", "bpm", 1.0),
    ("hrv", "HRV", "ms", 1.0),
    ("hrvSDNN", "HRV SDNN", "ms", 1.0),
    ("weight", "Vekt", "kg", 1.0),
    ("readiness", "Readiness", "", 1.0),
    ("avgSleepingHR", "Søvnpuls snitt", "bpm", 1.0),
    ("soreness", "Stølhet", "", 1.0),
    ("fatigue", "Utmattelse", "", 1.0),
    ("stress", "Stress", "", 1.0),
    ("mood", "Humør", "", 1.0),
    ("motivation", "Motivasjon", "", 1.0),
    ("steps", "Skritt", "", 1.0),
    ("spO2", "SpO2", "%", 1.0),
    ("bodyFat", "Fett %", "%", 1.0),
]


def load_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")
        return list(reader), list(reader.fieldnames)


def col_map(fields: list[str]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for key, _label, _unit, _div in WELLNESS_METRICS:
        out[key] = find_column(fields, [key, key.lower()])
    out["date"] = find_column(fields, ["date", "id", "day"])
    out["comments"] = find_column(fields, ["comments", "comment"])
    out["bodyFat"] = find_column(fields, ["bodyFat", "body_fat", "body fat"])
    out["ctl"] = find_column(fields, ["ctl"])
    out["atl"] = find_column(fields, ["atl"])
    return out


def metric_value(row: dict[str, str], col: str | None, div: float) -> float | None:
    if not col:
        return None
    v = parse_float(row.get(col, ""))
    if v is None:
        return None
    return v / div if div != 1.0 else v


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Intervals.icu wellness CSV")
    parser.add_argument("csv_path", type=Path)
    args = parser.parse_args()
    if not args.csv_path.is_file():
        print(f"File not found: {args.csv_path}", file=sys.stderr)
        return 1

    rows, fields = load_rows(args.csv_path)
    cols = col_map(fields)
    if not cols["date"]:
        print("Could not find date column. Headers:", ", ".join(fields), file=sys.stderr)
        return 1

    dated: list[tuple[datetime, dict[str, str]]] = []
    for r in rows:
        d = parse_date(r.get(cols["date"], ""))
        if d:
            dated.append((d, r))
    if not dated:
        print("No parseable dates in export.", file=sys.stderr)
        return 1

    dated.sort(key=lambda x: x[0])
    n_days = len(dated)

    print("# Intervals.icu wellness summary\n")
    print(f"File: {args.csv_path.name}")
    print(f"Days: {n_days} ({dated[0][0].date()} … {dated[-1][0].date()})\n")

    print("## Data coverage")
    for key, label, unit, div in WELLNESS_METRICS:
        col = cols.get(key)
        if not col:
            continue
        values = [
            metric_value(r, col, div)
            for _d, r in dated
            if metric_value(r, col, div) is not None
        ]
        if not values:
            print(f"- {label}: ingen data")
            continue
        suffix = f" {unit}" if unit else ""
        print(
            f"- {label}: {len(values)}/{n_days} dager | "
            f"snitt {mean(values):.1f}{suffix} | "
            f"min {min(values):.1f} | max {max(values):.1f}"
        )

    sleep_col = cols.get("sleepSecs")
    if sleep_col:
        short_nights = 0
        for _d, r in dated:
            h = metric_value(r, sleep_col, 3600.0)
            if h is not None and h < 6.0:
                short_nights += 1
        if short_nights:
            print(f"\n**Flagg:** {short_nights} natt(er) med søvn < 6 t")

    weight_col = cols.get("weight")
    if weight_col:
        weights = [
            metric_value(r, weight_col, 1.0)
            for _d, r in dated
            if metric_value(r, weight_col, 1.0) is not None
        ]
        if weights:
            print(f"\n**Vekt:** sist {weights[-1]:.1f} kg (snitt {mean(weights):.1f} kg)")

    ctl_col, atl_col = cols.get("ctl"), cols.get("atl")
    if ctl_col and atl_col:
        last = dated[-1][1]
        ctl = parse_float(last.get(ctl_col, ""))
        atl = parse_float(last.get(atl_col, ""))
        if ctl is not None and atl is not None:
            print(f"\n**Fitness (siste dag):** CTL {ctl:.0f}, ATL {atl:.0f}")

    print("\n## Dag-for-dag (kompakt)")
    for d, r in dated:
        parts: list[str] = []
        for key, label, unit, div in WELLNESS_METRICS:
            col = cols.get(key)
            v = metric_value(r, col, div) if col else None
            if v is None:
                continue
            if key == "sleepSecs":
                parts.append(f"søvn {v:.1f}h")
            elif key == "weight":
                parts.append(f"{v:.1f} kg")
            elif key == "restingHR":
                parts.append(f"RHR {v:.0f}")
            elif key == "hrv":
                parts.append(f"HRV {v:.0f}")
            elif key in ("fatigue", "stress", "soreness"):
                parts.append(f"{label[:3]} {v:.0f}")
            elif key == "readiness":
                parts.append(f"ready {v:.0f}")
        if cols.get("comments") and (r.get(cols["comments"]) or "").strip():
            parts.append("kommentar")
        line = ", ".join(parts) if parts else "(kun CTL/ATL — ingen wellness fra enhet)"
        print(f"- {d.date()}: {line}")

    print(
        "\n---\nTomme felt = Garmin/klokke synker ikke wellness til Intervals, "
        "eller du logger ikke der. Sjekk Intervals → Wellness for én dag."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
