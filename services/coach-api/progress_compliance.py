"""Season volume progress + compliance (deterministic, no LLM).

See docs/product/progress-compliance.md.

Formula (stable):
  completed_h   = sum(duration_hours for discipline in [season_start … today])
  target_h      = season_{discipline}_hours_target
  progress_pct  = 0 if target_h <= 0 else min(100, 100 * completed_h / target_h)
  compliance_pct = progress_pct   # same ratio — «fullført av sesongmål»

On-pace (when season_start + goal_race_date exist):
  elapsed_days = max(1, (today − season_start).days + 1)
  season_days  = max(1, (goal_race_date − season_start).days)
  expected_h   = target_h * elapsed_days / season_days
  on_pace_pct  = 100 * completed_h / expected_h   (not capped; shows ahead/behind)
  on_pace_note = Norwegian short status vs expected
"""

from __future__ import annotations

import base64
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
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

# Intervals list endpoint can truncate; page with limit + shrinking newest.
_PAGE_LIMIT = 100
_ACTIVITY_FIELDS = "id,type,sport,moving_time,elapsed_time,duration,start_date_local"
_FETCH_TIMEOUT = 12
_CACHE_TTL_SEC = 120

_cache_lock = threading.Lock()
_progress_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def compliance_pct(completed_hours: float, target_hours: float | None) -> float | None:
    """completed / target * 100, capped at 100. None if no target."""
    if target_hours is None or target_hours <= 0:
        return None
    return round(min(100.0, 100.0 * float(completed_hours) / float(target_hours)), 1)


def progress_pct(completed_hours: float, target_hours: float | None) -> float | None:
    """Same ratio as compliance — alias for callers/tests."""
    return compliance_pct(completed_hours, target_hours)


def on_pace_metrics(
    completed_hours: float,
    target_hours: float | None,
    *,
    season_start: date | None,
    goal_race: date | None,
    today: date | None = None,
) -> dict[str, Any]:
    """Compare completed hours to linear expected volume toward race day.

    Formula:
      expected_h = target_h * elapsed_days / season_days
      on_pace_pct = 100 * completed_h / expected_h
    """
    today = today or date.today()
    empty: dict[str, Any] = {
        "expected_hours": None,
        "on_pace_pct": None,
        "on_pace": None,
        "on_pace_note": None,
        "elapsed_days": None,
        "season_days": None,
    }
    if (
        target_hours is None
        or target_hours <= 0
        or season_start is None
        or goal_race is None
    ):
        return empty
    if goal_race <= season_start:
        return empty
    if today < season_start:
        return {
            **empty,
            "expected_hours": 0.0,
            "on_pace_pct": None,
            "on_pace": True,
            "on_pace_note": "Sesong ikke startet",
            "elapsed_days": 0,
            "season_days": (goal_race - season_start).days,
        }
    season_days = max(1, (goal_race - season_start).days)
    elapsed_days = max(1, (today - season_start).days + 1)
    elapsed_days = min(elapsed_days, season_days)
    expected = float(target_hours) * float(elapsed_days) / float(season_days)
    if expected <= 0:
        return empty
    ratio_pct = round(100.0 * float(completed_hours) / expected, 1)
    delta_pct = round(ratio_pct - 100.0, 1)
    on_pace = ratio_pct >= 95.0
    if abs(delta_pct) < 5:
        note = "På plan"
    elif delta_pct > 0:
        note = f"Foran plan (+{delta_pct:.0f} %)"
    else:
        note = f"Bak plan ({delta_pct:.0f} %)"
    return {
        "expected_hours": round(expected, 1),
        "on_pace_pct": ratio_pct,
        "on_pace": on_pace,
        "on_pace_note": note,
        "elapsed_days": elapsed_days,
        "season_days": season_days,
    }


