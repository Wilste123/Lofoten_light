"""Intervals wellness fetch + sleep / body-metrics analysis (soft-fail).

Reuses auth patterns from progress_compliance / intervals_lib.
Does NOT write wellness back to Intervals.
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
from statistics import mean
from typing import Any

API_BASE = "https://intervals.icu/api/v1"
_FETCH_TIMEOUT = 12
_CACHE_TTL_SEC = 120
_cache_lock = threading.Lock()
_wellness_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _auth_headers(api_key: str) -> dict[str, str]:
    token = base64.b64encode(f"API_KEY:{api_key}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Accept": "application/json",
        "User-Agent": "LofotenCoachApi/0.1 (wellness)",
    }


def _parse_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _row_date(row: dict[str, Any]) -> date | None:
    raw = row.get("id") or row.get("date") or row.get("day") or ""
    s = str(raw)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def clear_wellness_cache() -> None:
    with _cache_lock:
        _wellness_cache.clear()


def fetch_wellness(
    api_key: str,
    athlete_id: str,
    oldest: str,
    newest: str,
    *,
    timeout: int = _FETCH_TIMEOUT,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    """GET /athlete/{id}/wellness?oldest=&newest= — soft callers wrap exceptions."""
    key = (api_key or "").strip()
    aid = (athlete_id or "").strip()
    if not key or not aid:
        raise ValueError("Mangler Intervals-credentials")
    cache_id = f"{aid}|{key[-6:]}|{oldest[:10]}|{newest[:10]}"
    if use_cache:
        with _cache_lock:
            hit = _wellness_cache.get(cache_id)
            if hit and (time.time() - hit[0]) < _CACHE_TTL_SEC:
                return list(hit[1])

    qs = urllib.parse.urlencode({"oldest": oldest[:10], "newest": newest[:10]})
    url = f"{API_BASE}/athlete/{aid}/wellness?{qs}"
    req = urllib.request.Request(url, method="GET", headers=_auth_headers(key))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    if not raw:
        rows: list[dict[str, Any]] = []
    else:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = data.get("wellness") or data.get("data") or []
        rows = [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []

    if use_cache:
        with _cache_lock:
            _wellness_cache[cache_id] = (time.time(), list(rows))
    return rows


def _series(rows: list[dict[str, Any]], field: str, *, div: float = 1.0) -> list[float]:
    out: list[float] = []
    for r in rows:
        v = _parse_float(r.get(field))
        if v is None:
            continue
        out.append(v / div if div != 1.0 else v)
    return out


def analyze_sleep(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize sleep from wellness rows (last N days already filtered)."""
    sleep_h = _series(rows, "sleepSecs", div=3600.0)
    if not sleep_h:
        # Some devices export sleepTime as hours already
        sleep_h = _series(rows, "sleepTime")
    scores = _series(rows, "sleepScore")
    short = sum(1 for h in sleep_h if h < 6.5)
    avg_h = round(mean(sleep_h), 2) if sleep_h else None
    avg_score = round(mean(scores), 1) if scores else None
    note = None
    if avg_h is not None:
        if avg_h < 6.5:
            note = "Kort snitt — prioriter søvn før hardøkt."
        elif avg_h >= 7.5:
            note = "Solid søvngrunnlag."
        else:
            note = "OK snitt — følg med på korte netter."
    return {
        "days_with_data": len(sleep_h),
        "avg_hours": avg_h,
        "avg_score": avg_score,
        "short_nights": short,
        "min_hours": round(min(sleep_h), 2) if sleep_h else None,
        "max_hours": round(max(sleep_h), 2) if sleep_h else None,
        "note": note,
        "available": bool(sleep_h),
    }


