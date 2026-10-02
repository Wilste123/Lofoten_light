"""Push / status / delete coach plan-block notes on Intervals calendar.

Patterns adapted from scripts/intervals_push_calendar.py and intervals_lib.py.
Events use external_id prefix ``ll-coach-`` so we can withdraw only agent writes.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any

API_BASE = "https://intervals.icu/api/v1"
EXTERNAL_PREFIX = "ll-coach-"
# Structured calendar workouts (not meso NOTES) — distinct prefix for withdraw.
WORKOUT_EXTERNAL_PREFIX = "ll-coach-w-"
_HTTP_TIMEOUT = 60

SPORT_TO_INTERVALS_TYPE: dict[str, str] = {
    "bike": "Ride",
    "ride": "Ride",
    "sykkel": "Ride",
    "run": "Run",
    "løp": "Run",
    "lop": "Run",
    "swim": "Swim",
    "svøm": "Swim",
    "svom": "Swim",
    "strength": "WeightTraining",
    "styrke": "WeightTraining",
    "weighttraining": "WeightTraining",
    "other": "Other",
}


def _auth_header(api_key: str) -> str:
    token = base64.b64encode(f"API_KEY:{api_key}".encode()).decode()
    return f"Basic {token}"


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": _auth_header(api_key),
        "Content-Type": "application/json",
        "User-Agent": "LofotenCoachApi/0.1 (intervals calendar)",
        "Accept": "application/json",
    }


def external_id_for_block_day(block_id: str, day: date) -> str:
    short = (block_id or "x").replace("-", "")[:12]
    return f"{EXTERNAL_PREFIX}{short}-{day.strftime('%Y%m%d')}"


def parse_iso_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def iter_week_starts(start: date, end: date) -> list[date]:
    """Mondays (or start if mid-week) covering [start, end]."""
    if end < start:
        return []
    # First marker = start_date; then each following Monday
    days = [start]
    # Next Monday strictly after start
    days_until_monday = (7 - start.weekday()) % 7
    cursor = start + timedelta(days=days_until_monday or 7)
    if days_until_monday == 0:
        cursor = start + timedelta(days=7)
    while cursor <= end:
        if cursor != start:
            days.append(cursor)
        cursor += timedelta(days=7)
    return days


def build_block_note_events(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One NOTE per week-start in each block (makro → Intervals, not full workouts)."""
    events: list[dict[str, Any]] = []
    for block in blocks:
        bid = str(block.get("id") or "")
        start = parse_iso_date(block.get("start_date"))
        end = parse_iso_date(block.get("end_date"))
        if not bid or not start or not end:
            continue
        title = (block.get("title") or "Planblokk").strip()
        theme = (block.get("theme") or "").strip()
        wh = block.get("weekly_hours")
        hours_bit = f"{wh} t/uke" if wh is not None else "uketimer ikke satt"
        for day in iter_week_starts(start, end):
            desc = (
                f"### Lofoten Coach — grovplan\n\n"
                f"**{title}** ({start.isoformat()} – {end.isoformat()})\n\n"
                f"Tema: {theme or '—'}\n"
                f"Mål: {hours_bit}\n\n"
                f"_Detaljøkter lever i Intervals — denne noten speiler meso-blokken._"
            )
            events.append(
                {
                    "category": "NOTE",
                    "start_date_local": f"{day.isoformat()}T07:00:00",
                    "name": f"Plan: {title}",
                    "description": desc,
                    "color": "blue",
                    "external_id": external_id_for_block_day(bid, day),
                    "_block_id": bid,
                    "_block_title": title,
                    "_day": day.isoformat(),
                }
            )
    return events


def public_event_preview(ev: dict[str, Any]) -> dict[str, Any]:
    return {
        "external_id": ev.get("external_id"),
        "name": ev.get("name"),
        "start_date_local": ev.get("start_date_local"),
        "category": ev.get("category"),
        "type": ev.get("type"),
        "block_id": ev.get("_block_id"),
        "block_title": ev.get("_block_title"),
        "day": ev.get("_day"),
    }


def external_id_for_workout(day: date, name: str, index: int = 0) -> str:
    """Stable-ish id from date + name slug (upsert-friendly within a day)."""
    slug = "".join(ch for ch in (name or "okt").lower() if ch.isalnum())[:16] or "okt"
    return f"{WORKOUT_EXTERNAL_PREFIX}{day.strftime('%Y%m%d')}-{slug}-{index}"


