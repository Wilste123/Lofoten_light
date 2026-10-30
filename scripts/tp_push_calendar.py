#!/usr/bin/env python3
"""Push TrainingDojo-format CSV to TrainingPeaks calendar (Partner / bearer token)."""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, timedelta
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO = _SCRIPT_DIR.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from intervals_lib import (  # noqa: E402
    resolve_planned_session,
    resolve_strength_description,
)
from tp_lib import athlete_id, plan_workout, sport_to_workout_type  # noqa: E402


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def resolve_description(row: dict[str, str], repo: Path) -> str:
    desc = (row.get("description") or "").strip()
    sport = (row.get("sport") or "").lower()
    if sport == "strength":
        full = resolve_strength_description(desc, repo)
        if full:
            return full
    if sport in ("run", "swim", "bike", "other"):
        full = resolve_planned_session(desc, repo)
        if full:
            return full
    return desc


def build_payload(
    row: dict[str, str],
    plan_start: date,
    aid: int,
    repo: Path,
) -> dict:
    day = int(row["day"])
    wday = (plan_start + timedelta(days=day - 1)).isoformat()
    sport = (row.get("sport") or "Other").strip()
    title = (row.get("title") or "Workout").strip()
    duration_min = float(row.get("duration_minutes") or 0)
    tss = row.get("tss")
    start_time = (row.get("start_time") or "").strip()

    payload: dict = {
        "AthleteId": aid,
        "WorkoutDay": wday,
        "WorkoutType": sport_to_workout_type(sport),
        "Title": title,
        "Description": resolve_description(row, repo),
    }
    if duration_min > 0:
        payload["TotalTimePlanned"] = round(duration_min / 60.0, 3)
    if tss and str(tss).strip().replace(".", "", 1).isdigit():
        payload["TSSPlanned"] = float(tss)
    if start_time and ":" in start_time:
        hh, mm = start_time.split(":")[:2]
        payload["StartTimePlanned"] = f"{wday}T{int(hh):02d}:{int(mm):02d}:00"
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="trainingdojo-*.csv")
    parser.add_argument(
        "--plan-start",
        required=True,
        help="First day = CSV day 1 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print payloads, do not POST",
    )
    args = parser.parse_args()
    plan_start = date.fromisoformat(args.plan_start)
    rows = load_csv(args.csv)
    aid = athlete_id()

    ok = 0
    for row in rows:
        sport = (row.get("sport") or "").strip().lower()
        if sport == "other" and "note" in (row.get("title") or "").lower():
            continue
        payload = build_payload(row, plan_start, aid, _REPO)
        if args.dry_run:
            print(json_dumps(payload))
            ok += 1
            continue
        plan_workout(payload)
        ok += 1
        print(f"Planned: {payload['WorkoutDay']} {payload['Title']}")

    print(f"Done: {ok} workout(s)")
    return 0


def json_dumps(obj: dict) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    raise SystemExit(main())