def parse_duration_hours(raw: Any, field_hint: str = "") -> float | None:
    """Convert Intervals duration field to hours.

    Seconds if field name contains 'time' and value > 24, or value >= 15.
    Values < 15 treated as already-hours (CSV-quirk).
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


def _activity_local_date(act: dict[str, Any]) -> date | None:
    raw = act.get("start_date_local") or act.get("start_date") or act.get("date")
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        if "T" in text:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def season_window(athlete: dict[str, Any], today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    start = _parse_iso_date(athlete.get("season_start_date"))
    if start is None:
        start = date(today.year, 1, 1)
    end = today
    if start > end:
        # Sesong ikke startet — tomt vindu (ingen fetch-trøbbel på fremtidig start)
        return start, start
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
    fetch_error: bool = False,
    fetch_error_detail: str | None = None,
    activity_count: int | None = None,
) -> dict[str, Any]:
    """Assemble overview.progress from completed hours + athlete targets."""
    today = today or date.today()
    start, end = season_window(athlete, today)
    season_start = _parse_iso_date(athlete.get("season_start_date"))
    season_not_started = bool(season_start and season_start > today)
    demo = source == "demo"
    session_counts = session_counts or {}
    race = _parse_iso_date(athlete.get("goal_race_date"))
    disciplines: list[dict[str, Any]] = []
    thin = False
    for disc_id, label, field in DISCIPLINES:
        completed_h = float(completed.get(disc_id) or 0.0)
        target_h = target_for(athlete, field, demo=demo)
        pct = compliance_pct(completed_h, target_h)
        pace = on_pace_metrics(
            completed_h,
            target_h,
            season_start=season_start,
            goal_race=race,
            today=today,
        )
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
                "expected_hours": pace["expected_hours"],
                "on_pace_pct": pace["on_pace_pct"],
                "on_pace": pace["on_pace"],
                "on_pace_note": pace["on_pace_note"],
            }
        )
    total_sessions = (
        activity_count
        if activity_count is not None
        else sum(session_counts.values())
    )
    payload: dict[str, Any] = {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "source": source,
        "estimate": thin,
        "season_not_started": season_not_started,
        "activity_count": total_sessions,
        "formula": "completed_hours / season_target_hours (capped 100%)",
        "on_pace_formula": (
            "expected = target * elapsed_days / season_days; "
            "on_pace_pct = 100 * completed / expected"
        ),
        "disciplines": disciplines,
    }
    if fetch_error:
        payload["fetch_error"] = True
        payload["retryable"] = True
        if fetch_error_detail:
            payload["fetch_error_detail"] = fetch_error_detail[:200]
        payload["offline_or_error_note"] = (
            "Intervals-henting feilet — completed=0 (ikke demo-timer). "
            "Prøv igjen; cache tømmes automatisk etter TTL."
        )
    return payload


def demo_progress(athlete: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    return build_progress_payload(
        athlete,
        completed=dict(DEMO_COMPLETED),
        source="demo",
        session_counts={k: 12 for k in DEMO_COMPLETED},
        today=today,
    )


def empty_progress(
    athlete: dict[str, Any],
    *,
    source: str,
    today: date | None = None,
    fetch_error: bool = False,
    fetch_error_detail: str | None = None,
) -> dict[str, Any]:
    """Zero completed hours — used when linked but no data / fetch failed."""
    zeros_h = {d[0]: 0.0 for d in DISCIPLINES}
    zeros_n = {d[0]: 0 for d in DISCIPLINES}
    return build_progress_payload(
        athlete,
        completed=zeros_h,
        source=source,
        session_counts=zeros_n,
        today=today,
        fetch_error=fetch_error,
        fetch_error_detail=fetch_error_detail,
        activity_count=0,
    )


def _auth_headers(api_key: str) -> dict[str, str]:
    token = base64.b64encode(f"API_KEY:{api_key}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "User-Agent": "LofotenCoachApi/0.1 (progress)",
        "Accept": "application/json",
    }


def _http_get_json(url: str, api_key: str, *, timeout: int = _FETCH_TIMEOUT) -> Any:
    req = urllib.request.Request(
        url,
        method="GET",
        headers=_auth_headers(api_key),
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    if not raw:
        return []
    return json.loads(raw)


def fetch_intervals_activities_page(
    api_key: str,
    athlete_id: str,
    oldest: str,
    newest: str,
    *,
    limit: int = _PAGE_LIMIT,
    timeout: int = _FETCH_TIMEOUT,
) -> list[dict[str, Any]]:
    """Single page GET /athlete/{id}/activities."""
    key = (api_key or "").strip()
    aid = (athlete_id or "").strip()
    if not key or not aid:
        raise ValueError("Mangler Intervals-credentials")
    qs = urllib.parse.urlencode(
        {
            "oldest": oldest,
            "newest": newest,
            "limit": str(limit),
            "fields": _ACTIVITY_FIELDS,
        }
    )
    url = f"{API_BASE}/athlete/{aid}/activities?{qs}"
    data = _http_get_json(url, key, timeout=timeout)
    if isinstance(data, dict):
        data = data.get("activities") or data.get("data") or []
    if not isinstance(data, list):
        return []
    return [a for a in data if isinstance(a, dict)]


def fetch_intervals_activities(
    api_key: str,
    athlete_id: str,
    oldest: str,
    newest: str,
    *,
    timeout: int = _FETCH_TIMEOUT,
    page_limit: int = _PAGE_LIMIT,
) -> list[dict[str, Any]]:
    """GET activities for [oldest, newest], paging when Intervals truncates.

    Walks newest→oldest in pages of ``page_limit``. Dedupes by activity id.
    """
    oldest_d = date.fromisoformat(oldest[:10])
    newest_d = date.fromisoformat(newest[:10])
    if oldest_d > newest_d:
        return []

    collected: list[dict[str, Any]] = []
    seen: set[str] = set()
    cursor_newest = newest_d
    # Safety: season-long fetch should not loop forever
    for _ in range(40):
        batch = fetch_intervals_activities_page(
            api_key,
            athlete_id,
            oldest_d.isoformat(),
            cursor_newest.isoformat(),
            limit=page_limit,
            timeout=timeout,
        )
        if not batch:
            break
        new_in_batch = 0
        oldest_in_batch: date | None = None
        for act in batch:
            aid = str(act.get("id") or "")
            if aid and aid in seen:
                continue
            if aid:
                seen.add(aid)
            collected.append(act)
            new_in_batch += 1
            ad = _activity_local_date(act)
            if ad is not None and (oldest_in_batch is None or ad < oldest_in_batch):
                oldest_in_batch = ad
        if len(batch) < page_limit or oldest_in_batch is None:
            break
        # Next page: everything strictly older than oldest in this page
        next_newest = oldest_in_batch - timedelta(days=1)
        if next_newest < oldest_d or new_in_batch == 0:
            break
        cursor_newest = next_newest
    return collected


def count_sessions_by_discipline(activities: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {d[0]: 0 for d in DISCIPLINES}
    for act in activities:
        disc = map_activity_type(act.get("type") or act.get("sport"))
        if disc:
            counts[disc] = counts.get(disc, 0) + 1
    return counts


def _cache_key(athlete_id: str, api_key: str, start: date, end: date) -> str:
    # Key includes key suffix so rotated credentials bust cache
    return f"{athlete_id}|{api_key[-6:]}|{start.isoformat()}|{end.isoformat()}"


def clear_progress_cache() -> None:
    with _cache_lock:
        _progress_cache.clear()


def resolve_progress(
    athlete: dict[str, Any],
    secrets: dict[str, Any] | None,
    *,
    today: date | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Prefer Intervals when credentials exist; else demo.

    Soft-fail when linked: zeros + fetch_error (not fake demo hours).
    """
    today = today or date.today()
    start, end = season_window(athlete, today)
    key = ((secrets or {}).get("intervals_api_key") or "").strip()
    aid = ((secrets or {}).get("intervals_athlete_id") or "").strip()
    if not key or not aid:
        return demo_progress(athlete, today)

    # Sesong ikke startet — ingen ICU-kall, tomme tall merket Intervals
    season_start = _parse_iso_date(athlete.get("season_start_date"))
    if season_start and season_start > today:
        return empty_progress(athlete, source="intervals", today=today)

    cache_id = _cache_key(aid, key, start, end)
    if use_cache:
        with _cache_lock:
            hit = _progress_cache.get(cache_id)
            if hit and (time.time() - hit[0]) < _CACHE_TTL_SEC:
                return dict(hit[1])

    try:
        activities = fetch_intervals_activities(
            key, aid, start.isoformat(), end.isoformat()
        )
        completed = sum_hours_by_discipline(activities)
        counts = count_sessions_by_discipline(activities)
        payload = build_progress_payload(
            athlete,
            completed=completed,
            source="intervals",
            session_counts=counts,
            today=today,
            activity_count=len(activities),
        )
        if use_cache:
            with _cache_lock:
                _progress_cache[cache_id] = (time.time(), dict(payload))
        return payload
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        ValueError,
        json.JSONDecodeError,
        OSError,
    ) as exc:
        detail = str(exc) or exc.__class__.__name__
        if isinstance(exc, urllib.error.HTTPError):
            detail = f"HTTP {exc.code}"
        # Linked but failed: do NOT show fake demo hours
        return empty_progress(
            athlete,
            source="intervals",
            today=today,
            fetch_error=True,
            fetch_error_detail=detail,
        )


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
