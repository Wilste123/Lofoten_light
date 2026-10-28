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
USER_AGENT = "Lofoten_light-coach/1.0"


def access_token() -> str:
    for key in ("TRAININGPEAKS_ACCESS_TOKEN", "TP_BEARER_TOKEN", "TRAININGPEAKS_BEARER"):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    raise RuntimeError(
        "Missing TrainingPeaks token. Set TRAININGPEAKS_ACCESS_TOKEN or TP_BEARER_TOKEN "
        "(see docs/trainingpeaks/tp-api-setup.md)."
    )


def athlete_id() -> int:
    raw = (os.environ.get("TRAININGPEAKS_ATHLETE_ID") or "").strip()
    if not raw:
        raise RuntimeError(
            "Missing TRAININGPEAKS_ATHLETE_ID (needed to plan workouts). "
            "See docs/trainingpeaks/tp-api-setup.md."
        )
    return int(raw)


def _request(
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
        "Authorization": f"Bearer {access_token()}",
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


def get_workouts(
    start: str,
    end: str,
    *,
    include_description: bool = True,
) -> list[dict[str, Any]]:
    """GET /v2/workouts/{start}/{end} — max 45 days span."""
    q = {"includeDescription": "true"} if include_description else {}
    raw = _request("GET", f"/v2/workouts/{start}/{end}", query=q)
    data = json.loads(raw.decode())
    if isinstance(data, list):
        return data
    return data.get("Workouts") or data.get("workouts") or []


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
