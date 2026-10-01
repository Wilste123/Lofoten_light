"""List recent + upcoming sessions from Intervals (activities + events).

Compliance / completion stays app-side — never written to Intervals.

Library view: group distinct workouts (by coach external_id slug or
title+sport) so the same template is not repeated once per calendar day.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from intervals_calendar import WORKOUT_EXTERNAL_PREFIX, fetch_events
from progress_compliance import (
    DISCIPLINES,
    fetch_intervals_activities,
    map_activity_type,
)

# ll-coach-w-YYYYMMDD-slug-N → capture slug
_COACH_W_RE = re.compile(
    rf"^{re.escape(WORKOUT_EXTERNAL_PREFIX)}(\d{{8}})-([a-z0-9]+)-(\d+)$",
    re.IGNORECASE,
)

# ICU calendar categories that are not trainable planned workouts
_CANCELLED_OR_OFF_CATEGORIES = frozenset(
    {
        "HOLIDAY",
        "SICK_DAYS",
        "TRIP",
        "INJURED",
        "SICK",
        "VACATION",
        "SEASON_START",
        "TARGET",
    }
)

# Activity → calendar event link fields (Intervals: paired_event_id is canonical)
_ACTIVITY_EVENT_LINK_KEYS = (
    "paired_event_id",
    "workout_id",
    "icu_workout_id",
    "event_id",
)


def activity_paired_event_ids(act: dict[str, Any]) -> set[str]:
    """ICU ids of calendar events linked to this activity (if any)."""
    out: set[str] = set()
    for key in _ACTIVITY_EVENT_LINK_KEYS:
        raw = act.get(key)
        if raw is None or raw == "":
            continue
        out.add(str(raw).strip())
    return out


def event_icu_id(ev: dict[str, Any]) -> str | None:
    raw = ev.get("id")
    if raw is None or raw == "":
        return None
    return str(raw).strip()


def find_activity_match_for_event(
    *,
    event: dict[str, Any],
    event_date: str | None,
    event_discipline: str | None,
    paired_to_activity: dict[str, str],
    unused_by_date_disc: dict[str, list[str]],
    unused_by_date: dict[str, list[str]],
    used_activity_ids: set[str],
) -> tuple[str | None, str]:
    """Match one planned event to at most one unused ICU activity.

    Priority: paired_event_id → same date+discipline → same date only.
    Returns (activity_external_id, match_method).
    """
    ev_id = event_icu_id(event)
    if ev_id:
        aid = paired_to_activity.get(ev_id)
        if aid and aid not in used_activity_ids:
            return aid, "paired_event_id"
    if event_date:
        disc = event_discipline or ""
        for aid in unused_by_date_disc.get(f"{event_date}|{disc}", []):
            if aid not in used_activity_ids:
                return aid, "date_discipline"
        for aid in unused_by_date.get(event_date, []):
            if aid not in used_activity_ids:
                return aid, "date_only"
    return None, ""


def rolling_session_compliance(
    *,
    activities: list[dict[str, Any]],
    events: list[dict[str, Any]],
    today: date | None = None,
    days: int = 28,
) -> dict[str, Any]:
    """sessions_done / sessions_planned for last N days.

    - sessions_planned = calendar WORKOUT (not NOTE / cancelled categories)
    - sessions_done = planned workouts matched to an ICU **activity**
      (paired_event_id or date/discipline). Numerator never counts NOTES.
    """
    today = today or date.today()
    start = today - timedelta(days=max(1, days) - 1)
    start_s, end_s = start.isoformat(), today.isoformat()

    # Index activities in window
    paired_to_activity: dict[str, str] = {}
    unused_by_date_disc: dict[str, list[str]] = {}
    unused_by_date: dict[str, list[str]] = {}
    activity_dates: dict[str, str | None] = {}
    activity_count = 0
    for act in activities:
        aid = str(act.get("id") or "").strip()
        if not aid:
            continue
        d = _activity_local_date(act)
        if d is None or d < start or d > today:
            continue
        activity_count += 1
        activity_dates[aid] = d.isoformat()
        for peid in activity_paired_event_ids(act):
            paired_to_activity.setdefault(peid, aid)
        disc = map_activity_type(act.get("type") or act.get("sport")) or ""
        ds = d.isoformat()
        unused_by_date_disc.setdefault(f"{ds}|{disc}", []).append(aid)
        unused_by_date.setdefault(ds, []).append(aid)

    used: set[str] = set()
    planned = 0
    done = 0
    cancelled = 0
    match_methods: dict[str, int] = {}
    for ev in events:
        cat = (ev.get("category") or ev.get("type") or "").upper()
        role = calendar_role_for_event(ev, category=cat)
        d = _event_local_date(ev)
        if d is None or d < start or d > today:
            continue
        if role == "cancelled":
            cancelled += 1
            continue
        if role != "planned_workout":
            continue
        planned += 1
        aid, method = find_activity_match_for_event(
            event=ev,
            event_date=d.isoformat(),
            event_discipline=map_activity_type(ev.get("type") or ev.get("sport") or cat),
            paired_to_activity=paired_to_activity,
            unused_by_date_disc=unused_by_date_disc,
            unused_by_date=unused_by_date,
            used_activity_ids=used,
        )
        if aid:
            used.add(aid)
            done += 1
            match_methods[method] = match_methods.get(method, 0) + 1

    ratio = None
    if planned > 0:
        ratio = round(min(100.0, 100.0 * float(done) / float(planned)), 1)
    return {
        "window": {"start": start_s, "end": end_s},
        "days": days,
        "sessions_planned": planned,
        "sessions_done": done,
        "sessions_cancelled_or_off": cancelled,
        "activity_count": activity_count,
        "compliance_pct": ratio,
        "formula": "sessions_done / sessions_planned (done = ICU activity match only)",
        "match_methods": match_methods,
        "note": (
            "4-ukers økt-compliance: planlagte WORKOUT vs matching ICU-aktiviteter. "
            "NOTE og avlyste kategorier teller ikke."
        ),
    }


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
        "calendar_role": "completed_activity",
        "training_status": "completed",
        "description": (act.get("description") or "")[:8000] or None,
        "description_preview": _preview_text(act.get("description") or "", 160),
        "start_time": None,
        "editable": False,
    }


def calendar_role_for_event(ev: dict[str, Any], *, category: str | None = None) -> str:
    """Classify calendar events: note | planned_workout | cancelled | other.

    NOTES are never completed training. WORKOUT / Ride / Run / … are planned.
    HOLIDAY / SICK_DAYS / TRIP / … are cancelled-or-off (not planned volume).
    """
    cat = (category or ev.get("category") or ev.get("type") or "").upper()
    eid = str(ev.get("external_id") or "").strip()
    if cat == "NOTE" or bool(ev.get("show_as_note")):
        return "note"
    # Meso grovplan notes use ll-coach-{block}-{day}; workouts use ll-coach-w-
    if eid.startswith("ll-coach-") and not eid.startswith(WORKOUT_EXTERNAL_PREFIX):
        return "note"
    if cat in _CANCELLED_OR_OFF_CATEGORIES:
        return "cancelled"
    if cat == "WORKOUT" or map_activity_type(ev.get("type") or ev.get("sport") or cat):
        return "planned_workout"
    if cat in ("RACE",):
        return "other"
    return "other"


def normalize_event(ev: dict[str, Any], *, today: date) -> dict[str, Any] | None:
    icu_id = event_icu_id(ev)
    ext = str(ev.get("external_id") or "").strip()
    # Prefer coach/Intervals external_id for stable upsert keys; keep ICU id for pairing
    eid = ext or icu_id or ""
    if not eid:
        return None
    d = _event_local_date(ev)
    cat = (ev.get("category") or ev.get("type") or "").upper()
    name = ev.get("name") or ev.get("title") or cat or "Planlagt økt"
    disc = map_activity_type(ev.get("type") or ev.get("sport") or cat)
    role = calendar_role_for_event(ev, category=cat)
    bucket = "upcoming"
    if d and d < today:
        bucket = "recent"
    elif d and d == today:
        bucket = "today"
    # Default training_status for events — refined in list_sessions after activity match
    if role == "note":
        training_status = "note"
    elif role == "cancelled":
        training_status = "cancelled"
    elif role == "planned_workout":
        if d and d < today:
            training_status = "planned_not_done"
        else:
            training_status = "planned"
    else:
        training_status = "other"
    return {
        "id": f"evt:{eid}",
        "external_id": eid,
        "icu_event_id": icu_id,
        "kind": "event",
        "bucket": bucket,
        "name": str(name),
        "date": d.isoformat() if d else None,
        "start_date_local": ev.get("start_date_local") or ev.get("start_date"),
        "discipline": disc,
        "discipline_label": _disc_label(disc),
        "type": ev.get("type") or cat,
        "duration_hours": _event_duration_hours(ev),
        "category": cat or None,
        "calendar_role": role,
        "training_status": training_status,
        "description": (ev.get("description") or "")[:8000] or None,
        "description_preview": _preview_text(ev.get("description") or "", 160),
        "start_time": _event_start_time(ev),
        "editable": _is_coach_editable(eid, cat),
    }


def _event_duration_hours(ev: dict[str, Any]) -> float | None:
    for key in ("moving_time", "elapsed_time", "icu_moving_time", "duration"):
        raw = ev.get(key)
        if raw is None or raw == "":
            continue
        try:
            v = float(raw)
        except (TypeError, ValueError):
            continue
        if v < 15:
            return round(v, 2)
        return round(v / 3600.0, 2)
    return None


def _event_start_time(ev: dict[str, Any]) -> str | None:
    raw = str(ev.get("start_date_local") or ev.get("start_date") or "")
    if "T" in raw and len(raw) >= 16:
        return raw[11:16]
    return None


def _is_coach_editable(external_id: str, category: str | None) -> bool:
    eid = (external_id or "").strip()
    cat = (category or "").upper()
    if eid.startswith(WORKOUT_EXTERNAL_PREFIX):
        return True
    if eid.startswith("ll-coach-") and cat == "WORKOUT":
        return True
    return False


def _preview_text(text: str, limit: int = 160) -> str | None:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return None
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def parse_coach_steps(description: str | None) -> list[str]:
    """Extract bullet / numbered steps from coach description («Fra treneren»)."""
    structure = parse_session_structure(description)
    steps: list[str] = []
    for phase in structure.get("phases") or []:
        for item in phase.get("items") or []:
            if item and item not in steps:
                steps.append(item)
    return steps[:40]


_PHASE_LABELS = {
    "warmup": "Oppvarming",
    "main": "Hoveddel",
    "cooldown": "Nedkjøling",
    "other": "Øvrig",
}

_WARMUP_RE = re.compile(
    r"^(warmup|oppvarming|wu)\b",
    re.IGNORECASE,
)
_COOLDOWN_RE = re.compile(
    r"^(cooldown|nedkjøling|nedkjoling|nedjogg|cd)\b",
    re.IGNORECASE,
)
_MAIN_RE = re.compile(
    r"^(main(?:\s*set)?|hoveddel|hovedsett)\b",
    re.IGNORECASE,
)
_INTERVAL_RE = re.compile(
    r"^(\d+\s*[x×]\s*\d+|crisscross|elghufs|18\s*[x×]\s*3)",
    re.IGNORECASE,
)


def _intervals_block(description: str) -> str:
    """Prefer Intervals syntax block after --- / ---intervals--- when present."""
    text = description or ""
    if "---intervals---" in text:
        return text.split("---intervals---", 1)[1].strip()
    # format_planned_session_for_intervals: coach markdown + --- + intervals
    if "\n---\n" in text:
        head, tail = text.split("\n---\n", 1)
        # Only treat as intervals block if Warmup/Main/Cooldown-ish lines exist
        if re.search(r"(?im)^(warmup|cooldown|main|- )", tail.strip()):
            return tail.strip()
    return text


def _classify_phase(line: str, current: str) -> str:
    if _WARMUP_RE.match(line):
        return "warmup"
    if _COOLDOWN_RE.match(line):
        return "cooldown"
    if _MAIN_RE.match(line):
        return "main"
    if current == "warmup" and _INTERVAL_RE.match(line):
        return "main"
    if current == "other" and _INTERVAL_RE.match(line):
        return "main"
    return current


def parse_session_structure(description: str | None) -> dict[str, Any]:
    """Warmup / main (intervals) / cooldown structure for detail UI + chat.

    Returns::
        {
          "phases": [{"id": "warmup", "label": "Oppvarming", "items": [...]}, ...],
          "flat_steps": [...],
        }
    """
    empty = {"phases": [], "flat_steps": []}
    if not description:
        return empty
    block = _intervals_block(description)
    buckets: dict[str, list[str]] = {
        "warmup": [],
        "main": [],
        "cooldown": [],
        "other": [],
    }
    current = "other"
    for raw in block.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#") or line.startswith("###"):
            continue
        if line.lower().startswith("plan b"):
            continue
        if line in ("---", "---intervals---"):
            continue
        m = re.match(r"^(?:[-*•]|\d+[.)])\s+(.+)$", line)
        step = m.group(1).strip() if m else line
        if not step:
            continue
        # Header-only lines like "Main:" / "Oppvarming:" switch phase (require colon)
        header = re.match(
            r"^(warmup|oppvarming|main(?:\s*set)?|hoveddel|cooldown|nedkjøling|nedkjoling)\s*:\s*$",
            step,
            re.IGNORECASE,
        )
        if header:
            current = _classify_phase(step, current)
            continue
        current = _classify_phase(step, current)
        if step not in buckets[current]:
            buckets[current].append(step)

    phases: list[dict[str, Any]] = []
    flat: list[str] = []
    for pid in ("warmup", "main", "cooldown", "other"):
        items = buckets[pid]
        if not items:
            continue
        phases.append(
            {
                "id": pid,
                "label": _PHASE_LABELS[pid],
                "items": items,
            }
        )
        flat.extend(items)
    return {"phases": phases, "flat_steps": flat[:40]}


def structure_to_description(structure: dict[str, Any] | None) -> str:
    """Rebuild bullet description from edited phases (for edit preview)."""
    if not structure:
        return ""
    lines: list[str] = []
    for phase in structure.get("phases") or []:
        items = [str(i).strip() for i in (phase.get("items") or []) if str(i).strip()]
        if not items:
            continue
        label = phase.get("label") or _PHASE_LABELS.get(phase.get("id") or "", "")
        if label:
            lines.append(f"{label}:")
        for it in items:
            lines.append(f"- {it}")
        lines.append("")
    return "\n".join(lines).strip()


# Visual øktbygger step types (first-class JSON on planned_sessions.steps_json)
BUILDER_STEP_TYPES = ("warmup", "work", "recover", "cooldown")
BUILDER_STEP_LABELS = {
    "warmup": "Oppvarming",
    "work": "Arbeid",
    "recover": "Pause / restit",
    "cooldown": "Nedkjøling",
}


def normalize_builder_steps(raw: list[Any] | None) -> list[dict[str, Any]]:
    """Validate/normalize visual builder steps."""
    out: list[dict[str, Any]] = []
    for i, item in enumerate(raw or []):
        if not isinstance(item, dict):
            continue
        stype = str(item.get("type") or "work").strip().lower()
        if stype in ("main", "hoveddel", "interval", "intervals"):
            stype = "work"
        if stype in ("rest", "pause", "recovery"):
            stype = "recover"
        if stype not in BUILDER_STEP_TYPES:
            stype = "work"
        try:
            dur = item.get("duration_minutes")
            dur_i = int(float(dur)) if dur is not None and str(dur).strip() != "" else None
        except (TypeError, ValueError):
            dur_i = None
        intensity = str(
            item.get("intensity") or item.get("zone") or item.get("rpe") or ""
        ).strip()[:80]
        note = str(item.get("note") or item.get("text") or item.get("label") or "").strip()[
            :200
        ]
        dist = str(item.get("distance") or "").strip()[:40]
        out.append(
            {
                "id": str(item.get("id") or f"s{i+1}"),
                "type": stype,
                "duration_minutes": dur_i,
                "distance": dist or None,
                "intensity": intensity or None,
                "note": note or None,
                "sort_order": int(item.get("sort_order") if item.get("sort_order") is not None else i),
            }
        )
    out.sort(key=lambda x: x.get("sort_order") or 0)
    for i, s in enumerate(out):
        s["sort_order"] = i
    return out


def builder_steps_to_description(steps: list[dict[str, Any]] | None) -> str:
    """Serialize builder steps → text description (Intervals / legacy)."""
    norm = normalize_builder_steps(steps)
    if not norm:
        return ""
    by_type: dict[str, list[str]] = {t: [] for t in BUILDER_STEP_TYPES}
    for s in norm:
        bits = []
        if s.get("duration_minutes"):
            bits.append(f"{s['duration_minutes']} min")
        if s.get("distance"):
            bits.append(str(s["distance"]))
        if s.get("intensity"):
            bits.append(str(s["intensity"]))
        if s.get("note"):
            bits.append(str(s["note"]))
        line = " · ".join(bits) if bits else BUILDER_STEP_LABELS.get(s["type"], s["type"])
        by_type.setdefault(s["type"], []).append(line)
    lines: list[str] = []
    for t in BUILDER_STEP_TYPES:
        items = by_type.get(t) or []
        if not items:
            continue
        lines.append(f"{BUILDER_STEP_LABELS[t]}:")
        for it in items:
            lines.append(f"- {it}")
        lines.append("")
    return "\n".join(lines).strip()


def builder_steps_from_structure(structure: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Best-effort migrate legacy phase structure → builder steps."""
    if not structure:
        return []
    map_phase = {
        "warmup": "warmup",
        "main": "work",
        "cooldown": "cooldown",
        "other": "work",
    }
    raw: list[dict[str, Any]] = []
    i = 0
    for phase in structure.get("phases") or []:
        pid = map_phase.get(str(phase.get("id") or ""), "work")
        for item in phase.get("items") or []:
            text = str(item).strip()
            if not text:
                continue
            # Try pull leading minutes
            m = re.match(r"^(\d+)\s*(?:min|m)\b", text, re.I)
            dur = int(m.group(1)) if m else None
            raw.append(
                {
                    "id": f"mig{i}",
                    "type": pid,
                    "duration_minutes": dur,
                    "note": text,
                    "sort_order": i,
                }
            )
            i += 1
    return normalize_builder_steps(raw)


