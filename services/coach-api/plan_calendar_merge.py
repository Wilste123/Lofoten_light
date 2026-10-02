"""Merge app ``planned_sessions`` with coach WORKOUT events on Intervals for Plan calendar."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from intervals_calendar import (
    WORKOUT_EXTERNAL_PREFIX,
    event_local_date,
    fetch_events,
    parse_iso_date,
)
from plan_workouts import monday_of, public_planned_session_row

# Sync status labels for UI (Norwegian copy in API for consistency).
SYNC_PLANNED_NOT_SYNCED = "planned_not_synced"
SYNC_SYNCED = "synced"
SYNC_INTERVALS_ONLY = "intervals_only"


def _planned_external_id(row: dict[str, Any]) -> str:
    eid = str(row.get("external_id") or "").strip()
    if eid:
        return eid
    day_s = str(row.get("session_date") or "")[:10]
    name = str(row.get("name") or "okt").strip()
    slug = re.sub(r"[^a-z0-9]+", "", name.lower())[:24] or "okt"
    if day_s:
        return f"{WORKOUT_EXTERNAL_PREFIX}{day_s.replace('-', '')}-{slug}-ps"
    return f"{WORKOUT_EXTERNAL_PREFIX}local-{slug}-ps"


def _is_coach_workout_event(ev: dict[str, Any]) -> bool:
    eid = str(ev.get("external_id") or "").strip()
    if not eid.startswith(WORKOUT_EXTERNAL_PREFIX):
        return False
    cat = str(ev.get("category") or "WORKOUT").upper()
    return cat == "WORKOUT"


def _event_to_calendar_row(ev: dict[str, Any], *, sync_status: str) -> dict[str, Any]:
    d = event_local_date(ev)
    day_s = d.isoformat() if d else str(ev.get("start_date_local") or "")[:10]
    name = str(ev.get("name") or "Økt").strip() or "Økt"
    eid = str(ev.get("external_id") or "").strip()
    return {
        "id": f"icu:{ev.get('id') or eid}",
        "session_date": day_s,
        "name": name[:200],
        "sport": _sport_from_intervals_type(ev.get("type")),
        "duration_minutes": _duration_minutes(ev),
        "external_id": eid,
        "icu_event_id": ev.get("id"),
        "source": "intervals",
        "sync_status": sync_status,
        "sync_status_nb": _status_label_nb(sync_status),
    }


def _sport_from_intervals_type(t: Any) -> str:
    raw = str(t or "").strip().lower()
    mapping = {
        "ride": "bike",
        "run": "run",
        "swim": "swim",
        "weighttraining": "strength",
    }
    return mapping.get(raw, "other")


def _duration_minutes(ev: dict[str, Any]) -> int | None:
    for key in ("moving_time", "duration", "planned_duration"):
        v = ev.get(key)
        if v is None:
            continue
        try:
            sec = int(v)
            if sec > 0:
                return max(1, sec // 60)
        except (TypeError, ValueError):
            continue
    return None


def _status_label_nb(status: str) -> str:
    if status == SYNC_SYNCED:
        return "Synket med Intervals"
    if status == SYNC_INTERVALS_ONLY:
        return "Kun på Intervals (mangler i app-plan)"
    return "Planlagt i app — ikke synket"


def _row_from_planned(
    row: dict[str, Any],
    *,
    sync_status: str,
    icu_event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = public_planned_session_row(row)
    out = {
        **base,
        "sync_status": sync_status,
        "sync_status_nb": _status_label_nb(sync_status),
        "source": "planned_sessions",
    }
    if icu_event:
        out["icu_event_id"] = icu_event.get("id")
        out["intervals_name"] = icu_event.get("name")
    return out


def merge_plan_calendar_sessions(
    planned_rows: list[dict[str, Any]],
    icu_events: list[dict[str, Any]] | None,
    *,
    range_start: date | None = None,
    range_end: date | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Union calendar rows with sync classification (app SoT + ICU coach WORKOUTs)."""
    planned = [public_planned_session_row(r) for r in (planned_rows or [])]
    icu_workouts = [
        e for e in (icu_events or []) if isinstance(e, dict) and _is_coach_workout_event(e)
    ]

    if planned:
        dates = [
            parse_iso_date(str(s.get("session_date") or "")[:10]) for s in planned
        ]
        dates = [d for d in dates if d]
        if dates:
            auto_start = min(dates)
            auto_end = max(dates)
        else:
            auto_start = auto_end = date.today()
    else:
        auto_start = date.today()
        auto_end = date.today() + timedelta(days=56)

    rs = range_start or auto_start
    re = range_end or auto_end
    if re < rs:
        rs, re = re, rs

    icu_by_eid: dict[str, dict[str, Any]] = {}
    for ev in icu_workouts:
        eid = str(ev.get("external_id") or "").strip()
        if not eid:
            continue
        d = event_local_date(ev)
        if d and rs <= d <= re:
            icu_by_eid[eid] = ev

    merged: list[dict[str, Any]] = []
    counts = {SYNC_PLANNED_NOT_SYNCED: 0, SYNC_SYNCED: 0, SYNC_INTERVALS_ONLY: 0}
    used_icu_eids: set[str] = set()

    for row in planned:
        d = parse_iso_date(str(row.get("session_date") or "")[:10])
        if not d or d < rs or d > re:
            continue
        eid = _planned_external_id(row)
        icu = icu_by_eid.get(eid)
        if icu:
            st = SYNC_SYNCED
            used_icu_eids.add(eid)
        else:
            st = SYNC_PLANNED_NOT_SYNCED
        counts[st] += 1
        merged.append(_row_from_planned(row, sync_status=st, icu_event=icu))

    for eid, ev in icu_by_eid.items():
        if eid in used_icu_eids:
            continue
        counts[SYNC_INTERVALS_ONLY] += 1
        merged.append(_event_to_calendar_row(ev, sync_status=SYNC_INTERVALS_ONLY))

    merged.sort(
        key=lambda s: (
            str(s.get("session_date") or ""),
            str(s.get("name") or "").lower(),
        )
    )
    return merged, counts


