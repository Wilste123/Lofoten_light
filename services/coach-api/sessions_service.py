"""List recent + upcoming sessions from Intervals (activities + events).

Compliance / completion stays app-side — never written to Intervals.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from intervals_calendar import fetch_events
from progress_compliance import (
    DISCIPLINES,
    fetch_intervals_activities,
    map_activity_type,
)


def _disc_label(disc_id: str | None) -> str:
    if not disc_id:
        return "Annet"
    for did, label, _ in DISCIPLINES:
        if did == disc_id:
            return label
    return disc_id


def _activity_local_date(act: dict[str, Any]) -> date | None:
    raw = act.get("start_date_local") or act.get("start_date") or ""
    s = str(raw)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _event_local_date(ev: dict[str, Any]) -> date | None:
    raw = ev.get("start_date_local") or ev.get("start_date") or ""
    s = str(raw)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _duration_hours(act: dict[str, Any]) -> float | None:
    for key in ("moving_time", "elapsed_time", "duration"):
        raw = act.get(key)
        if raw is None or raw == "":
            continue
        try:
            v = float(raw)
        except (TypeError, ValueError):
            continue
        if v < 15:
            return round(v, 2)  # already hours quirk
        return round(v / 3600.0, 2)
    return None


def public_session(
    item: dict[str, Any],
    *,
    completion: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = dict(item)
    if completion:
        out["completion"] = {
            "status": completion.get("status"),
            "reason": completion.get("reason") or "",
            "note": completion.get("note") or "",
            "updated_at": completion.get("updated_at"),
        }
    else:
        out["completion"] = None
    return out


def normalize_activity(act: dict[str, Any]) -> dict[str, Any] | None:
    aid = str(act.get("id") or "").strip()
    if not aid:
        return None
    disc = map_activity_type(act.get("type") or act.get("sport"))
    d = _activity_local_date(act)
    name = (
        act.get("name")
        or act.get("type")
        or act.get("sport")
        or "Aktivitet"
    )
    return {
        "id": f"act:{aid}",
        "external_id": aid,
        "kind": "activity",
        "bucket": "recent",
        "name": str(name),
        "date": d.isoformat() if d else None,
        "start_date_local": act.get("start_date_local") or act.get("start_date"),
        "discipline": disc,
        "discipline_label": _disc_label(disc),
        "type": act.get("type") or act.get("sport"),
        "duration_hours": _duration_hours(act),
        "category": None,
    }


def normalize_event(ev: dict[str, Any], *, today: date) -> dict[str, Any] | None:
    eid = str(ev.get("id") or ev.get("external_id") or "").strip()
    if not eid:
        return None
    # Skip pure coach notes? Keep them — William may ask about plan notes.
    d = _event_local_date(ev)
    cat = (ev.get("category") or ev.get("type") or "").upper()
    name = ev.get("name") or ev.get("title") or cat or "Planlagt økt"
    disc = map_activity_type(ev.get("type") or ev.get("sport") or cat)
    bucket = "upcoming"
    if d and d < today:
        bucket = "recent"
    elif d and d == today:
        bucket = "today"
    return {
        "id": f"evt:{eid}",
        "external_id": eid,
        "kind": "event",
        "bucket": bucket,
        "name": str(name),
        "date": d.isoformat() if d else None,
        "start_date_local": ev.get("start_date_local") or ev.get("start_date"),
        "discipline": disc,
        "discipline_label": _disc_label(disc),
        "type": ev.get("type") or cat,
        "duration_hours": None,
        "category": cat or None,
        "description": (ev.get("description") or "")[:400] or None,
    }


def list_sessions(
    secrets: dict[str, Any] | None,
    completions: dict[str, dict[str, Any]] | None = None,
    *,
    past_days: int = 14,
    future_days: int = 14,
    today: date | None = None,
) -> dict[str, Any]:
    """Soft-fail session list. Never writes to Intervals."""
    today = today or date.today()
    oldest = (today - timedelta(days=past_days)).isoformat()
    newest = (today + timedelta(days=future_days)).isoformat()
    key = ((secrets or {}).get("intervals_api_key") or "").strip()
    aid = ((secrets or {}).get("intervals_athlete_id") or "").strip()
    comps = completions or {}

    base = {
        "window": {"start": oldest, "end": newest},
        "source": "none",
        "fetch_error": False,
        "fetch_error_detail": None,
        "recent": [],
        "upcoming": [],
        "today": [],
        "compliance_note": (
            "Compliance beregnes i appen (aktiviteter vs sesongmål) "
            "— lagres ikke i Intervals."
        ),
    }
    if not key or not aid:
        return base

    recent: list[dict[str, Any]] = []
    upcoming: list[dict[str, Any]] = []
    today_items: list[dict[str, Any]] = []
    errors: list[str] = []

    try:
        activities = fetch_intervals_activities(key, aid, oldest, today.isoformat())
        for act in activities:
            item = normalize_activity(act)
            if not item:
                continue
            comp = comps.get(item["id"]) or comps.get(item["external_id"])
            pub = public_session(item, completion=comp)
            if item.get("date") == today.isoformat():
                today_items.append(pub)
            else:
                recent.append(pub)
    except Exception as exc:  # noqa: BLE001 — soft-fail
        errors.append(f"activities: {exc}")

    try:
        events = fetch_events(key, aid, oldest, newest)
        for ev in events:
            item = normalize_event(ev, today=today)
            if not item:
                continue
            # Skip NOTE category noise unless coach-prefixed plan notes
            cat = (item.get("category") or "").upper()
            if cat == "NOTE" and not str(ev.get("external_id") or "").startswith(
                "ll-coach-"
            ):
                # Keep workout-ish notes; skip empty calendar notes without name
                if not ev.get("name"):
                    continue
            comp = comps.get(item["id"]) or comps.get(item["external_id"])
            pub = public_session(item, completion=comp)
            if item["bucket"] == "upcoming":
                upcoming.append(pub)
            elif item["bucket"] == "today":
                today_items.append(pub)
            else:
                # Past events that aren't already covered as activities
                recent.append(pub)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"events: {exc}")

    def _sort_key(s: dict[str, Any], reverse: bool = False):
        return (s.get("date") or "", s.get("start_date_local") or "")

    recent.sort(key=_sort_key, reverse=True)
    upcoming.sort(key=_sort_key)
    today_items.sort(key=_sort_key)

    out = dict(base)
    out["source"] = "intervals"
    out["recent"] = recent[:40]
    out["upcoming"] = upcoming[:40]
    out["today"] = today_items[:20]
    if errors and not (recent or upcoming or today_items):
        out["fetch_error"] = True
        out["fetch_error_detail"] = "; ".join(errors)[:400]
    elif errors:
        out["fetch_error_detail"] = "; ".join(errors)[:400]
    return out


def seed_chat_prompt(session: dict[str, Any]) -> str:
    """Norwegian prompt seeded into Coach chat about one session."""
    name = session.get("name") or "økten"
    when = session.get("date") or "ukjent dato"
    disc = session.get("discipline_label") or session.get("discipline") or ""
    dur = session.get("duration_hours")
    dur_bit = f", ca. {dur} t" if dur is not None else ""
    comp = session.get("completion") or {}
    status = comp.get("status")
    status_bit = f" Status logget: {status}." if status else ""
    return (
        f"Kan du se på økten «{name}» ({when}"
        f"{f', {disc}' if disc else ''}{dur_bit})?{status_bit} "
        f"Gi kort feedback og hva jeg bør tenke på neste gang."
    )


def completion_note_line(data: dict[str, Any]) -> str:
    """One line appended to athlete notes / profile."""
    when = data.get("session_date") or datetime.utcnow().date().isoformat()
    name = data.get("session_name") or data.get("external_session_id") or "økt"
    status = data.get("status") or "?"
    reason = (data.get("reason") or "").strip()
    note = (data.get("note") or "").strip()
    bits = [f"{when}: {name} → {status}"]
    if reason:
        bits.append(f"grunn={reason}")
    if note:
        bits.append(note)
    return " · ".join(bits)