def total_builder_duration(steps: list[dict[str, Any]] | None) -> int | None:
    norm = normalize_builder_steps(steps)
    total = sum(int(s["duration_minutes"]) for s in norm if s.get("duration_minutes"))
    return total or None


def library_key_for(session: dict[str, Any]) -> str:
    """Stable key for library grouping (template identity, not calendar day)."""
    eid = str(session.get("external_id") or "").strip()
    m = _COACH_W_RE.match(eid)
    if m:
        slug = m.group(2).lower()
        disc = (session.get("discipline") or "").strip().lower()
        return f"w:{slug}|{disc}"
    name = re.sub(r"\s+", " ", (session.get("name") or "").strip().lower())
    disc = (session.get("discipline") or "").strip().lower()
    kind = (session.get("kind") or "").strip().lower()
    if not name:
        return f"id:{session.get('id') or eid or 'unknown'}"
    return f"n:{name}|{disc}|{kind}"


def _attach_library_meta(item: dict[str, Any]) -> dict[str, Any]:
    out = dict(item)
    out["library_key"] = library_key_for(out)
    structure = parse_session_structure(out.get("description"))
    out["steps"] = structure.get("flat_steps") or parse_coach_steps(out.get("description"))
    out["structure"] = structure
    if out.get("description") and not out.get("description_preview"):
        out["description_preview"] = _preview_text(out["description"], 160)
    return out