def fetch_intervals_workouts_for_range(
    secrets: dict[str, Any] | None,
    *,
    range_start: date,
    range_end: date,
) -> list[dict[str, Any]]:
    """Coach WORKOUT events on Intervals in [range_start, range_end] (soft-fail)."""
    sec = secrets or {}
    key = str(sec.get("intervals_api_key") or "").strip()
    aid = str(sec.get("intervals_athlete_id") or "").strip()
    if not key or not aid:
        return []
    try:
        raw = fetch_events(
            key,
            aid,
            oldest=range_start.isoformat(),
            newest=range_end.isoformat(),
        )
    except Exception:  # noqa: BLE001
        return []
    return [e for e in raw if _is_coach_workout_event(e)]


def sessions_in_week_range(
    sessions: list[dict[str, Any]],
    week_start: date,
    week_end: date,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in sessions:
        d = parse_iso_date(str(s.get("session_date") or "")[:10])
        if d and week_start <= d <= week_end:
            out.append(s)
    return sorted(out, key=lambda x: str(x.get("session_date") or ""))


def weekday_indices_from_message(message: str) -> list[int]:
    """0=Monday … 6=Sunday for Norwegian/English day names in text."""
    text = (message or "").lower()
    patterns: list[tuple[str, int]] = [
        (r"\bmandag\b|\bmonday\b", 0),
        (r"\btirsdag\b|\btuesday\b", 1),
        (r"\bonsdag\b|\bwednesday\b", 2),
        (r"\btorsdag\b|\bthursday\b", 3),
        (r"\bfredag\b|\bfriday\b", 4),
        (r"\blør(?:dag)?\b|\bsat(?:urday)?\b", 5),
        (r"\bsøn(?:dag)?\b|\bsun(?:day)?\b", 6),
    ]
    found: list[int] = []
    for pat, idx in patterns:
        if re.search(pat, text):
            found.append(idx)
    return sorted(set(found))


def dates_for_weekday_indices(
    indices: list[int],
    *,
    anchor: date | None = None,
    week_start_key: str = "this_week",
) -> list[date]:
    """Map weekday names → concrete dates in this or next ISO week."""
    if not indices:
        return []
    today = anchor or date.today()
    mon = monday_of(today)
    if str(week_start_key).lower() in ("next_week", "neste_uke"):
        mon += timedelta(days=7)
    return sorted({mon + timedelta(days=i) for i in indices})


def user_requests_weekday_plan_focus(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    # Week surgical adjust (fre–lør / helg) owns those phrases — not day listing.
    from chat_service import (
        user_requests_intervals_plan_sync,
        user_requests_plan_adjust,
        user_requests_session_change,
    )

    if user_requests_session_change(text) or user_requests_intervals_plan_sync(text):
        return False
    if user_requests_plan_adjust(text):
        return False
    if not weekday_indices_from_message(text):
        return False
    return bool(
        re.search(
            r"jus?etr|endre|oppdater|planlegg|hva\s+har\s+jeg|vis|"
            r"legg\s+inn|juster|justere",
            text,
            re.IGNORECASE,
        )
    )
