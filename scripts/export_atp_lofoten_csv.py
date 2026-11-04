#!/usr/bin/env python3
"""Export ATP_Lofoten.xlsx → plans/csv/atp-lofoten-weekly.csv"""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
XLSX = ROOT / "ATP_Lofoten.xlsx"
OUT = ROOT / "plans/csv/atp-lofoten-weekly.csv"


def td_hours(val) -> float | None:
    if val is None:
        return None
    if isinstance(val, timedelta):
        return round(val.total_seconds() / 3600, 2)
    if isinstance(val, (int, float)):
        return float(val)
    return None


def main() -> None:
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    ws = wb["ATP - Lofoten"]
    rows: list[dict] = []
    for r in range(5, ws.max_row + 1):
        start = ws.cell(r, 1).value
        if start is None:
            continue
        period = ws.cell(r, 5).value
        if not period:
            continue
        if isinstance(start, datetime):
            week_start = start.date().isoformat()
        elif isinstance(start, date):
            week_start = start.isoformat()
        else:
            week_start = str(start)[:10]
        hours = td_hours(ws.cell(r, 6).value)
        if hours is None:
            continue
        rows.append(
            {
                "week_start": week_start,
                "weeks_to_event": ws.cell(r, 3).value,
                "period": str(period).strip(),
                "hours": hours,
                "tss_approx": round(hours * 52),
                "recovery_week": "true" if hours <= 9.0 and "Week 4" in str(period) else "false",
                "ftp_test": "true" if ws.cell(r, 10).value == "X" else "false",
                "intensity_note": ws.cell(r, 8).value or "",
                "limiters": ws.cell(r, 9).value or "",
                "merknad": ws.cell(r, 12).value or "",
            }
        )
    # Drop obvious post-race duplicate rows (after Race week)
    race_idx = next(
        (i for i, x in enumerate(rows) if str(x["period"]).startswith("Race")),
        None,
    )
    if race_idx is not None:
        rows = rows[: race_idx + 1]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else []
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUT}")


if __name__ == "__main__":
    main()
