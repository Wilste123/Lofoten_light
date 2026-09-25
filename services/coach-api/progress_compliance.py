"""Season volume progress + compliance (deterministic, no LLM).

See docs/product/progress-compliance.md.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from datetime import date
from typing import Any

API_BASE = "https://intervals.icu/api/v1"

DISCIPLINES: tuple[tuple[str, str, str], ...] = (
    ("swim", "Svøm", "season_swim_hours_target"),
    ("bike", "Sykkel", "season_bike_hours_target"),
    ("run", "Løp", "season_run_hours_target"),
    ("strength", "Styrke", "season_strength_hours_target"),
)

# Intervals activity type → discipline id
_TYPE_MAP: dict[str, str] = {
    "swim": "swim",
    "swimworkout": "swim",
    "ride": "bike",
    "virtualride": "bike",
    "gravelride": "bike",
    "mountainbikeride": "bike",
    "ebikeride": "bike",
    "velomobile": "bike",
    "run": "run",
    "virtualrun": "run",
    "trailrun": "run",
    "weighttraining": "strength",
    "workout": "strength",
    "strength": "strength",
}

# Demo stub when no Intervals credentials (clearly labeled in UI)
DEMO_COMPLETED: dict[str, float] = {
    "swim": 28.0,
    "bike": 175.0,
    "run": 62.0,
    "strength": 18.0,
}

DEFAULT_TARGETS: dict[str, float] = {
    "swim": 100.0,
    "bike": 500.0,
    "run": 150.0,
    "strength": 50.0,
}


def compliance_pct(completed_hours: float, target_hours: float | None) -> float | None:
    """MVP: completed / target * 100, capped at 100. None if no target."""
    if target_hours is None or target_hours <= 0:
        return None
    return round(min(100.0, 100.0 * float(completed_hours) / float(target_hours)), 1)


def progress_pct(completed_hours: float, target_hours: float | None) -> float | None:
    """Same ratio as compliance in MVP — kept as alias for clarity in callers/tests."""
    return compliance_pct(completed_hours, target_hours)


def parse_duration_hours(raw: Any, field_hint: str = "") -> float | None:
    """Convert Intervals duration field to hours.

    Seconds if field name contains 'time' and value > 24, or value >= 15.
    Values < 15 treated as already-hours (CSV quirk).
    """
    if raw is None or raw == "":
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val < 0:
        return None
    hint = (field_hint or "").lower()
    if "time" in hint and val > 24:
        return val / 3600.0
    if val < 15:
        return val
    return val / 3600.0


def map_activity_type(type_raw: str | None) -> str | None:
    if not type_raw:
        return None
    key = str(type_raw).strip().lower().replace(" ", "").replace("_", "")
    return _TYPE_MAP.get(key)


def sum_hours_by_discipline(activities: list[dict[str, Any]]) -> dict[str, float]:
    """Sum duration hours per discipline from Intervals activity dicts."""
    totals: dict[str, float] = {d[0]: 0.0 for d in DISCIPLINES}
    for act in activities:
        disc = map_activity_type(act.get("type") or act.get("sport"))
        if not disc:
            continue
        hours = None
        for field in ("moving_time", "elapsed_time", "duration", "icu_coach_time"):
            if act.get(field) is not None and act.get(field) != "":
                hours = parse_duration_hours(act.get(field), field)
                if hours is not None:
                    break
        if hours is None:
            continue
        totals[disc] = totals.get(disc, 0.0) + hours
    return {k: round(v, 2) for k, v in totals.items()}


def _parse_iso_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def season_window(athlete: dict[str, Any], today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    start = _parse_iso_date(athlete.get("season_start_date"))
    if start is None:
        start = date(today.year, 1, 1)
    end = today
    if start > end:
        start = end
    return start, end


def target_for(athlete: dict[str, Any], field: str, demo: bool) -> float | None:
    raw = athlete.get(field)
    if raw is not None and raw != "":
        try:
            val = float(raw)
            return val if val > 0 else None
        except (TypeError, ValueError):
            return None
    if demo:
        # Provide default targets so demo bars render without Du setup
        disc = field.replace("season_", "").replace("_hours_target", "")
        return DEFAULT_TARGETS.get(disc)
    return None


def build_progress_payload(
    athlete: dict[str, Any],
    *,
    completed: dict[str, float],
    source: str,
    session_counts: dict[str, int] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Assemble overview.progress from completed hours + athlete targets."""
    start, end = season_window(athlete, today)
    demo = source == "demo"
    session_counts = session_counts or {}
    disciplines: list[dict[str, Any]] = []
    thin = False
    for disc_id, label, field in DISCIPLINES:
        completed_h = float(completed.get(disc_id) or 0.0)
        target_h = target_for(athlete, field, demo=demo)
        pct = compliance_pct(completed_h, target_h)
        count = session_counts.get(disc_id, 0)
        if source == "intervals" and count < 3 and (target_h or completed_h):
            thin = True
        disciplines.append(
            {
                "id": disc_id,
                "label": label,
                "completed_hours": round(completed_h, 1),
                "target_hours": round(target_h, 1) if target_h is not None else None,
                "progress_pct": pct,
                "compliance_pct": pct,
                "session_count": count,
            }
        )
    return {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "source": source,
        "estimate": thin,
        "disciplines": disciplines,
    }


