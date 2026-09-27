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
        "description": (act.get("description") or "")[:8000] or None,
        "description_preview": _preview_text(act.get("description") or "", 160),
        "start_time": None,
        "editable": False,
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
        "duration_hours": _event_duration_hours(ev),
        "category": cat or None,
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
    for bucket in ("today", "upcoming", "recent"):
        for s in bundle.get(bucket) or []:
            out.append(s)
    return out


def enrich_sessions_bundle(bundle: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    """Attach library grouping to a list_sessions payload."""
    today = today or date.today()
    out = dict(bundle)
    flat = [_attach_library_meta(s) for s in flatten_sessions(out)]
    # Re-write buckets with library_key / steps
    by_id = {s["id"]: s for s in flat if s.get("id")}
    for bucket in ("today", "upcoming", "recent"):
        out[bucket] = [by_id.get(s["id"], _attach_library_meta(s)) for s in (bundle.get(bucket) or [])]
    out["library"] = group_library(flat, today=today)
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
    return {
        "session": item,
        "library_key": key,
        "occurrences": occurrences,
        "dates": [o.get("date") for o in occurrences if o.get("date")],
        "description": desc or None,
        "steps": steps,
        "structure": structure,
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
                else None
            ),
            "description": desc,
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
        "library": [],
        "view_modes": ["library", "chronological"],
        "default_view": "library",
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
) -> dict[str, Any]:
    """Deterministic Intervals sessions strip for the single LLM call."""
    if not bundle:
        return {
            "source": "none",
            "window": None,
            "today": [],
            "upcoming": [],
            "recent": [],
            "note": "Ingen øktdata — Intervals ikke koblet eller tomt vindu.",
        }
    source = bundle.get("source") or "none"
    note = (
        "Kommende = planlagte kalenderhendelser; recent = fullførte aktiviteter "
        "(og evt. passerte events). Detaljer eies av Intervals."
    )
    if bundle.get("fetch_error"):
        note = f"Henting feilet: {bundle.get('fetch_error_detail') or 'ukjent'}"
    elif source == "none":
        note = "Intervals ikke koblet — kan ikke svare på konkrete kalenderøkter."
    return {
        "source": source,
        "window": bundle.get("window"),
        "today": [_slim_session(s) for s in (bundle.get("today") or [])[:max_today]],
        "upcoming": [
            _slim_session(s) for s in (bundle.get("upcoming") or [])[:max_upcoming]
        ],
        "recent": [_slim_session(s) for s in (bundle.get("recent") or [])[:max_recent]],
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