def group_library(
    sessions: list[dict[str, Any]],
    *,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Collapse same template into one card with occurrence dates.

    Prefer upcoming/today events; activities without a matching event still
    appear as their own library rows when they are unique.
    """
    today = today or date.today()
    today_s = today.isoformat()
    buckets: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    # Prefer planned events over activities for the same key+date
    ranked = sorted(
        sessions,
        key=lambda s: (
            0 if s.get("kind") == "event" else 1,
            s.get("date") or "9999",
            s.get("name") or "",
        ),
    )

    for raw in ranked:
        item = _attach_library_meta(raw)
        key = item["library_key"]
        d = item.get("date")
        if key not in buckets:
            buckets[key] = {
                "library_key": key,
                "name": item.get("name"),
                "discipline": item.get("discipline"),
                "discipline_label": item.get("discipline_label"),
                "type": item.get("type"),
                "category": item.get("category"),
                "kind": item.get("kind"),
                "description_preview": item.get("description_preview"),
                "editable": bool(item.get("editable")),
                "occurrence_count": 0,
                "dates": [],
                "occurrences": [],
                "next_date": None,
                "representative_id": item.get("id"),
                "sample_session_id": item.get("id"),
            }
            order.append(key)
        entry = buckets[key]
        # Prefer richer description / coach name on the card
        if item.get("description_preview") and (
            not entry.get("description_preview")
            or len(item.get("description_preview") or "")
            > len(entry.get("description_preview") or "")
        ):
            entry["description_preview"] = item.get("description_preview")
        if item.get("kind") == "event":
            entry["kind"] = "event"
            entry["editable"] = entry.get("editable") or bool(item.get("editable"))
            entry["representative_id"] = item.get("id")
            entry["sample_session_id"] = item.get("id")
            if item.get("name"):
                entry["name"] = item.get("name")
            if item.get("discipline_label"):
                entry["discipline_label"] = item.get("discipline_label")
                entry["discipline"] = item.get("discipline")

        # Dedupe same date (activity + event)
        existing_dates = {o.get("date") for o in entry["occurrences"]}
        if d and d in existing_dates:
            # Enrich occurrence with event id if we only had activity
            for occ in entry["occurrences"]:
                if occ.get("date") == d and item.get("kind") == "event":
                    occ["id"] = item.get("id")
                    occ["external_id"] = item.get("external_id")
                    occ["bucket"] = item.get("bucket")
                    occ["completion"] = item.get("completion")
                    occ["editable"] = bool(item.get("editable"))
            continue

        occ = {
            "id": item.get("id"),
            "external_id": item.get("external_id"),
            "date": d,
            "bucket": item.get("bucket"),
            "kind": item.get("kind"),
            "completion": item.get("completion"),
            "editable": bool(item.get("editable")),
        }
        entry["occurrences"].append(occ)
        if d:
            entry["dates"].append(d)
        entry["occurrence_count"] = len(entry["occurrences"])

    library: list[dict[str, Any]] = []
    for key in order:
        entry = buckets[key]
        entry["dates"] = sorted({d for d in entry["dates"] if d})
        entry["occurrences"].sort(key=lambda o: o.get("date") or "")
        future = [d for d in entry["dates"] if d and d >= today_s]
        past = [d for d in entry["dates"] if d and d < today_s]
        entry["next_date"] = future[0] if future else (past[-1] if past else None)
        # Prefer opening the next upcoming occurrence
        next_occ = None
        for o in entry["occurrences"]:
            if o.get("date") and o["date"] >= today_s:
                next_occ = o
                break
        if next_occ:
            entry["sample_session_id"] = next_occ.get("id")
            entry["representative_id"] = next_occ.get("id")
        library.append(entry)

    # Sort: next upcoming first, then name
    def _lib_sort(e: dict[str, Any]) -> tuple:
        nd = e.get("next_date") or "9999-99-99"
        upcoming = 0 if nd >= today_s else 1
        return (upcoming, nd, (e.get("name") or "").lower())

    library.sort(key=_lib_sort)
    return library


def flatten_sessions(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for bucket in (
        "today",
        "upcoming",
        "recent",
        "completed",
        "planned",
        "planned_not_done",
        "notes",
        "cancelled",
    ):
        for s in bundle.get(bucket) or []:
            sid = str(s.get("id") or "")
            if sid and sid in seen:
                continue
            if sid:
                seen.add(sid)
            out.append(s)
    return out


def enrich_sessions_bundle(bundle: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    """Attach library grouping to a list_sessions payload."""
    today = today or date.today()
    out = dict(bundle)
    flat = [_attach_library_meta(s) for s in flatten_sessions(out)]
    # Re-write buckets with library_key / steps
    by_id = {s["id"]: s for s in flat if s.get("id")}
    for bucket in (
        "today",
        "upcoming",
        "recent",
        "completed",
        "planned",
        "planned_not_done",
        "notes",
        "cancelled",
    ):
        out[bucket] = [
            by_id.get(s["id"], _attach_library_meta(s)) for s in (bundle.get(bucket) or [])
        ]
    # Library: planned workouts + activities (exclude pure notes / cancelled-off)
    lib_src = [
        s
        for s in flat
        if s.get("calendar_role") not in ("note", "cancelled")
        and s.get("training_status") not in ("note", "cancelled")
    ]
    out["library"] = group_library(lib_src, today=today)
    out["view_modes"] = ["library", "chronological"]
    out["default_view"] = "library"
    return out


def find_session_in_bundle(
    bundle: dict[str, Any],
    session_id: str,
) -> dict[str, Any] | None:
    sid = session_id.strip()
    for s in flatten_sessions(bundle):
        if s.get("id") == sid or s.get("external_id") == sid:
            return _attach_library_meta(s)
    return None


def session_detail_payload(
    bundle: dict[str, Any],
    session: dict[str, Any],
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """Structured detail for library → detail view."""
    today = today or date.today()
    item = _attach_library_meta(session)
    key = item["library_key"]
    library = group_library(flatten_sessions(bundle), today=today)
    siblings = next((g for g in library if g.get("library_key") == key), None)
    occurrences = (siblings or {}).get("occurrences") or [
        {
            "id": item.get("id"),
            "external_id": item.get("external_id"),
            "date": item.get("date"),
            "bucket": item.get("bucket"),
            "kind": item.get("kind"),
            "completion": item.get("completion"),
            "editable": bool(item.get("editable")),
        }
    ]
    desc = item.get("description") or ""
    structure = item.get("structure") or parse_session_structure(desc)
    steps = item.get("steps") or structure.get("flat_steps") or []
    builder_steps = item.get("builder_steps")
    if not builder_steps:
        builder_steps = builder_steps_from_structure(structure)
    return {
        "session": item,
        "library_key": key,
        "occurrences": occurrences,
        "dates": [o.get("date") for o in occurrences if o.get("date")],
        "description": desc or None,
        "steps": steps,
        "structure": structure,
        "builder_steps": builder_steps,
        "builder_step_types": list(BUILDER_STEP_TYPES),
        "builder_step_labels": dict(BUILDER_STEP_LABELS),
        "coach_block": {
            "title": "Fra treneren",
            "body": desc or None,
            "steps": steps,
            "structure": structure,
        },
        "status": (item.get("completion") or {}).get("status"),
        "editable_fields": {
            "name": item.get("name") or "",
            "date": item.get("date"),
            "sport": item.get("discipline") or "other",
            "duration_minutes": (
                int(round(float(item["duration_hours"]) * 60))
                if item.get("duration_hours") is not None
                else item.get("duration_minutes")
            ),
            "description": desc,
            "builder_steps": builder_steps,
            "warmup": "\n".join(
                (next((p for p in structure.get("phases") or [] if p.get("id") == "warmup"), {})).get(
                    "items"
                )
                or []
            ),
            "main": "\n".join(
                (next((p for p in structure.get("phases") or [] if p.get("id") == "main"), {})).get(
                    "items"
                )
                or []
            ),
            "cooldown": "\n".join(
                (
                    next(
                        (p for p in structure.get("phases") or [] if p.get("id") == "cooldown"),
                        {},
                    )
                ).get("items")
                or []
            ),
            "start_time": item.get("start_time") or "07:00",
            "external_id": item.get("external_id"),
        },
        "editable": bool(item.get("editable")),
        "seed_prompt": seed_chat_prompt(item),
        "compliance_note": bundle.get("compliance_note"),
    }


def session_focus_for_chat(session: dict[str, Any]) -> dict[str, Any]:
    """Compact focused-session strip for knowledge-grounded chat about one økt."""
    structure = session.get("structure") or parse_session_structure(session.get("description"))
    return {
        "id": session.get("id"),
        "external_id": session.get("external_id"),
        "name": session.get("name"),
        "date": session.get("date"),
        "discipline": session.get("discipline_label") or session.get("discipline"),
        "sport": session.get("discipline") or session.get("sport"),
        "kind": session.get("kind"),
        "bucket": session.get("bucket"),
        "duration_hours": session.get("duration_hours"),
        "category": session.get("category"),
        "description": (session.get("description") or "")[:2000] or None,
        "steps": (session.get("steps") or structure.get("flat_steps") or parse_coach_steps(session.get("description")))[
            :20
        ],
        "structure": structure,
        "completion": session.get("completion"),
        "editable": bool(session.get("editable")),
        "library_key": session.get("library_key") or library_key_for(session),
        "note": (
            "Utøveren ser på DENNE økten. Svar konkret om den — knowledge for sporten "
            "er injisert. Ved foreslått endring: bruk workout_proposal med oppdatert "
            "name/date/sport/duration_minutes/description (Warmup/Main/Cooldown-steg). "
            "Samme dato med mindre de ber om å flytte. Ingenting skrives til Intervals "
            "uten bekreftelse."
        ),
    }


def planned_session_to_public(
    row: dict[str, Any],
    *,
    today: date,
    window_start: date,
    window_end: date,
    completion: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Map one SQLite ``planned_sessions`` row → Økter public session shape."""
    day_s = str(row.get("session_date") or "")[:10]
    if not day_s:
        return None
    try:
        d = date.fromisoformat(day_s)
    except ValueError:
        return None
    if d < window_start or d > window_end:
        return None
    name = str(row.get("name") or "Økt").strip() or "Økt"
    sport = str(row.get("sport") or "other").strip().lower() or "other"
    disc = map_activity_type(sport)
    eid = str(row.get("external_id") or "").strip()
    if not eid:
        # Stable local id when chat/setup omitted external_id
        slug = re.sub(r"[^a-z0-9]+", "", name.lower())[:24] or "okt"
        eid = f"{WORKOUT_EXTERNAL_PREFIX}{d.strftime('%Y%m%d')}-{slug}-ps"
    start_time = str(row.get("start_time") or "07:00")[:5] or "07:00"
    dur_m = row.get("duration_minutes")
    try:
        dur_h = round(float(dur_m) / 60.0, 2) if dur_m is not None else None
    except (TypeError, ValueError):
        dur_h = None
    desc = str(row.get("description") or "")[:8000] or None
    if d < today:
        bucket = "recent"
        training_status = "planned_not_done"
    elif d == today:
        bucket = "today"
        training_status = "planned"
    else:
        bucket = "upcoming"
        training_status = "planned"
    item = {
        "id": f"evt:{eid}",
        "external_id": eid,
        "icu_event_id": None,
        "kind": "event",
        "bucket": bucket,
        "name": name[:200],
        "date": day_s,
        "start_date_local": f"{day_s}T{start_time}:00",
        "discipline": disc,
        "discipline_label": _disc_label(disc),
        "type": sport.title() if sport else "Other",
        "duration_hours": dur_h,
        "duration_minutes": int(dur_m) if dur_m is not None else None,
        "category": "WORKOUT",
        "calendar_role": "planned_workout",
        "training_status": training_status,
        "description": desc,
        "description_preview": _preview_text(desc or "", 160),
        "start_time": start_time,
        "editable": True,  # app planned_sessions — visual builder SoT
        "source": "planned_sessions",
        "app_planned": True,
        "planned_row_id": row.get("id"),
        "plan_tier": row.get("plan_tier") or "detalj",
        "builder_steps": row.get("steps")
        if isinstance(row.get("steps"), list)
        else None,
        "planned_path": row.get("planned_path") or row.get("description") or None,
        "phase": row.get("phase") or None,
    }
    if completion:
        item["completion"] = completion
        st = str(completion.get("status") or "")
        if st in ("skipped", "injured", "sick", "tired", "other", "moved", "cancelled"):
            item["training_status"] = st
        elif st == "completed":
            # App overlay only — never invent ICU volume
            item["training_status"] = "app_logged_completed"
            item["volume_counts"] = False
    return item


def merge_planned_sessions(
    bundle: dict[str, Any],
    planned_rows: list[dict[str, Any]] | None,
    *,
    today: date | None = None,
    completions: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Merge app SoT ``planned_sessions`` into Økter list (Plan + Økter same model).

    - Upcoming/today/library show stored plan even without Intervals sync.
    - Dedupes by ``external_id`` against ICU calendar events already present.
    - Never adds to ``completed`` / invents compliance (ICU activities remain truth).
    """
    today = today or date.today()
    rows = list(planned_rows or [])
    if not rows:
        out = dict(bundle)
        out.setdefault("app_planned_merged", 0)
        return out

    win = bundle.get("window") or {}
    try:
        window_start = date.fromisoformat(str(win.get("start") or today.isoformat())[:10])
    except ValueError:
        window_start = today - timedelta(days=14)
    try:
        window_end = date.fromisoformat(str(win.get("end") or today.isoformat())[:10])
    except ValueError:
        window_end = today + timedelta(days=14)

    existing_ext: set[str] = set()
    for bucket in (
        "today",
        "upcoming",
        "planned",
        "planned_not_done",
        "recent",
        "completed",
        "cancelled",
        "notes",
    ):
        for s in bundle.get(bucket) or []:
            eid = str(s.get("external_id") or "").strip()
            if eid:
                existing_ext.add(eid)

    comps = completions or {}
    added_upcoming: list[dict[str, Any]] = []
    added_today: list[dict[str, Any]] = []
    added_missed: list[dict[str, Any]] = []
    for row in rows:
        eid = str(row.get("external_id") or "").strip()
        if eid and eid in existing_ext:
            continue
        comp = None
        if eid:
            comp = comps.get(f"evt:{eid}") or comps.get(eid)
        pub = planned_session_to_public(
            row,
            today=today,
            window_start=window_start,
            window_end=window_end,
            completion=comp,
        )
        if not pub:
            continue
        existing_ext.add(pub["external_id"])
        st = pub.get("training_status")
        if pub["bucket"] == "today":
            added_today.append(pub)
        elif pub["bucket"] == "upcoming":
            added_upcoming.append(pub)
        elif st == "planned_not_done":
            added_missed.append(pub)

    out = dict(bundle)
    if added_upcoming or added_today or added_missed:
        src = out.get("source") or "none"
        if src == "none":
            out["source"] = "planned_sessions"
        elif src == "intervals":
            out["source"] = "intervals+planned_sessions"
        out["upcoming"] = sorted(
            list(out.get("upcoming") or []) + added_upcoming,
            key=lambda s: (s.get("date") or "", s.get("start_date_local") or ""),
        )[:40]
        out["today"] = sorted(
            list(out.get("today") or []) + added_today,
            key=lambda s: (s.get("date") or "", s.get("start_date_local") or ""),
        )[:20]
        out["planned"] = sorted(
            list(out.get("planned") or []) + added_upcoming + added_today,
            key=lambda s: (s.get("date") or "", s.get("start_date_local") or ""),
        )[:40]
        out["planned_not_done"] = sorted(
            list(out.get("planned_not_done") or []) + added_missed,
            key=lambda s: (s.get("date") or "", s.get("start_date_local") or ""),
            reverse=True,
        )[:30]
        note = out.get("compliance_note") or ""
        if "planned_sessions" not in note:
            out["compliance_note"] = (
                (note + " " if note else "")
                + "Planlagte økter inkluderer app-plan (planned_sessions); "
                "gjennomført = fortsatt kun ICU-aktiviteter."
            ).strip()
    out["app_planned_merged"] = len(added_upcoming) + len(added_today) + len(added_missed)
    out["truth"] = {
        **(out.get("truth") or {}),
        "planned_source": "planned_sessions_and_or_intervals",
        "completed_source": "intervals_activities",
    }
    return enrich_sessions_bundle(out, today=today)


def list_sessions(
    secrets: dict[str, Any] | None,
    completions: dict[str, dict[str, Any]] | None = None,
    *,
    past_days: int = 14,
    future_days: int = 14,
    today: date | None = None,
) -> dict[str, Any]:
    """Soft-fail session list. Never writes to Intervals.

    Truth rules:
    - ``completed`` / volume = ICU **activities** only.
    - Calendar NOTES never count as completed (kept under ``notes``).
    - Past WORKOUTs without a matching activity = ``planned_not_done``.
    - App completion status (skipped/moved/…) overlays events when present.
    - Callers should ``merge_planned_sessions`` so Økter shows app plan without ICU.
    """
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
        "partial_fetch": False,
        "recent": [],
        "upcoming": [],
        "today": [],
        "notes": [],
        "planned_not_done": [],
        "completed": [],
        "planned": [],
        "cancelled": [],
        "library": [],
        "view_modes": ["library", "chronological"],
        "default_view": "library",
        "app_planned_merged": 0,
        "compliance_note": (
            "Gjennomført volum = Intervals-aktiviteter (ikke kalender-NOTE, "
            "ikke planlagt WORKOUT uten aktivitet). Compliance beregnes i appen "
            "— lagres ikke i Intervals."
        ),
        "truth": {
            "completed_source": "intervals_activities",
            "notes_never_completed": True,
            "planned_not_activity": True,
            "match_priority": ["paired_event_id", "date_discipline", "date_only"],
        },
        "rolling_compliance_4w": None,
    }
    if not key or not aid:
        return enrich_sessions_bundle(base, today=today)

    completed_acts: list[dict[str, Any]] = []
    upcoming: list[dict[str, Any]] = []
    today_items: list[dict[str, Any]] = []
    notes: list[dict[str, Any]] = []
    planned_not_done: list[dict[str, Any]] = []
    planned_future: list[dict[str, Any]] = []
    cancelled_items: list[dict[str, Any]] = []
    errors: list[str] = []

    # Matching indexes (built from activities; consumed 1:1 per planned event)
    paired_to_activity: dict[str, str] = {}
    unused_by_date_disc: dict[str, list[str]] = {}
    unused_by_date: dict[str, list[str]] = {}
    activity_date_by_id: dict[str, str | None] = {}
    used_activity_ids: set[str] = set()
    raw_activities: list[dict[str, Any]] = []
    raw_events: list[dict[str, Any]] = []

    try:
        activities = fetch_intervals_activities(key, aid, oldest, today.isoformat())
        raw_activities = list(activities)
        for act in activities:
            item = normalize_activity(act)
            if not item:
                continue
            act_eid = item["external_id"]
            activity_date_by_id[act_eid] = item.get("date")
            for peid in activity_paired_event_ids(act):
                paired_to_activity.setdefault(peid, act_eid)
            d = item.get("date")
            disc = item.get("discipline") or ""
            if d:
                unused_by_date_disc.setdefault(f"{d}|{disc}", []).append(act_eid)
                unused_by_date.setdefault(d, []).append(act_eid)
            comp = comps.get(item["id"]) or comps.get(item["external_id"])
            pub = public_session(item, completion=comp)
            # App overlay: skipped etc. still originated as ICU activity
            if comp and comp.get("status") in (
                "skipped",
                "injured",
                "sick",
                "tired",
                "other",
                "moved",
                "cancelled",
            ):
                pub["training_status"] = comp.get("status")
            if d == today.isoformat():
                today_items.append(pub)
            else:
                completed_acts.append(pub)
    except Exception as exc:  # noqa: BLE001 — soft-fail
        errors.append(f"activities: {exc}")

    try:
        events = fetch_events(key, aid, oldest, newest)
        raw_events = list(events)
        for ev in events:
            item = normalize_event(ev, today=today)
            if not item:
                continue
            role = item.get("calendar_role") or "other"
            cat = (item.get("category") or "").upper()
            # Skip anonymous non-coach NOTES
            if role == "note" and not str(ev.get("external_id") or "").startswith(
                "ll-coach-"
            ):
                if not ev.get("name"):
                    continue
            comp = comps.get(item["id"]) or comps.get(item["external_id"])
            pub = public_session(item, completion=comp)

            if role == "note":
                pub["training_status"] = "note"
                notes.append(pub)
                continue

            if role == "cancelled":
                pub["training_status"] = "cancelled"
                # App overlay can refine
                if comp and comp.get("status") in ("moved", "cancelled", "skipped"):
                    pub["training_status"] = str(comp.get("status"))
                cancelled_items.append(pub)
                if item["bucket"] == "upcoming":
                    upcoming.append(pub)
                elif item["bucket"] == "today":
                    today_items.append(pub)
                continue

            # App completion overlay on planned events
            if comp and comp.get("status"):
                st = str(comp.get("status"))
                if st in ("skipped", "injured", "sick", "tired", "other", "moved", "cancelled"):
                    pub["training_status"] = st
                elif st == "completed":
                    # App says done but no ICU activity — still not volume truth;
                    # mark app_logged_completed, keep out of completed activities list.
                    pub["training_status"] = "app_logged_completed"
                    pub["volume_counts"] = False

            if role == "planned_workout":
                # Prefer ICU paired_event_id; fall back to date(+discipline), 1:1
                matched_aid, match_method = find_activity_match_for_event(
                    event=ev,
                    event_date=item.get("date"),
                    event_discipline=item.get("discipline"),
                    paired_to_activity=paired_to_activity,
                    unused_by_date_disc=unused_by_date_disc,
                    unused_by_date=unused_by_date,
                    used_activity_ids=used_activity_ids,
                )
                if matched_aid and pub.get("training_status") in (
                    "planned",
                    "planned_not_done",
                ):
                    used_activity_ids.add(matched_aid)
                    pub["matched_activity_id"] = f"act:{matched_aid}"
                    pub["match_method"] = match_method
                    act_date = activity_date_by_id.get(matched_aid)
                    if (
                        act_date
                        and item.get("date")
                        and act_date != item.get("date")
                    ):
                        pub["training_status"] = "moved"
                        pub["moved_from"] = item.get("date")
                        pub["moved_to"] = act_date
                    else:
                        pub["training_status"] = "matched_activity"
                    # Do not duplicate into completed — activity already listed
                    continue
                if pub.get("training_status") in (
                    "skipped",
                    "moved",
                    "cancelled",
                    "injured",
                    "sick",
                    "tired",
                    "other",
                    "app_logged_completed",
                ):
                    if item["bucket"] == "upcoming":
                        upcoming.append(pub)
                    elif item["bucket"] == "today":
                        today_items.append(pub)
                    else:
                        planned_not_done.append(pub)
                    continue
                if item["bucket"] == "upcoming":
                    pub["training_status"] = "planned"
                    upcoming.append(pub)
                    planned_future.append(pub)
                elif item["bucket"] == "today":
                    pub["training_status"] = "planned"
                    today_items.append(pub)
                    planned_future.append(pub)
                else:
                    # Past planned workout without matching ICU activity
                    pub["training_status"] = "planned_not_done"
                    planned_not_done.append(pub)
                continue

            # other calendar categories (race, …) — not completed training
            if item["bucket"] == "upcoming":
                upcoming.append(pub)
            elif item["bucket"] == "today":
                today_items.append(pub)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"events: {exc}")

    def _sort_key(s: dict[str, Any]):
        return (s.get("date") or "", s.get("start_date_local") or "")

    completed_acts.sort(key=_sort_key, reverse=True)
    upcoming.sort(key=_sort_key)
    today_items.sort(key=_sort_key)
    notes.sort(key=_sort_key, reverse=True)
    planned_not_done.sort(key=_sort_key, reverse=True)
    planned_future.sort(key=_sort_key)
    cancelled_items.sort(key=_sort_key, reverse=True)

    # recent/completed = ICU activities only (incl. today's activities for volume truth)
    today_completed = [
        s for s in today_items if s.get("kind") == "activity" or s.get("training_status") == "completed"
    ]
    recent = list(completed_acts)
    all_completed = recent + today_completed
    all_completed.sort(key=_sort_key, reverse=True)

    rolling = rolling_session_compliance(
        activities=raw_activities,
        events=raw_events,
        today=today,
        days=28,
    )

    out = dict(base)
    out["source"] = "intervals"
    out["recent"] = recent[:40]
    out["completed"] = all_completed[:40]
    out["upcoming"] = upcoming[:40]
    out["today"] = today_items[:20]
    out["notes"] = notes[:30]
    out["planned_not_done"] = planned_not_done[:30]
    out["planned"] = planned_future[:40]
    out["cancelled"] = cancelled_items[:30]
    out["rolling_compliance_4w"] = rolling
    if errors and not (recent or upcoming or today_items or notes or planned_not_done):
        out["fetch_error"] = True
        out["fetch_error_detail"] = "; ".join(errors)[:400]
        out["partial_fetch"] = False
    elif errors:
        # One of activities/events failed — not silent success
        out["partial_fetch"] = True
        out["fetch_error_detail"] = "; ".join(errors)[:400]
    return enrich_sessions_bundle(out, today=today)


def _slim_session(item: dict[str, Any]) -> dict[str, Any]:
    """Compact row for LLM context (no long descriptions)."""
    out: dict[str, Any] = {
        "date": item.get("date"),
        "name": item.get("name"),
        "kind": item.get("kind"),
        "bucket": item.get("bucket"),
        "discipline": item.get("discipline_label") or item.get("discipline"),
    }
    if item.get("duration_hours") is not None:
        out["duration_hours"] = item.get("duration_hours")
    if item.get("category"):
        out["category"] = item.get("category")
    if item.get("calendar_role"):
        out["calendar_role"] = item.get("calendar_role")
    if item.get("training_status"):
        out["training_status"] = item.get("training_status")
    if item.get("match_method"):
        out["match_method"] = item.get("match_method")
    comp = item.get("completion") or {}
    if comp.get("status"):
        out["completion_status"] = comp.get("status")
    return out


def sessions_snapshot_for_chat(
    bundle: dict[str, Any] | None,
    *,
    max_upcoming: int = 14,
    max_recent: int = 10,
    max_today: int = 8,
    max_missed: int = 8,
) -> dict[str, Any]:
    """Deterministic Intervals sessions strip for the single LLM call.

    Separates **planlagt** (calendar WORKOUT) from **gjennomført** (ICU activities).
    NOTES never appear as completed.
    """
    if not bundle:
        return {
            "source": "none",
            "window": None,
            "today": [],
            "upcoming": [],
            "recent": [],
            "planlagt": [],
            "gjennomfort": [],
            "ikke_gjennomfort": [],
            "noter": [],
            "avlyst": [],
            "rolling_compliance_4w": None,
            "note": "Ingen øktdata — Intervals ikke koblet eller tomt vindu.",
        }
    source = bundle.get("source") or "none"
    note = (
        "planlagt = kalender-WORKOUT (ikke volum); gjennomført = ICU-aktiviteter "
        "(eneste kilde til completed volum). NOTE ≠ trening. "
        "ikke_gjennomfort = planlagt WORKOUT uten matching aktivitet "
        "(paired_event_id eller dato+disiplin)."
    )
    if bundle.get("fetch_error"):
        note = (
            f"Henting feilet: {bundle.get('fetch_error_detail') or 'ukjent'}. "
            "Ikke anta økter — be utøveren synce/prøve igjen."
        )
    elif bundle.get("partial_fetch"):
        note = (
            f"Delvis henting: {bundle.get('fetch_error_detail') or 'ukjent'}. "
            "Ikke behandle listen som komplett."
        )
    elif source == "none":
        note = "Intervals ikke koblet — kan ikke svare på konkrete kalenderøkter."

    planned = list(bundle.get("planned") or [])
    if not planned:
        # Fallback: upcoming + today events that are planned workouts
        for s in list(bundle.get("upcoming") or []) + list(bundle.get("today") or []):
            if s.get("kind") == "event" and s.get("calendar_role") != "note":
                if s.get("training_status") in (None, "planned", "planned_not_done"):
                    planned.append(s)
    completed = list(bundle.get("completed") or bundle.get("recent") or [])
    # Never treat notes as completed
    completed = [
        s
        for s in completed
        if s.get("calendar_role") != "note"
        and s.get("training_status") != "note"
        and (s.get("kind") == "activity" or s.get("training_status") == "completed")
    ]
    missed = list(bundle.get("planned_not_done") or [])
    notes = list(bundle.get("notes") or [])
    cancelled = list(bundle.get("cancelled") or [])

    return {
        "source": source,
        "window": bundle.get("window"),
        "today": [_slim_session(s) for s in (bundle.get("today") or [])[:max_today]],
        "upcoming": [
            _slim_session(s) for s in (bundle.get("upcoming") or [])[:max_upcoming]
        ],
        # Legacy aliases — recent MUST stay activities-only after this change
        "recent": [_slim_session(s) for s in (bundle.get("recent") or [])[:max_recent]],
        "planlagt": [_slim_session(s) for s in planned[:max_upcoming]],
        "gjennomfort": [_slim_session(s) for s in completed[:max_recent]],
        "ikke_gjennomfort": [_slim_session(s) for s in missed[:max_missed]],
        "noter": [_slim_session(s) for s in notes[:6]],
        "avlyst": [_slim_session(s) for s in cancelled[:6]],
        "rolling_compliance_4w": bundle.get("rolling_compliance_4w"),
        "partial_fetch": bool(bundle.get("partial_fetch")),
        "fetch_error": bool(bundle.get("fetch_error")),
        "note": note,
    }


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
    steps = session.get("steps") or parse_coach_steps(session.get("description"))
    steps_bit = ""
    if steps:
        steps_bit = " Steg: " + "; ".join(steps[:5]) + "."
    return (
        f"Kan du se på økten «{name}» ({when}"
        f"{f', {disc}' if disc else ''}{dur_bit})?{status_bit}{steps_bit} "
        f"Gi kort feedback, og foreslå konkrete endringer hvis jeg ber om det "
        f"(da med workout_proposal til forhåndsvisning)."
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
