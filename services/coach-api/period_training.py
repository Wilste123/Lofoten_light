"""Period-scoped training volume from Intervals activities (Dashboard).

Separate from season progress/compliance — no season targets in this payload.
See docs/product/dashboard-okter.md.
"""

from __future__ import annotations

import json
import urllib.error
from datetime import date, timedelta
from typing import Any

from progress_compliance import (
    DISCIPLINES,
    DEMO_COMPLETED,
    _activity_local_date,
    count_sessions_by_discipline,
    fetch_intervals_activities,
    map_activity_type,
    parse_duration_hours,
    sum_hours_by_discipline,
)

PERIOD_PRESETS: dict[str, int] = {
    "7d": 7,
    "14d": 14,
    "30d": 30,
    "90d": 90,
}

DEFAULT_PERIOD = "14d"
MAX_CUSTOM_DAYS = 366

# Demo weekly hours (scaled by period length when no Intervals credentials)
_DEMO_WEEKLY: dict[str, float] = {
    "swim": DEMO_COMPLETED["swim"] / 52.0,
    "bike": DEMO_COMPLETED["bike"] / 52.0,
    "run": DEMO_COMPLETED["run"] / 52.0,
    "strength": DEMO_COMPLETED["strength"] / 52.0,
}


class PeriodValidationError(ValueError):
    """Invalid period / from / to query combination."""


