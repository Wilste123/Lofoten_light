#!/usr/bin/env python3
"""Push planned workouts from repo CSV to Intervals.icu calendar."""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from intervals_lib import (  # noqa: E402
    SPORT_TO_INTERVALS_TYPE,
    api_key,
    post_events_bulk,
    resolve_bike_zwo_path,
    resolve_planned_session,
    resolve_strength_description,
)


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_bike_by_date(path: Path | None) -> dict[str, str]:
    if not path or not path.is_file():
        return {}
    out: dict[str, str] = {}
    for row in load_csv(path):
        d = (row.get("date") or "").strip()
        zwo = (row.get("zwo_path") or "").strip()
        if d and zwo:
            out[d] = zwo
    return out


def day_to_datetime(plan_start: date, day_index: int, start_time: str) -> str:
    d = plan_start + timedelta(days=day_index - 1)
    hh, mm = start_time.split(":")[:2]
    return f"{d.isoformat()}T{int(hh):02d}:{int(mm):02d}:00"


def external_id(plan_start: date, day_index: int, suffix: str = "") -> str:
    base = f"ll-agent-{plan_start.strftime('%Y%m%d')}-d{day_index:03d}"
    return f"{base}-{suffix}" if suffix else base


def build_workout_event(
    row: dict[str, str],
    plan_start: date,
    start_time: str,
    bike_by_date: dict[str, str],
    repo_root: Path,
) -> dict:
    day = int(row["day"])
    sport_raw = (row.get("sport") or "").strip()
    sport_key = sport_raw.lower()
    title = (row.get("title") or "Workout").strip()
    description = (row.get("description") or "").strip()
    duration_min = int(float(row.get("duration_minutes") or 0))
    tss = row.get("tss")
    event_date = (plan_start + timedelta(days=day - 1)).isoformat()

    icu_type = SPORT_TO_INTERVALS_TYPE.get(sport_key, "Other")
    zwo_explicit = bike_by_date.get(event_date) if sport_key == "bike" else None
    # Run/swim: bike-ZWO shows watts in Intervals — use native HR/pace text only.
    zwo_path = None
    if sport_key == "bike":
        zwo_path = resolve_bike_zwo_path(
            description, sport_raw, repo_root, zwo_explicit
        )

    row_start = (row.get("start_time") or "").strip() or start_time
    suffix = (row.get("external_suffix") or "").strip()
    ev: dict = {
        "category": "WORKOUT",
        "start_date_local": day_to_datetime(plan_start, day, row_start),
        "type": icu_type,
        "name": title,
        "description": description,
        "external_id": external_id(plan_start, day, suffix),
    }
    if duration_min > 0:
        ev["moving_time"] = duration_min * 60
    if tss and str(tss).strip().isdigit():
        ev["icu_training_load"] = int(tss)

    if zwo_path and zwo_path.is_file():
        ev["filename"] = zwo_path.name
        ev["file_contents"] = zwo_path.read_text(encoding="utf-8")
        if sport_key == "run":
            ev["type"] = "Run"
        elif sport_key == "swim":
            ev["type"] = "Swim"
        elif sport_key == "bike":
            ev["type"] = "Ride"
    elif sport_key in ("run", "swim", "bike") and duration_min > 0:
        # Fallback: simple steady block in Intervals workout text
        pct = "Z2 HR" if sport_key != "bike" else "68%"
        ev["description"] = f"- {duration_min}m {pct}\n\n{description}".strip()

    if sport_key == "strength":
        body = resolve_strength_description(description, repo_root)
        if body:
            ev["description"] = body
    else:
        session = resolve_planned_session(description, sport_key, repo_root)
        if session:
            ev["description"] = session

    return ev


def build_note_event(
    row: dict[str, str],
    plan_start: date,
    start_time: str,
) -> dict:
    day = int(row["day"])
    title = (row.get("title") or "Ukenotat").strip()
    description = (row.get("description") or "").strip()
    return {
        "category": "NOTE",
        "start_date_local": day_to_datetime(plan_start, day, start_time),
        "name": title,
        "description": description,
        "color": "blue",
        "external_id": external_id(plan_start, day, "note"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Push plan CSV to Intervals.icu")
    parser.add_argument(
        "--start",
        type=str,
        required=True,
        help="Plan start date YYYY-MM-DD (day 1)",
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
        "--bike-calendar",
        type=Path,
        default=_REPO / "plans/csv/sykkel-zwo-kalender-4uker.csv",
    )
    parser.add_argument(
        "--start-time",
        type=str,
        default="07:00",
        help="Local start time for calendar events (HH:MM)",
    )
    parser.add_argument(
        "--note-time",
        type=str,
        default="19:00",
        help="Local time for weekly NOTE events (HH:MM)",
    )
    parser.add_argument(
        "--chunk",
        type=int,
        default=15,
        help="Events per bulk POST (default 15)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print summary only, no API calls",
    )
    args = parser.parse_args()

    if not args.dry_run and not api_key():
        print(
            "Set INTERVALS_API or INTERVALS_API_KEY (optional INTERVALS_ATHLETE_ID=0).",
            file=sys.stderr,
        )
        return 1

    plan_start = date.fromisoformat(args.start)
    bike_by_date = load_bike_by_date(args.bike_calendar)
    events: list[dict] = []

    for row in load_csv(args.plan):
        sport = (row.get("sport") or "").strip().lower()
        if sport in ("other",) or (row.get("subtype") or "").lower() == "note":
            continue
        events.append(
            build_workout_event(
                row, plan_start, args.start_time, bike_by_date, _REPO
            )
        )

    if args.notes.is_file():
        for row in load_csv(args.notes):
            if (row.get("subtype") or "").lower() == "note" or (
                row.get("sport") or ""
            ).lower() == "other":
                events.append(build_note_event(row, plan_start, args.note_time))

    events.sort(key=lambda e: e["start_date_local"])
    print(f"Prepared {len(events)} calendar events from {args.plan.name}")

    zwo_count = sum(1 for e in events if e.get("file_contents"))
    print(f"  With structured ZWO: {zwo_count}")

    if args.dry_run:
        post_events_bulk(events, dry_run=True)
        for e in events[:5]:
            print(
                f"  {e['start_date_local'][:10]} {e.get('category')} "
                f"{e.get('type', '')} {e.get('name', '')[:50]}"
            )
        if len(events) > 5:
            print(f"  ... +{len(events) - 5} more")
        return 0

    chunk = max(args.chunk, 1)
    for i in range(0, len(events), chunk):
        batch = events[i : i + chunk]
        result = post_events_bulk(batch, upsert=True, dry_run=False)
        print(f"Posted batch {i // chunk + 1}: {len(batch)} events — OK")

    print(
        "Done. Enable Garmin/Wahoo «Upload planned workouts» in Intervals Settings "
        "if not already."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
