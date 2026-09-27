"""Wire form_estimates from Intervals bike+power activities (90d) + power curve.

See docs/product/form-estimates.md.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any

from form_estimates import (
    ActivityPower,
    MMP_FACTORS,
    compute_form_estimates,
)
from progress_compliance import (
    API_BASE,
    _http_get_json,
    map_activity_type,
    parse_duration_hours,
)

POWER_LOOKBACK_DAYS = 90
_POWER_FIELDS = (
    "id,type,sport,moving_time,elapsed_time,duration,start_date_local,"
    "average_watts,icu_average_watts,icu_weighted_avg_watts,max_watts,"
    "icu_ftp,has_power"
)
_CACHE_TTL_SEC = 180
_cache_lock = threading.Lock()
_power_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_curve_cache: dict[str, tuple[float, dict[int, float]]] = {}


def clear_form_caches() -> None:
    with _cache_lock:
        _power_cache.clear()
        _curve_cache.clear()


def _mean_watts(act: dict[str, Any]) -> float | None:
    for field in (
        "icu_weighted_avg_watts",
        "icu_average_watts",
        "average_watts",
        "weighted_average_watts",
        "avg_watts",
    ):
        raw = act.get(field)
        if raw is None or raw == "":
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        if val > 0:
            return val
    return None


def _duration_min(act: dict[str, Any]) -> float | None:
    for field in ("moving_time", "elapsed_time", "duration"):
        if act.get(field) is None or act.get(field) == "":
            continue
        hours = parse_duration_hours(act.get(field), field)
        if hours is not None and hours > 0:
            return hours * 60.0
    return None


def is_bike_with_power(act: dict[str, Any]) -> bool:
    if map_activity_type(act.get("type") or act.get("sport")) != "bike":
        return False
    if act.get("has_power") is False:
        return False
    return _mean_watts(act) is not None


def activity_to_power(act: dict[str, Any]) -> ActivityPower | None:
    """Map one Intervals activity → ActivityPower for the gate / fallback MMP."""
    if not is_bike_with_power(act):
        return None
    dur = _duration_min(act)
    mean = _mean_watts(act)
    if dur is None or mean is None:
        return None
    # Conservative local MMP: only claim a window if the ride is at least that long.
    # Mean power ≤ true MMP for that window — keeps estimates low (product rule).
    mmp: dict[int, float] = {}
    for window in MMP_FACTORS:
        if dur >= window:
            mmp[window] = mean
    return ActivityPower(
        duration_min=dur,
        mean_power=mean,
        mmp=mmp or None,
        has_power=True,
    )


def activities_to_power_list(activities: list[dict[str, Any]]) -> list[ActivityPower]:
    out: list[ActivityPower] = []
    for act in activities:
        converted = activity_to_power(act)
        if converted is not None:
            out.append(converted)
    return out


def fetch_bike_power_activities(
    api_key: str,
    athlete_id: str,
    *,
    today: date | None = None,
    lookback_days: int = POWER_LOOKBACK_DAYS,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    """Bike activities with watt fields for the last N days."""
    today = today or date.today()
    oldest = (today - timedelta(days=max(lookback_days, 1) - 1)).isoformat()
    newest = today.isoformat()
    cache_id = f"{athlete_id}|{api_key[-6:]}|{oldest}|{newest}|pwr"
    if use_cache:
        with _cache_lock:
            hit = _power_cache.get(cache_id)
            if hit and (time.time() - hit[0]) < _CACHE_TTL_SEC:
                return list(hit[1])

    # Temporarily request power fields via page helper by monkeypatching fields
    # — call list endpoint with extended fields.
    activities = _fetch_activities_with_fields(
        api_key, athlete_id, oldest, newest, fields=_POWER_FIELDS
    )
    bike = [a for a in activities if is_bike_with_power(a)]
    if use_cache:
        with _cache_lock:
            _power_cache[cache_id] = (time.time(), list(bike))
    return bike


def _fetch_activities_with_fields(
    api_key: str,
    athlete_id: str,
    oldest: str,
    newest: str,
    *,
    fields: str,
    page_limit: int = 100,
) -> list[dict[str, Any]]:
    """Same paging as progress_compliance, but with custom fields."""
    oldest_d = date.fromisoformat(oldest[:10])
    newest_d = date.fromisoformat(newest[:10])
    if oldest_d > newest_d:
        return []

    collected: list[dict[str, Any]] = []
    seen: set[str] = set()
    cursor_newest = newest_d
    for _ in range(40):
        qs = urllib.parse.urlencode(
            {
                "oldest": oldest_d.isoformat(),
                "newest": cursor_newest.isoformat(),
                "limit": str(page_limit),
                "fields": fields,
            }
        )
        url = f"{API_BASE}/athlete/{athlete_id.strip()}/activities?{qs}"
        data = _http_get_json(url, api_key)
        if isinstance(data, dict):
            data = data.get("activities") or data.get("data") or []
        if not isinstance(data, list):
            batch = []
        else:
            batch = [a for a in data if isinstance(a, dict)]
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
            raw = act.get("start_date_local") or act.get("start_date") or ""
            try:
                text = str(raw)
                ad = (
                    datetime.fromisoformat(text.replace("Z", "+00:00")).date()
                    if "T" in text
                    else date.fromisoformat(text[:10])
                )
            except ValueError:
                ad = None
            if ad is not None and (oldest_in_batch is None or ad < oldest_in_batch):
                oldest_in_batch = ad
        if len(batch) < page_limit or oldest_in_batch is None:
            break
        next_newest = oldest_in_batch - timedelta(days=1)
        if next_newest < oldest_d or new_in_batch == 0:
            break
        cursor_newest = next_newest
    return collected


def parse_power_curve_mmp(payload: Any) -> dict[int, float]:
    """Extract MMP watts for windows in MMP_FACTORS from Intervals power-curves JSON."""
    targets = {w * 60: w for w in MMP_FACTORS}  # seconds → minutes
    secs: list[int] = []
    watts: list[float] = []

    def _take_pair(s_list: Any, w_list: Any) -> None:
        nonlocal secs, watts
        if not isinstance(s_list, list) or not isinstance(w_list, list):
            return
        if len(s_list) != len(w_list) or not s_list:
            return
        try:
            secs = [int(x) for x in s_list]
            watts = [float(x) for x in w_list]
        except (TypeError, ValueError):
            return

    if isinstance(payload, dict):
        # Shapes: {"90d": {"secs":[], "watts":[]}}, {"list":[...]}, or direct secs/watts
        if "secs" in payload and "watts" in payload:
            _take_pair(payload.get("secs"), payload.get("watts"))
        elif "list" in payload and isinstance(payload["list"], list):
            for item in payload["list"]:
                if isinstance(item, dict) and "secs" in item:
                    _take_pair(item.get("secs"), item.get("watts"))
                    if secs:
                        break
        else:
            for key in ("90d", "42d", "365d", "all"):
                node = payload.get(key)
                if isinstance(node, dict) and "secs" in node:
                    _take_pair(node.get("secs"), node.get("watts"))
                    if secs:
                        break
            if not secs:
                for node in payload.values():
                    if isinstance(node, dict) and "secs" in node:
                        _take_pair(node.get("secs"), node.get("watts"))
                        if secs:
                            break
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and "secs" in item:
                _take_pair(item.get("secs"), item.get("watts"))
                if secs:
                    break

    if not secs:
        return {}

    # Index by second for exact hits; else nearest ≤ target
    by_sec = {s: w for s, w in zip(secs, watts) if w and w > 0}
    mmp: dict[int, float] = {}
    sorted_secs = sorted(by_sec)
    for target_sec, window_min in targets.items():
        if target_sec in by_sec:
            mmp[window_min] = by_sec[target_sec]
            continue
        # nearest duration at or below target (never invent longer effort)
        candidates = [s for s in sorted_secs if s <= target_sec]
        if candidates:
            best = candidates[-1]
            # Accept if within 10% of target window
            if best >= target_sec * 0.9:
                mmp[window_min] = by_sec[best]
    return mmp


def fetch_power_curve_mmp(
    api_key: str,
    athlete_id: str,
    *,
    curves: str = "90d",
    use_cache: bool = True,
) -> dict[int, float]:
    cache_id = f"{athlete_id}|{api_key[-6:]}|{curves}"
    if use_cache:
        with _cache_lock:
            hit = _curve_cache.get(cache_id)
            if hit and (time.time() - hit[0]) < _CACHE_TTL_SEC:
                return dict(hit[1])
    qs = urllib.parse.urlencode({"curves": curves})
    url = f"{API_BASE}/athlete/{athlete_id.strip()}/power-curves?{qs}"
    try:
        data = _http_get_json(url, api_key, timeout=15)
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        ValueError,
        json.JSONDecodeError,
        OSError,
    ):
        return {}
    mmp = parse_power_curve_mmp(data)
    if use_cache and mmp:
        with _cache_lock:
            _curve_cache[cache_id] = (time.time(), dict(mmp))
    return mmp


def resolve_form_estimates(
    athlete: dict[str, Any],
    secrets: dict[str, Any] | None,
    *,
    today: date | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Compute estimates from ICU when linked; else closed gate from empty list.

    Does not persist — caller writes ftp_estimated / confidence to SQLite.
    """
    today = today or date.today()
    key = ((secrets or {}).get("intervals_api_key") or "").strip()
    aid = ((secrets or {}).get("intervals_athlete_id") or "").strip()
    ftp_tested = athlete.get("ftp_tested")
    weight = athlete.get("weight_kg")
    age = athlete.get("age_years")

    if not key or not aid:
        result = compute_form_estimates(
            [],
            ftp_tested=ftp_tested,
            weight_kg=weight,
            age_years=age,
        )
        result["fetch_source"] = "none"
        return result

    try:
        raw_acts = fetch_bike_power_activities(
            key, aid, today=today, use_cache=use_cache
        )
        power_acts = activities_to_power_list(raw_acts)
        curve_mmp = fetch_power_curve_mmp(key, aid, use_cache=use_cache)
        if curve_mmp and power_acts:
            # Attach curve MMP to a synthetic activity so aggregate_mmp picks peaks
            power_acts = list(power_acts) + [
                ActivityPower(
                    duration_min=90,
                    mean_power=max(curve_mmp.values()),
                    mmp=curve_mmp,
                    has_power=True,
                )
            ]
        result = compute_form_estimates(
            power_acts,
            ftp_tested=ftp_tested,
            weight_kg=weight,
            age_years=age,
        )
        result["fetch_source"] = "intervals"
        result["bike_power_activity_count"] = len(raw_acts)
        if curve_mmp:
            result["power_curve_windows"] = sorted(curve_mmp.keys())
        return result
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        ValueError,
        json.JSONDecodeError,
        OSError,
    ) as exc:
        result = compute_form_estimates(
            [],
            ftp_tested=ftp_tested,
            weight_kg=weight,
            age_years=age,
        )
        result["fetch_source"] = "error"
        result["fetch_error"] = True
        detail = str(exc) or exc.__class__.__name__
        if isinstance(exc, urllib.error.HTTPError):
            detail = f"HTTP {exc.code}"
        result["fetch_error_detail"] = detail[:200]
        # Keep previously stored estimates visible via athlete fields in overview
        result["disclaimer"] = (
            result.get("disclaimer")
            or "Kunne ikke hente watt-historikk fra Intervals."
        )
        return result


def persist_estimates_patch(estimates: dict[str, Any]) -> dict[str, Any]:
    """Fields to write on athletes when gate is open (or clear when closed after success)."""
    from db import utc_now

    if estimates.get("fetch_source") == "error":
        return {}
    if not estimates.get("gate_open"):
        return {
            "ftp_estimated": None,
            "vo2_estimate": None,
            "estimate_confidence": None,
            "estimate_source": estimates.get("fetch_source") or "intervals",
            "estimate_updated_at": utc_now(),
        }
    return {
        "ftp_estimated": estimates.get("ftp_estimated"),
        "vo2_estimate": estimates.get("vo2_estimate"),
        "estimate_confidence": estimates.get("estimate_confidence"),
        "estimate_source": estimates.get("estimate_source") or "intervals",
        "estimate_updated_at": utc_now(),
    }