def analyze_body(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Weight + body-fat from wellness / BIA fields."""
    weights = _series(rows, "weight")
    fats = _series(rows, "bodyFat")
    latest_w = None
    latest_f = None
    latest_date = None
    dated = [(d, r) for r in rows if (d := _row_date(r)) is not None]
    dated.sort(key=lambda x: x[0])
    for d, r in reversed(dated):
        w = _parse_float(r.get("weight"))
        f = _parse_float(r.get("bodyFat"))
        if latest_w is None and w is not None:
            latest_w = w
            latest_date = d.isoformat()
        if latest_f is None and f is not None:
            latest_f = f
        if latest_w is not None and (latest_f is not None or not fats):
            break
    delta_7 = None
    if len(weights) >= 2 and dated:
        # Compare latest vs ~7d earlier mean of first half if enough points
        recent = weights[-3:] if len(weights) >= 3 else weights[-1:]
        older = weights[: max(1, len(weights) // 2)]
        if recent and older:
            delta_7 = round(mean(recent) - mean(older), 2)
    note = None
    if latest_w is not None and delta_7 is not None:
        if abs(delta_7) < 0.3:
            note = "Vekt stabil (støy ±0,3 kg)."
        elif delta_7 > 0:
            note = f"Lett opp (+{delta_7} kg vs tidligere snitt) — følg 7d-snitt."
        else:
            note = f"Lett ned ({delta_7} kg vs tidligere snitt) — følg 7d-snitt."
    return {
        "days_with_weight": len(weights),
        "days_with_body_fat": len(fats),
        "latest_weight_kg": round(latest_w, 2) if latest_w is not None else None,
        "latest_body_fat_pct": round(latest_f, 1) if latest_f is not None else None,
        "latest_date": latest_date,
        "avg_weight_kg": round(mean(weights), 2) if weights else None,
        "avg_body_fat_pct": round(mean(fats), 1) if fats else None,
        "weight_delta_vs_earlier": delta_7,
        "note": note,
        "available": bool(weights or fats),
    }


def load_summary_from_wellness(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """CTL/ATL / readiness from latest wellness row when present."""
    dated = [(d, r) for r in rows if (d := _row_date(r)) is not None]
    dated.sort(key=lambda x: x[0])
    if not dated:
        return {"available": False, "ctl": None, "atl": None, "readiness": None, "date": None}
    d, r = dated[-1]
    return {
        "available": any(
            _parse_float(r.get(k)) is not None for k in ("ctl", "atl", "readiness")
        ),
        "ctl": _parse_float(r.get("ctl")),
        "atl": _parse_float(r.get("atl")),
        "readiness": _parse_float(r.get("readiness")),
        "date": d.isoformat(),
    }


def resolve_wellness_bundle(
    secrets: dict[str, Any] | None,
    *,
    days: int = 14,
    today: date | None = None,
    include_body: bool = True,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, Any]:
    """Fetch + analyze wellness. Soft-fail when no credentials or ICU error.

    Prefer explicit ``start``/``end`` when provided (Dashboard period picker);
    otherwise last ``days`` ending on ``today``.
    """
    today = today or date.today()
    if start is not None and end is not None:
        if end < start:
            start, end = end, start
        oldest = start.isoformat()
        newest = end.isoformat()
    else:
        oldest = (today - timedelta(days=max(1, days - 1))).isoformat()
        newest = today.isoformat()
    key = ((secrets or {}).get("intervals_api_key") or "").strip()
    aid = ((secrets or {}).get("intervals_athlete_id") or "").strip()
    empty = {
        "window": {"start": oldest, "end": newest},
        "source": "none",
        "fetch_error": False,
        "fetch_error_detail": None,
        "sleep": {
            "available": False,
            "days_with_data": 0,
            "avg_hours": None,
            "avg_score": None,
            "short_nights": 0,
            "min_hours": None,
            "max_hours": None,
            "note": "Koble Intervals for søvnanalyse.",
        },
        "body": None,
        "load_wellness": {"available": False, "ctl": None, "atl": None, "readiness": None},
    }
    if include_body:
        empty["body"] = {
            "available": False,
            "days_with_weight": 0,
            "days_with_body_fat": 0,
            "latest_weight_kg": None,
            "latest_body_fat_pct": None,
            "latest_date": None,
            "avg_weight_kg": None,
            "avg_body_fat_pct": None,
            "weight_delta_vs_earlier": None,
            "note": "Koble Intervals for vekt/BIA.",
        }
    if not key or not aid:
        return empty

    try:
        rows = fetch_wellness(key, aid, oldest, newest)
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
        out = dict(empty)
        out["source"] = "intervals"
        out["fetch_error"] = True
        out["fetch_error_detail"] = detail
        out["sleep"] = {
            **empty["sleep"],
            "note": "Kunne ikke hente wellness.",
        }
        if include_body and out.get("body"):
            out["body"] = {**out["body"], "note": "Kunne ikke hente wellness."}
        return out

    payload: dict[str, Any] = {
        "window": {"start": oldest, "end": newest},
        "source": "intervals",
        "fetch_error": False,
        "fetch_error_detail": None,
        "row_count": len(rows),
        "sleep": analyze_sleep(rows),
        "load_wellness": load_summary_from_wellness(rows),
    }
    if include_body:
        payload["body"] = analyze_body(rows)
    else:
        payload["body"] = None
        payload["body_hidden"] = True
    return payload
