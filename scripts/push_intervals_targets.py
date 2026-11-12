#!/usr/bin/env python3
"""Push weekly TARGET load events to Intervals.icu from CSV."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO = _SCRIPT_DIR.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from intervals_lib import api_get, api_key, delete_events_bulk, post_events_bulk  # noqa: E402

# Tri split aligned with William (swim limiter, run + bike carry volume)
_SPLIT = {"Ride": 0.38, "Run": 0.38, "Swim": 0.24}
_TYPES = ("Ride", "Run", "Swim")


def _split_load(total: int) -> dict[str, int]:
    ride = int(round(total * _SPLIT["Ride"]))
    run = int(round(total * _SPLIT["Run"]))
    swim = max(total - ride - run, 0)
    return {"Ride": ride, "Run": run, "Swim": swim}


def _split_time(hours: float) -> dict[str, int]:
    secs = int(hours * 3600)
    out: dict[str, int] = {}
    rem = secs
    for i, sport in enumerate(_TYPES):
        if i < len(_TYPES) - 1:
            part = int(round(secs * _SPLIT[sport]))
            out[sport] = part
            rem -= part
        else:
            out[sport] = max(rem, 0)
    return out


def load_weeks(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            rows.append(
                {
                    "week_start": row["week_start"].strip(),
                    "phase": row.get("phase", ""),
                    "total_tss": int(float(row["total_tss"])),
                    "hours": float(row["hours"]),
                    "notes": (row.get("notes") or "").strip(),
                }
            )
    return rows


def build_target_events(weeks: list[dict]) -> list[dict]:
    events: list[dict] = []
    for w in weeks:
        ws = w["week_start"]
        loads = _split_load(w["total_tss"])
        times = _split_time(w["hours"])
        desc = f"Lofoten_light coach targets ({w['phase']}). {w['notes']}".strip()
        for sport in _TYPES:
            events.append(
                {
                    "category": "TARGET",
                    "type": sport,
                    "name": "Weekly",
                    "start_date_local": f"{ws}T00:00:00",
                    "load_target": loads[sport],
                    "time_target": times[sport],
                    "distance_target": 0,
                    "external_id": f"ll-agent-target-{ws.replace('-', '')}-{sport.lower()}",
                    "description": desc,
                }
            )
    return events


def fetch_target_ids(oldest: str, newest: str) -> list[int]:
    raw = api_get(f"/athlete/0/events?oldest={oldest}&newest={newest}", timeout=120)
    return [
        int(e["id"])
        for e in json.loads(raw)
        if (e.get("category") or "").upper() == "TARGET"
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Replace Intervals weekly TARGETs from CSV")
    parser.add_argument(
        "--csv",
        type=Path,
        default=_REPO / "plans/csv/intervals-weekly-targets-2026-10-12-12-31.csv",
    )
    parser.add_argument(
        "--delete-from",
        type=str,
        default="2025-01-01",
        help="Delete all TARGET events from this date forward (default all old ATP)",
    )
    parser.add_argument(
        "--delete-to",
        type=str,
        default="2027-12-31",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.dry_run and not api_key():
        print("Set INTERVALS_API", file=sys.stderr)
        return 1

    weeks = load_weeks(args.csv)
    new_events = build_target_events(weeks)
    old_ids = fetch_target_ids(args.delete_from, args.delete_to)

    print(f"CSV weeks: {len(weeks)} → {len(new_events)} TARGET events")
    print(f"Existing TARGET to delete ({args.delete_from}..{args.delete_to}): {len(old_ids)}")

    if args.dry_run:
        for e in new_events[:3]:
            print(" sample:", e["start_date_local"][:10], e["type"], e["load_target"])
        return 0

    if old_ids:
        res = delete_events_bulk(event_ids=old_ids)
        print(f"Deleted old TARGET: {res}")

    for i in range(0, len(new_events), 15):
        batch = new_events[i : i + 15]
        post_events_bulk(batch, upsert=True, dry_run=False)
        print(f"Posted TARGET batch {i // 15 + 1}: {len(batch)} events")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