def demo_progress(athlete: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    return build_progress_payload(
        athlete,
        completed=dict(DEMO_COMPLETED),
        source="demo",
        session_counts={k: 12 for k in DEMO_COMPLETED},
        today=today,
    )


def fetch_intervals_activities(
    api_key: str,
    athlete_id: str,
    oldest: str,
    newest: str,
    *,
    timeout: int = 20,
) -> list[dict[str, Any]]:
    """GET /athlete/{id}/activities?oldest=&newest= — returns list of activity dicts."""
    key = (api_key or "").strip()
    aid = (athlete_id or "").strip()
    if not key or not aid:
        raise ValueError("Mangler Intervals-credentials")
    token = base64.b64encode(f"API_KEY:{key}".encode()).decode()
    url = f"{API_BASE}/athlete/{aid}/activities?oldest={oldest}&newest={newest}"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Basic {token}",
            "User-Agent": "LofotenCoachApi/0.1 (progress)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    data = json.loads(raw) if raw else []
    if isinstance(data, dict):
        # Some endpoints wrap list
        data = data.get("activities") or data.get("data") or []
    if not isinstance(data, list):
        return []
    return data


def count_sessions_by_discipline(activities: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {d[0]: 0 for d in DISCIPLINES}
    for act in activities:
        disc = map_activity_type(act.get("type") or act.get("sport"))
        if disc:
            counts[disc] = counts.get(disc, 0) + 1
    return counts


def resolve_progress(
    athlete: dict[str, Any],
    secrets: dict[str, Any] | None,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """Prefer Intervals when credentials exist; else demo. Soft-fail to demo on error."""
    today = today or date.today()
    start, end = season_window(athlete, today)
    key = ((secrets or {}).get("intervals_api_key") or "").strip()
    aid = ((secrets or {}).get("intervals_athlete_id") or "").strip()
    if not key or not aid:
        return demo_progress(athlete, today)

    try:
        activities = fetch_intervals_activities(
            key, aid, start.isoformat(), end.isoformat()
        )
        completed = sum_hours_by_discipline(activities)
        counts = count_sessions_by_discipline(activities)
        return build_progress_payload(
            athlete,
            completed=completed,
            source="intervals",
            session_counts=counts,
            today=today,
        )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError, OSError):
        payload = demo_progress(athlete, today)
        payload["source"] = "demo"
        payload["fetch_error"] = True
        return payload


def days_to_goal(athlete: dict[str, Any], today: date | None = None) -> int | None:
    today = today or date.today()
    race = _parse_iso_date(athlete.get("goal_race_date"))
    if race is None:
        return None
    return (race - today).days


def pick_current_and_next(
    blocks: list[dict[str, Any]], today: date | None = None
) -> dict[str, Any]:
    """Select current + next plan block. See periodization-overview.md."""
    today = today or date.today()
    parsed: list[tuple[date, date, dict[str, Any]]] = []
    for b in blocks:
        s = _parse_iso_date(b.get("start_date"))
        e = _parse_iso_date(b.get("end_date"))
        if s and e:
            parsed.append((s, e, b))
    parsed.sort(key=lambda t: (t[0], t[1], t[2].get("sort_order") or 0))

    current = None
    for s, e, b in parsed:
        if s <= today <= e:
            current = b
            break
    if current is None:
        past = [(e, b) for s, e, b in parsed if e < today]
        if past:
            past.sort(key=lambda t: t[0], reverse=True)
            current = past[0][1]
        elif parsed:
            upcoming = [(s, b) for s, e, b in parsed if s > today]
            if upcoming:
                upcoming.sort(key=lambda t: t[0])
                current = upcoming[0][1]

    next_block = None
    if current:
        cur_end = _parse_iso_date(current.get("end_date"))
        for s, e, b in parsed:
            if b.get("id") == current.get("id"):
                continue
            if cur_end and s > cur_end:
                next_block = b
                break
            if s > today and (cur_end is None or s >= cur_end):
                next_block = b
                break
    else:
        upcoming = [(s, b) for s, e, b in parsed if s > today]
        if upcoming:
            upcoming.sort(key=lambda t: t[0])
            next_block = upcoming[0][1]

    return {"current": current, "next": next_block}


def public_block(b: dict[str, Any] | None) -> dict[str, Any] | None:
    if not b:
        return None
    return {
        "id": b.get("id"),
        "title": b.get("title") or "",
        "theme": b.get("theme") or "",
        "start_date": b.get("start_date"),
        "end_date": b.get("end_date"),
        "weekly_hours": b.get("weekly_hours"),
        "sort_order": b.get("sort_order") or 0,
    }
