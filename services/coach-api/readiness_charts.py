"""TB-Score / readiness time series for Dashboard graphs.

Recomputes server-side from wellness + activities (same engine as
``scripts/plot_readiness_report.py``) — returns JSON for SVG, never commits PNG.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from tb_score import (
    _import_rtl,
    activity_rows_from_sessions,
    compute_tb_snapshot,
    config_path,
)


def _float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def build_tb_trend_series(
    wellness_rows: list[dict[str, Any]] | None,
    activity_sessions: list[dict[str, Any]] | None = None,
    *,
    days: int = 14,
    morning: time = time(7, 0),
    evening: time = time(17, 0),
    today: date | None = None,
) -> dict[str, Any]:
    """Daily morgen/kveld TB points for line chart — soft empty when data thin."""
    today = today or date.today()
    empty: dict[str, Any] = {
        "available": False,
        "points": [],
        "components": [],
        "note_nb": "Mangler wellness for TB-graf.",
        "source": "readiness_total_load",
        "written_to_intervals": False,
        "plots": False,
    }
    rows = [r for r in (wellness_rows or []) if isinstance(r, dict)]
    if not rows:
        return empty

    try:
        rtl = _import_rtl()
    except Exception as exc:  # noqa: BLE001
        empty["note_nb"] = f"TB-modul utilgjengelig ({exc.__class__.__name__})"
        return empty

    try:
        fields: list[str] = []
        seen: set[str] = set()
        for r in rows:
            for k in r.keys():
                if k not in seen:
                    seen.add(k)
                    fields.append(str(k))
        day_inputs = rtl["parse_wellness_rows"](rows, fields)
        if not day_inputs:
            return empty
        a_rows = activity_rows_from_sessions(activity_sessions or [])
        acts = None
        if a_rows:
            a_fields: list[str] = []
            a_seen: set[str] = set()
            for r in a_rows:
                for k in r.keys():
                    if k not in a_seen:
                        a_seen.add(k)
                        a_fields.append(str(k))
            acts = rtl["parse_activity_points"](a_rows, a_fields)
        cfg_p = config_path()
        cfg = rtl["load_config"](cfg_p if cfg_p.is_file() else None)
    except Exception as exc:  # noqa: BLE001
        empty["note_nb"] = f"TB-graf feilet ({exc.__class__.__name__})"
        return empty

    n = max(3, min(28, int(days)))
    start = today - timedelta(days=n - 1)
    points: list[dict[str, Any]] = []
    for i in range(n):
        d = start + timedelta(days=i)
        base = datetime(d.year, d.month, d.day)
        row: dict[str, Any] = {
            "date": d.isoformat(),
            "label": f"{d.day:02d}.{d.month:02d}",
        }
        for label, t in (("morgen", morning), ("kveld", evening)):
            at = base.replace(hour=t.hour, minute=t.minute)
            try:
                result = rtl["compute_readiness_at"](
                    at, day_inputs, acts, cfg, False
                )
                payload = rtl["result_to_dict"](result)
                row[label] = payload.get("tb_score")
                row[f"{label}_band"] = payload.get("band")
            except Exception:  # noqa: BLE001
                row[label] = None
                row[f"{label}_band"] = None
        # Prefer evening for single-line consumers
        row["tb_score"] = row.get("kveld") if row.get("kveld") is not None else row.get(
            "morgen"
        )
        points.append(row)

    # Latest component snapshot (evening today)
    components: list[dict[str, Any]] = []
    latest_score = None
    latest_band = None
    try:
        at = datetime(today.year, today.month, today.day, evening.hour, evening.minute)
        result = rtl["compute_readiness_at"](at, day_inputs, acts, cfg, False)
        payload = rtl["result_to_dict"](result)
        components = list(payload.get("components") or [])
        latest_score = payload.get("tb_score")
        latest_band = payload.get("band")
    except Exception:  # noqa: BLE001
        pass

    usable = sum(1 for p in points if p.get("tb_score") is not None)
    if usable < 2:
        empty["note_nb"] = "For få TB-punkter til graf (trenger mer wellness)."
        empty["points"] = points
        empty["components"] = components
        return empty

    return {
        "available": True,
        "days": n,
        "points": points,
        "components": components,
        "latest": {
            "tb_score": latest_score,
            "band": latest_band,
            "as_of": "kveld",
        },
        "note_nb": "TB-trend regenerert server-side (ingen PNG i git).",
        "source": "readiness_total_load",
        "written_to_intervals": False,
        "plots": False,
    }


def fetch_readiness_charts(
    secrets: dict[str, Any] | None,
    *,
    activity_sessions: list[dict[str, Any]] | None = None,
    days: int = 14,
    today: date | None = None,
) -> dict[str, Any]:
    """Fetch wellness and build TB trend — soft-fail without Intervals."""
    today = today or date.today()
    key = ((secrets or {}).get("intervals_api_key") or "").strip()
    aid = ((secrets or {}).get("intervals_athlete_id") or "").strip()
    if not key or not aid:
        return {
            "available": False,
            "points": [],
            "components": [],
            "note_nb": "Intervals ikke koblet — TB-graf krever wellness.",
            "written_to_intervals": False,
            "plots": False,
        }
    try:
        from wellness import fetch_wellness

        oldest = (today - timedelta(days=max(days, 7) + 3)).isoformat()
        rows = fetch_wellness(key, aid, oldest, today.isoformat())
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "points": [],
            "components": [],
            "note_nb": f"Wellness-henting feilet ({exc.__class__.__name__})",
            "written_to_intervals": False,
            "plots": False,
            "fetch_error": True,
        }
    return build_tb_trend_series(
        rows,
        activity_sessions,
        days=days,
        today=today,
    )


def components_bar_payload(components: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Normalize TB components for horizontal bar chart."""
    bars: list[dict[str, Any]] = []
    for c in components or []:
        if not isinstance(c, dict):
            continue
        score = _float(c.get("score"))
        if score is None:
            continue
        bars.append(
            {
                "label": str(c.get("label") or c.get("key") or "?"),
                "score": round(score, 0),
                "detail": str(c.get("detail") or ""),
            }
        )
    return {
        "available": bool(bars),
        "bars": bars,
        "note_nb": None if bars else "Ingen TB-komponenter.",
    }
