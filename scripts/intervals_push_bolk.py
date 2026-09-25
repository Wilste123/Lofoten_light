#!/usr/bin/env python3
"""Push bolk / week marker events from ICS (or weekly CSV) to Intervals.icu as NOTE events."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from intervals_lib import api_key, post_events_bulk  # noqa: E402

VEVENT_RE = re.compile(
    r"BEGIN:VEVENT\r?\n(.*?)\r?\nEND:VEVENT",
    re.DOTALL,
)
FIELD_RE = re.compile(r"^([A-Z0-9-]+)(?:;[^:]*)?:(.*)$", re.MULTILINE)


def parse_ics(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    events: list[dict[str, str]] = []
    for block in VEVENT_RE.findall(text):
        fields: dict[str, str] = {}
        for m in FIELD_RE.finditer(block):
            key = m.group(1).split(";")[0]
            val = m.group(2).strip()
            fields[key] = val.replace("\\n", "\n")
        if fields.get("UID"):
            events.append(fields)
    return events


def ics_date_to_local_start(dtstart: str, time_hhmm: str) -> str:
    """VALUE=DATE:20261123 or datetime → local datetime string for API."""
    if "T" in dtstart:
        raw = dtstart.replace("Z", "")
        if len(raw) >= 15:
            return (
                f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
                f"T{raw[9:11]}:{raw[11:13]}:{raw[13:15]}"
            )
    d = dtstart if len(dtstart) == 8 else dtstart.split("T")[0].replace("-", "")
    if len(d) != 8:
        raise ValueError(f"Bad DTSTART: {dtstart}")
    iso = f"{d[0:4]}-{d[4:6]}-{d[6:8]}"
    hh, mm = time_hhmm.split(":")[:2]
    return f"{iso}T{int(hh):02d}:{int(mm):02d}:00"


def external_id_from_uid(uid: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]", "-", uid)
    return f"ll-agent-bolk-{safe}"[:120]


def build_note_from_ics(ev: dict[str, str], start_time: str) -> dict:
    uid = ev.get("UID", "")
    summary = (ev.get("SUMMARY") or "Bolk-markør").strip()
    description = (ev.get("DESCRIPTION") or "").strip()
    dtstart = ev.get("DTSTART", "")
    color = "orange" if "BLOKK" in summary.upper() else "gray"
    body = f"{summary}\n\n{description}" if description else summary
    return {
        "category": "NOTE",
        "start_date_local": ics_date_to_local_start(dtstart, start_time),
        "name": summary[:200],
        "description": body,
        "color": color,
        "external_id": external_id_from_uid(uid),
    }


def build_notes_from_bolk_csv(path: Path, start_time: str) -> list[dict]:
    events: list[dict] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            week_start = (row.get("week_start") or "").strip()
            if not week_start:
                continue
            wn = (row.get("week_number") or "").strip()
            bolk = (row.get("bolk_name") or "").strip()
            theme = (row.get("phase_theme") or "").strip()
            notes = (row.get("notes") or "").strip()
            title = f"Uke {wn} · {bolk}" if wn else bolk
            desc = theme
            if notes:
                desc = f"{theme}\n\n{notes}" if theme else notes
            events.append(
                {
                    "category": "NOTE",
                    "start_date_local": ics_date_to_local_start(
                        week_start.replace("-", ""), start_time
                    ),
                    "name": title[:200],
                    "description": desc or title,
                    "color": "blue",
                    "external_id": f"ll-agent-bolk-week-{week_start}",
                }
            )
    return events


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Push bolk markers to Intervals.icu (NOTE events)"
    )
    parser.add_argument(
        "--ics",
        type=Path,
        default=_REPO / "plans/calendar/2026-bolk-markers.ics",
        help="ICS calendar (default: plans/calendar/2026-bolk-markers.ics)",
    )
    parser.add_argument(
        "--bolk-csv",
        type=Path,
        default=None,
        help="Optional weekly bolk CSV (Monday notes; overlaps ICS week summaries if both used)",
    )
    parser.add_argument(
        "--only-block-boundaries",
        action="store_true",
        help="From ICS: only events whose SUMMARY contains BLOKK",
    )
    parser.add_argument(
        "--skip-ics",
        action="store_true",
        help="Do not read ICS (use with --bolk-csv only)",
    )
    parser.add_argument(
        "--start-time",
        type=str,
        default="06:00",
        help="Local time for NOTE events (HH:MM)",
    )
    parser.add_argument(
        "--chunk",
        type=int,
        default=15,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
    )
    args = parser.parse_args()

    if not args.dry_run and not api_key():
        print(
            "Set INTERVALS_API or INTERVALS_API_KEY (optional INTERVALS_ATHLETE_ID=0).",
            file=sys.stderr,
        )
        return 1

    events: list[dict] = []

    if not args.skip_ics:
        if not args.ics.is_file():
            print(f"Missing ICS: {args.ics}", file=sys.stderr)
            return 1
        for ev in parse_ics(args.ics):
            summary = ev.get("SUMMARY") or ""
            if args.only_block_boundaries and "BLOKK" not in summary.upper():
                continue
            events.append(build_note_from_ics(ev, args.start_time))

    if args.bolk_csv and args.bolk_csv.is_file():
        events.extend(build_notes_from_bolk_csv(args.bolk_csv, args.start_time))

    if not events:
        print("No events to push.", file=sys.stderr)
        return 1

    by_id: dict[str, dict] = {}
    for ev in events:
        by_id[ev["external_id"]] = ev
    events = sorted(by_id.values(), key=lambda e: e["start_date_local"])

    print(f"Prepared {len(events)} bolk NOTE events")

    if args.dry_run:
        post_events_bulk(events, dry_run=True)
        for ev in events[:6]:
            print(f"  {ev['start_date_local'][:10]} {ev['name'][:60]}")
        if len(events) > 6:
            print(f"  ... +{len(events) - 6} more")
        return 0

    chunk = max(args.chunk, 1)
    for i in range(0, len(events), chunk):
        batch = events[i : i + chunk]
        post_events_bulk(batch, upsert=True, dry_run=False)
        print(f"Posted batch {i // chunk + 1}: {len(batch)} events — OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