def parse_period_window(
    period: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """Resolve dashboard period query params to an inclusive date window.

    Presets: 7d, 14d, 30d, 90d (default 14d).
    Custom: period=custom with from=&to= (ISO YYYY-MM-DD), or bare from/to.
    """
    today = today or date.today()
    raw = (period or "").strip().lower() or DEFAULT_PERIOD
    from_s = (from_date or "").strip()[:10] or None
    to_s = (to_date or "").strip()[:10] or None

    if raw in PERIOD_PRESETS and not from_s and not to_s:
        days = PERIOD_PRESETS[raw]
        end = today
        start = today - timedelta(days=days - 1)
        return {
            "preset": raw,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "days": days,
        }

    # Custom or bare from/to
    if raw not in ("custom", *PERIOD_PRESETS) and raw:
        # Unknown preset name without dates
        if not from_s and not to_s:
            raise PeriodValidationError(
                f"Ugyldig period «{period}». Bruk 7d, 14d, 30d, 90d eller custom."
            )

    if not from_s or not to_s:
        raise PeriodValidationError(
            "Custom periode krever både from og to (YYYY-MM-DD)."
        )
    try:
        start = date.fromisoformat(from_s)
        end = date.fromisoformat(to_s)
    except ValueError as exc:
        raise PeriodValidationError("from/to må være ISO-dato (YYYY-MM-DD).") from exc
    if end < start:
        raise PeriodValidationError("to kan ikke være før from.")
    if end > today:
        end = today
    days = (end - start).days + 1
    if days > MAX_CUSTOM_DAYS:
        raise PeriodValidationError(
            f"Maks {MAX_CUSTOM_DAYS} dager i custom periode."
        )
    if days < 1:
        raise PeriodValidationError("Perioden må være minst 1 dag.")
    return {
        "preset": "custom",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": days,
    }


def _discipline_rows(
    hours: dict[str, float], counts: dict[str, int]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for disc_id, label, _field in DISCIPLINES:
        h = float(hours.get(disc_id) or 0.0)
        n = int(counts.get(disc_id) or 0)
        rows.append(
            {
                "id": disc_id,
                "label": label,
                "hours": round(h, 1),
                "session_count": n,
            }
        )
    return rows


def activity_duration_hours(act: dict[str, Any]) -> float | None:
    """Hours from one Intervals activity dict (moving_time preferred)."""
    for field in ("moving_time", "elapsed_time", "duration", "icu_coach_time"):
        if act.get(field) is not None and act.get(field) != "":
            hours = parse_duration_hours(act.get(field), field)
            if hours is not None:
                return hours
    return None


def hours_by_day(
    activities: list[dict[str, Any]],
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    """One row per calendar day in [start, end] with total + per-discipline hours.

    Days without activities get ``hours: 0``. Used by Dashboard volume chart.
    """
    if end < start:
        start, end = end, start
    disc_ids = [d[0] for d in DISCIPLINES]
    buckets: dict[date, dict[str, float]] = {}
    day = start
    while day <= end:
        buckets[day] = {d: 0.0 for d in disc_ids}
        day += timedelta(days=1)

    for act in activities:
        d = _activity_local_date(act)
        if d is None or d < start or d > end:
            continue
        disc = map_activity_type(act.get("type") or act.get("sport"))
        if not disc or disc not in buckets[d]:
            continue
        hours = activity_duration_hours(act)
        if hours is None:
            continue
        buckets[d][disc] += hours

    out: list[dict[str, Any]] = []
    day = start
    while day <= end:
        by_disc = {k: round(v, 2) for k, v in buckets[day].items()}
        total = round(sum(by_disc.values()), 2)
        out.append(
            {
                "date": day.isoformat(),
                "hours": total,
                "by_discipline": by_disc,
            }
        )
        day += timedelta(days=1)
    return out


def bucket_volume_series(
    daily: list[dict[str, Any]],
    *,
    max_bars: int = 31,
) -> dict[str, Any]:
    """Collapse daily hours into week buckets when the span is too wide for bars.

    Returns ``{bucket: "day"|"week", bars: [{label, start, end, hours, by_discipline}]}``.
    """
    if not daily:
        return {"bucket": "day", "bars": []}
    if len(daily) <= max_bars:
        bars = []
        for row in daily:
            d = row["date"]
            # DD.MM for Norwegian short labels
            label = f"{d[8:10]}.{d[5:7]}"
            bars.append(
                {
                    "label": label,
                    "start": d,
                    "end": d,
                    "hours": float(row.get("hours") or 0),
                    "by_discipline": dict(row.get("by_discipline") or {}),
                }
            )
        return {"bucket": "day", "bars": bars}

    # Week buckets (Mon–Sun ISO), merge days
    weeks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for row in daily:
        d = date.fromisoformat(row["date"])
        week_start = d - timedelta(days=d.weekday())
        week_key = week_start.isoformat()
        if current is None or current["_key"] != week_key:
            if current is not None:
                weeks.append(current)
            current = {
                "_key": week_key,
                "start": week_key,
                "end": row["date"],
                "hours": 0.0,
                "by_discipline": {d_id: 0.0 for d_id, _, _ in DISCIPLINES},
            }
        assert current is not None
        current["end"] = row["date"]
        current["hours"] += float(row.get("hours") or 0)
        for disc_id, val in (row.get("by_discipline") or {}).items():
            current["by_discipline"][disc_id] = (
                current["by_discipline"].get(disc_id, 0.0) + float(val or 0)
            )
    if current is not None:
        weeks.append(current)

    bars = []
    for w in weeks:
        start_s = w["start"]
        end_s = w["end"]
        label = f"{start_s[8:10]}.{start_s[5:7]}"
        if end_s != start_s:
            label = f"{start_s[8:10]}.{start_s[5:7]}–{end_s[8:10]}.{end_s[5:7]}"
        bars.append(
            {
                "label": label,
                "start": start_s,
                "end": end_s,
                "hours": round(float(w["hours"]), 2),
                "by_discipline": {
                    k: round(v, 2) for k, v in w["by_discipline"].items()
                },
            }
        )
    return {"bucket": "week", "bars": bars}


def demo_daily_hours(
    start: date, end: date, hours: dict[str, float]
) -> list[dict[str, Any]]:
    """Spread demo discipline totals across weekdays in the window (no weekend bias)."""
    if end < start:
        start, end = end, start
    days_list: list[date] = []
    day = start
    while day <= end:
        days_list.append(day)
        day += timedelta(days=1)
    n = max(1, len(days_list))
    # Prefer Mon–Fri for “training” feel when window has weekdays
    weekdays = [d for d in days_list if d.weekday() < 5] or days_list
    slots = weekdays
    disc_ids = [d[0] for d in DISCIPLINES]
    buckets: dict[date, dict[str, float]] = {
        d: {did: 0.0 for did in disc_ids} for d in days_list
    }
    for i, disc_id in enumerate(disc_ids):
        total = float(hours.get(disc_id) or 0.0)
        if total <= 0 or not slots:
            continue
        # Distribute with a mild mid-week peak
        weights = []
        for j, _d in enumerate(slots):
            weights.append(1.0 + 0.35 * ((j + i) % 3))
        wsum = sum(weights) or 1.0
        for slot, w in zip(slots, weights):
            buckets[slot][disc_id] += total * (w / wsum)
    return [
        {
            "date": d.isoformat(),
            "hours": round(sum(buckets[d].values()), 2),
            "by_discipline": {k: round(v, 2) for k, v in buckets[d].items()},
        }
        for d in days_list
    ]


def build_period_training_payload(
    *,
    start: date,
    end: date,
    hours: dict[str, float],
    session_counts: dict[str, int],
    source: str,
    activity_count: int | None = None,
    fetch_error: bool = False,
    fetch_error_detail: str | None = None,
    daily_hours: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble period training summary (no season targets)."""
    rows = _discipline_rows(hours, session_counts)
    total_h = round(sum(float(r["hours"]) for r in rows), 1)
    total_sessions = (
        activity_count
        if activity_count is not None
        else sum(int(c) for c in session_counts.values())
    )
    days = (end - start).days + 1
    daily = daily_hours if daily_hours is not None else hours_by_day([], start, end)
    volume = bucket_volume_series(daily)
    payload: dict[str, Any] = {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "days": days,
        "source": source,
        "activity_count": total_sessions,
        "total_hours": total_h,
        "disciplines": rows,
        "daily_hours": daily,
        "charts": {
            "volume": volume,
            "by_discipline": [
                {"id": r["id"], "label": r["label"], "hours": r["hours"]}
                for r in rows
            ],
        },
        "note": (
            "Treningsdata for valgt periode (aktiviteter fra Intervals). "
            "Ikke det samme som sesongmål / compliance."
        ),
    }
    if fetch_error:
        payload["fetch_error"] = True
        if fetch_error_detail:
            payload["fetch_error_detail"] = fetch_error_detail[:200]
    return payload


def demo_period_training(start: date, end: date) -> dict[str, Any]:
    days = max(1, (end - start).days + 1)
    scale = days / 7.0
    hours = {k: round(v * scale, 2) for k, v in _DEMO_WEEKLY.items()}
    # Rough session counts ~ 1 per ~1.5h for bike, etc.
    counts = {
        "swim": max(1, int(round(hours["swim"] / 0.75))),
        "bike": max(1, int(round(hours["bike"] / 1.5))),
        "run": max(1, int(round(hours["run"] / 0.9))),
        "strength": max(1, int(round(hours["strength"] / 0.75))),
    }
    daily = demo_daily_hours(start, end, hours)
    return build_period_training_payload(
        start=start,
        end=end,
        hours=hours,
        session_counts=counts,
        source="demo",
        activity_count=sum(counts.values()),
        daily_hours=daily,
    )


def empty_period_training(
    start: date,
    end: date,
    *,
    source: str,
    fetch_error: bool = False,
    fetch_error_detail: str | None = None,
) -> dict[str, Any]:
    zeros_h = {d[0]: 0.0 for d in DISCIPLINES}
    zeros_n = {d[0]: 0 for d in DISCIPLINES}
    return build_period_training_payload(
        start=start,
        end=end,
        hours=zeros_h,
        session_counts=zeros_n,
        source=source,
        activity_count=0,
        fetch_error=fetch_error,
        fetch_error_detail=fetch_error_detail,
        daily_hours=hours_by_day([], start, end),
    )


def resolve_period_training(
    secrets: dict[str, Any] | None,
    start: date,
    end: date,
) -> dict[str, Any]:
    """Fetch Intervals activities for [start, end] and aggregate hours.

    Soft-fail: linked + error → zeros + fetch_error; no credentials → demo.
    """
    key = ((secrets or {}).get("intervals_api_key") or "").strip()
    aid = ((secrets or {}).get("intervals_athlete_id") or "").strip()
    if not key or not aid:
        return demo_period_training(start, end)

    try:
        activities = fetch_intervals_activities(
            key, aid, start.isoformat(), end.isoformat()
        )
        completed = sum_hours_by_discipline(activities)
        counts = count_sessions_by_discipline(activities)
        daily = hours_by_day(activities, start, end)
        return build_period_training_payload(
            start=start,
            end=end,
            hours=completed,
            session_counts=counts,
            source="intervals",
            activity_count=len(activities),
            daily_hours=daily,
        )
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
        return empty_period_training(
            start,
            end,
            source="intervals",
            fetch_error=True,
            fetch_error_detail=detail,
        )
