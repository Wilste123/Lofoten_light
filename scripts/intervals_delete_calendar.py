#!/usr/bin/env python3
"""Remove agent-pushed plan events from Intervals.icu (by external_id)."""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from intervals_lib import api_key, delete_events_bulk  # noqa: E402
from intervals_push_calendar import external_id  # noqa: E402


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def collect_external_ids(
    plan_start: date,
    plan_path: Path,
    notes_path: Path | None,
) -> list[str]:
    ids: list[str] = []
    for row in load_csv(plan_path):
        sport = (row.get("sport") or "").strip().lower()
        if sport in ("other",) or (row.get("subtype") or "").lower() == "note":
            continue
        day = int(row["day"])
        suffix = (row.get("external_suffix") or "").strip()
        ids.append(external_id(plan_start, day, suffix))

    if notes_path and notes_path.is_file():
        for row in load_csv(notes_path):
            if (row.get("subtype") or "").lower() == "note" or (
                row.get("sport") or ""
            ).lower() == "other":
                ids.append(external_id(plan_start, int(row["day"]), "note"))
    return sorted(set(ids))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Delete Intervals.icu calendar events pushed by intervals_push_calendar.py"
    )
    parser.add_argument(
        "--start",
        type=str,
        required=True,
        help="Plan start date YYYY-MM-DD (same as push --start)",
    )
    parser.add_argument(
        "--plan",
        type=Path,
        default=_REPO / "plans/csv/trainingdojo-4uker-2026-09-28.csv",
    )
    parser.add_argument(
        "--notes",
        type=Path,
        default=_REPO / "plans/csv/trainingdojo-uke-notater-4uker-opv.csv",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List external_ids only, no API call",
    )
    args = parser.parse_args()

    if not args.dry_run and not api_key():
        print(
            "Set INTERVALS_API or INTERVALS_API_KEY (optional INTERVALS_ATHLETE_ID=0).",
            file=sys.stderr,
        )
        return 1

    plan_start = date.fromisoformat(args.start)
    ids = collect_external_ids(plan_start, args.plan, args.notes)
    print(f"Prepared {len(ids)} external_ids for plan start {args.start}")

    if args.dry_run:
        for eid in ids[:8]:
            print(f"  {eid}")
        if len(ids) > 8:
            print(f"  ... +{len(ids) - 8} more")
        return 0

    result = delete_events_bulk(ids)
    deleted = result.get("eventsDeleted", result)
    print(f"Deleted: {deleted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