def build_workout_events(
    workouts: list[dict[str, Any]],
    *,
    athlete: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """ICU WORKOUT events via the Cursor/CLI builder — not a thin NOTE-like stub.

    Delegates to ``plan_workouts.icu_events_from_chat_workouts`` →
    ``scripts/intervals_push_calendar.build_workout_event`` so name, duration,
    moving_time, and ---intervals--- / planned-path structure match Plan Sync.
    """
    # Lazy import avoids circular import with plan_workouts.
    from plan_workouts import icu_events_from_chat_workouts

    return icu_events_from_chat_workouts(workouts, athlete=athlete)


def strip_internal(ev: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in ev.items() if not str(k).startswith("_")}


def post_events_bulk(
    api_key: str,
    athlete_id: str,
    events: list[dict[str, Any]],
    *,
    upsert: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    clean = [strip_internal(e) for e in events]
    if dry_run:
        return {"dry_run": True, "count": len(clean), "sample": clean[:3]}
    if not clean:
        return {"count": 0, "events": []}
    qs = "?upsert=true" if upsert else ""
    url = f"{API_BASE}/athlete/{athlete_id.strip()}/events/bulk{qs}"
    body = json.dumps(clean).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST", headers=_headers(api_key)
    )
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if not raw:
                return {"status": resp.status, "count": len(clean)}
            parsed = json.loads(raw)
            return {"response": parsed, "count": len(clean)}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"Intervals API {e.code}: {detail}") from e


def delete_events_bulk(
    api_key: str,
    athlete_id: str,
    external_ids: list[str],
) -> dict[str, Any]:
    if not external_ids:
        return {"eventsDeleted": 0}
    unique = sorted(set(external_ids))
    url = f"{API_BASE}/athlete/{athlete_id.strip()}/events/bulk-delete"
    body = json.dumps([{"external_id": eid} for eid in unique]).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="PUT", headers=_headers(api_key)
    )
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if not raw:
                return {"status": resp.status, "eventsDeleted": len(unique)}
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
            return {"eventsDeleted": len(unique), "response": parsed}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"Intervals API {e.code}: {detail}") from e


def fetch_events(
    api_key: str,
    athlete_id: str,
    oldest: str,
    newest: str,
) -> list[dict[str, Any]]:
    qs = urllib.parse.urlencode({"oldest": oldest, "newest": newest})
    url = f"{API_BASE}/athlete/{athlete_id.strip()}/events?{qs}"
    req = urllib.request.Request(url, method="GET", headers=_headers(api_key))
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if not raw:
                return []
            data = json.loads(raw)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"Intervals API {e.code}: {detail}") from e
    if isinstance(data, dict):
        data = data.get("events") or data.get("data") or []
    if not isinstance(data, list):
        return []
    return [e for e in data if isinstance(e, dict)]


def filter_coach_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ev in events:
        eid = str(ev.get("external_id") or "")
        if eid.startswith(EXTERNAL_PREFIX):
            out.append(
                {
                    "id": ev.get("id"),
                    "external_id": eid,
                    "name": ev.get("name"),
                    "start_date_local": ev.get("start_date_local"),
                    "category": ev.get("category"),
                }
            )
    return out


def event_local_date(ev: dict[str, Any]) -> date | None:
    raw = ev.get("_day") or str(ev.get("start_date_local") or "")[:10]
    return parse_iso_date(str(raw)[:10] if raw else None)


def filter_events_in_date_range(
    events: list[dict[str, Any]],
    range_start: date,
    range_end: date,
) -> list[dict[str, Any]]:
    if range_end < range_start:
        return []
    out: list[dict[str, Any]] = []
    for ev in events:
        d = event_local_date(ev)
        if d and range_start <= d <= range_end:
            out.append(ev)
    return out


def select_blocks(
    all_blocks: list[dict[str, Any]],
    *,
    block_ids: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, Any]]:
    """Filter plan blocks by id list and/or overlapping date range."""
    selected = list(all_blocks)
    if block_ids:
        wanted = set(block_ids)
        selected = [b for b in selected if b.get("id") in wanted]
    range_start = parse_iso_date(start)
    range_end = parse_iso_date(end)
    if range_start or range_end:
        filtered: list[dict[str, Any]] = []
        for b in selected:
            bs = parse_iso_date(b.get("start_date"))
            be = parse_iso_date(b.get("end_date"))
            if not bs or not be:
                continue
            if range_start and be < range_start:
                continue
            if range_end and bs > range_end:
                continue
            filtered.append(b)
        selected = filtered
    return selected


def status_window_for_blocks(blocks: list[dict[str, Any]], today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    dates: list[date] = []
    for b in blocks:
        s = parse_iso_date(b.get("start_date"))
        e = parse_iso_date(b.get("end_date"))
        if s:
            dates.append(s)
        if e:
            dates.append(e)
    if not dates:
        return today - timedelta(days=14), today + timedelta(days=60)
    return min(dates), max(dates)
