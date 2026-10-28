"""TrainingPeaks API client (Partner OAuth token or session bearer).

Requires env:
  TRAININGPEAKS_ACCESS_TOKEN or TP_BEARER_TOKEN
  TRAININGPEAKS_ATHLETE_ID (numeric) for POST /v2/workouts/plan

Official access: https://api.trainingpeaks.com/request-access
Setup: docs/trainingpeaks/tp-api-setup.md
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API_BASE = os.environ.get("TRAININGPEAKS_API_BASE", "https://api.trainingpeaks.com").rstrip(
    "/"
)
TPAPI_BASE = "https://tpapi.trainingpeaks.com"
USER_AGENT = "Lofoten_light-coach/1.0"

_partners_token_cache: str | None = None
_tpapi_token_cache: str | None = None

# fitness/v6 workoutTypeValueId → Partners WorkoutType string
_WORKOUT_TYPE_BY_VALUE_ID: dict[int, str] = {
    1: "swim",
    2: "bike",
    3: "run",
    4: "brick",
    5: "crosstrain",
    6: "mtb",
    7: "run",
    8: "walk",
    9: "strength",
    10: "xc-ski",
    11: "rowing",
    12: "other",
}


def _normalize_cookie_value(raw: str) -> str:
    s = raw.strip()
    if s.lower().startswith("bearer "):
        s = s[7:].strip()
    for prefix in ("Production_tpAuth:", "Production_tpauth:", "production_tpauth:"):
        if s.lower().startswith(prefix.lower()):
            return s[len(prefix) :].strip()
    return s


def exchange_cookie_for_bearer(cookie_value: str) -> str:
    """TrainingPeaks web session → short-lived bearer (TrainingDojo / tp2intervals flow)."""
    val = _normalize_cookie_value(cookie_value)
    req = urllib.request.Request(
        f"{TPAPI_BASE}/users/v3/token",
        headers={
            "Cookie": f"Production_tpAuth={val}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(
            f"TrainingPeaks token exchange failed {e.code}: {detail}"
        ) from e
    token_obj = data.get("token")
    if isinstance(token_obj, dict):
        token = token_obj.get("access_token") or token_obj.get("accessToken")
    else:
        token = None
    if not token:
        token = (
            data.get("access_token")
            or data.get("accessToken")
            or data.get("bearerToken")
            or (data.get("data") or {}).get("token")
        )
    if not token and isinstance(data, str):
        token = data
    if not token:
        raise RuntimeError(f"Token exchange: unexpected response keys {list(data)[:10]}")
    return str(token).strip()


def _raw_credential() -> str:
    for key in ("TRAININGPEAKS_ACCESS_TOKEN", "TP_BEARER_TOKEN", "TRAININGPEAKS_BEARER"):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    raise RuntimeError(
        "Missing TrainingPeaks token. Set TRAININGPEAKS_ACCESS_TOKEN or TP_BEARER_TOKEN "
        "(Production_tpAuth cookie value or Bearer). See docs/trainingpeaks/tp-api-setup.md."
    )


def is_cookie_credential(raw: str | None = None) -> bool:
    val = (raw if raw is not None else _raw_credential()).strip()
    norm = _normalize_cookie_value(val)
    return norm.startswith("V001") or val.lower().startswith("production_tp")


def tpapi_access_token() -> str:
    """Bearer for tpapi.trainingpeaks.com (cookie exchange or JWT if tpapi accepts it)."""
    global _tpapi_token_cache
    if _tpapi_token_cache:
        return _tpapi_token_cache
    raw = _raw_credential()
    if is_cookie_credential(raw):
        _tpapi_token_cache = exchange_cookie_for_bearer(raw)
    else:
        _tpapi_token_cache = _normalize_cookie_value(raw)
    return _tpapi_token_cache


def partners_access_token() -> str:
    """Bearer for api.trainingpeaks.com Partners API (JWT from DevTools, not cookie exchange)."""
    global _partners_token_cache
    if _partners_token_cache:
        return _partners_token_cache
    raw = _raw_credential()
    if is_cookie_credential(raw):
        raise RuntimeError(
            "Production_tpAuth cookie cannot read Partners API (/v2). "
            "Use tpapi fitness read (automatic) or paste a JWT Bearer from api.trainingpeaks.com requests."
        )
    _partners_token_cache = _normalize_cookie_value(raw)
    return _partners_token_cache


def access_token() -> str:
    """Default bearer: Partners JWT if configured, else tpapi session bearer."""
    if not is_cookie_credential():
        return partners_access_token()
    return tpapi_access_token()


def athlete_id() -> int:
    raw = (os.environ.get("TRAININGPEAKS_ATHLETE_ID") or "").strip()
    if not raw:
        raise RuntimeError(
            "Missing TRAININGPEAKS_ATHLETE_ID (needed to plan workouts). "
            "See docs/trainingpeaks/tp-api-setup.md."
        )
    return int(raw)


def _request_partners(
    method: str,
    path: str,
    *,
    query: dict[str, str] | None = None,
    body: dict | None = None,
    timeout: int = 120,
) -> bytes:
    url = f"{API_BASE}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    data = None
    headers = {
        "Authorization": f"Bearer {partners_access_token()}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"TrainingPeaks API {e.code} {method} {path}: {detail}") from e


def _request_tpapi(
    method: str,
    path: str,
    *,
    query: dict[str, str] | None = None,
    timeout: int = 120,
) -> bytes:
    url = f"{TPAPI_BASE}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    headers = {
        "Authorization": f"Bearer {tpapi_access_token()}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    req = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"TrainingPeaks tpapi {e.code} {method} {path}: {detail}") from e


def _request(
    method: str,
    path: str,
    *,
    query: dict[str, str] | None = None,
    body: dict | None = None,
    timeout: int = 120,
) -> bytes:
    return _request_partners(method, path, query=query, body=body, timeout=timeout)


def normalize_tpapi_workout(row: dict[str, Any]) -> dict[str, Any]:
    """Map tpapi fitness/v6 workout → Partners-style keys for CSV/scripts."""
    type_id = row.get("workoutTypeValueId")
    wtype = row.get("workoutType")
    if not wtype and isinstance(type_id, int):
        wtype = _WORKOUT_TYPE_BY_VALUE_ID.get(type_id, "other")
    day_raw = row.get("workoutDay") or ""
    day = day_raw[:10] if isinstance(day_raw, str) else str(day_raw)[:10]
    return {
        "Id": row.get("workoutId"),
        "WorkoutDay": day,
        "WorkoutType": wtype or "other",
        "Title": row.get("title") or "",
        "TotalTime": row.get("totalTime"),
        "TotalTimePlanned": row.get("totalTimePlanned"),
        "TssActual": row.get("tssActual"),
        "TssPlanned": row.get("tssPlanned"),
        "Distance": row.get("distance"),
        "Description": row.get("description") or "",
        "Completed": row.get("completed"),
        "Source": "tpapi-fitness-v6",
    }


def get_workouts_tpapi(
    start: str,
    end: str,
    *,
    athlete: int | None = None,
) -> list[dict[str, Any]]:
    """GET tpapi …/fitness/v6/athletes/{id}/workouts/{start}/{end} (cookie session)."""
    aid = athlete if athlete is not None else athlete_id()
    path = f"/fitness/v6/athletes/{aid}/workouts/{start}/{end}"
    raw = _request_tpapi("GET", path)
    data = json.loads(raw.decode())
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected tpapi workouts payload: {type(data)}")
    return [normalize_tpapi_workout(w) for w in data]


def get_workouts(
    start: str,
    end: str,
    *,
    include_description: bool = True,
) -> list[dict[str, Any]]:
    """Planned + completed workouts (Partners /v2 or tpapi fitness/v6 fallback). Max 45 days."""
    if not is_cookie_credential():
        q = {"includeDescription": "true"} if include_description else {}
        raw = _request_partners("GET", f"/v2/workouts/{start}/{end}", query=q)
        data = json.loads(raw.decode())
        if isinstance(data, list):
            return data
        return data.get("Workouts") or data.get("workouts") or []
    return get_workouts_tpapi(start, end)


def get_metrics(
    start: str,
    end: str,
    *,
    athlete: int | None = None,
) -> list[dict[str, Any]]:
    """GET /v2/metrics/{start}/{end} — requires Partners JWT (not cookie session)."""
    aid = athlete if athlete is not None else athlete_id()
    if is_cookie_credential():
        raise RuntimeError(
            "TrainingPeaks body metrics (weight, HRV in TP) require Partners JWT Bearer. "
            "Cookie session can read workouts via tpapi only. "
            "Use fetch_intervals_wellness.py for Garmin wellness in this repo."
        )
    raw = _request_partners("GET", f"/v2/metrics/{start}/{end}")
    data = json.loads(raw.decode())
    if isinstance(data, list):
        return data
    return data.get("Metrics") or data.get("metrics") or []


def plan_workout(payload: dict[str, Any]) -> dict[str, Any]:
    """POST /v2/workouts/plan — payload must include AthleteId, WorkoutDay, WorkoutType."""
    raw = _request("POST", "/v2/workouts/plan", body=payload)
    if not raw:
        return {}
    return json.loads(raw.decode())


def sport_to_workout_type(sport: str) -> str:
    s = sport.strip().lower()
    mapping = {
        "bike": "bike",
        "run": "run",
        "swim": "swim",
        "strength": "strength",
        "other": "other",
        "x-train": "x-train",
        "walk": "walk",
    }
    return mapping.get(s, "other")
