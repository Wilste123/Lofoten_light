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
    count_sessions_by_discipline,
    fetch_intervals_activities,
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
    payload: dict[str, Any] = {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "days": days,
        "source": source,
        "activity_count": total_sessions,
        "total_hours": total_h,
        "disciplines": rows,
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
    return build_period_training_payload(
        start=start,
        end=end,
        hours=hours,
        session_counts=counts,
        source="demo",
        activity_count=sum(counts.values()),
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
        return build_period_training_payload(
            start=start,
            end=end,
            hours=completed,
            session_counts=counts,
            source="intervals",
            activity_count=len(activities),
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
