"""Shared Intervals.icu API helpers (personal API key)."""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = "https://intervals.icu/api/v1"

SPORT_TO_INTERVALS_TYPE: dict[str, str] = {
    "bike": "Ride",
    "run": "Run",
    "swim": "Swim",
    "strength": "WeightTraining",
    "other": "Other",
}

ZWO_PATH_RE = re.compile(
    r"(workouts/zwo/[^\s,\"')]+\.zwo)|(?:\b([A-Za-z0-9_-]+\.zwo)\b)"
)


def api_key() -> str:
    """GitHub repo secret: INTERVALS_API. Local .env may use either name."""
    return (
        os.environ.get("INTERVALS_API", "").strip()
        or os.environ.get("INTERVALS_API_KEY", "").strip()
    )


def athlete_id() -> str:
    return os.environ.get("INTERVALS_ATHLETE_ID", "0").strip() or "0"


def auth_header() -> str:
    key = api_key()
    token = base64.b64encode(f"API_KEY:{key}".encode()).decode()
    return f"Basic {token}"


def resolve_zwo_path(
    description: str,
    sport: str,
    repo_root: Path,
    explicit_path: str | None = None,
) -> Path | None:
    if explicit_path:
        p = repo_root / explicit_path
        if p.is_file():
            return p
    if not description:
        return None
    for m in ZWO_PATH_RE.finditer(description):
        rel = m.group(1) or m.group(2)
        if not rel:
            continue
        if not rel.startswith("workouts/"):
            sub = sport.lower()
            if sub == "bike":
                sub = "bike"
            elif sub == "run":
                sub = "run"
            elif sub == "swim":
                sub = "swim"
            else:
                sub = "bike"
            rel = f"workouts/zwo/{sub}/{rel}"
        candidate = repo_root / rel
        if candidate.is_file():
            return candidate
    return None


def post_events_bulk(
    events: list[dict],
    *,
    upsert: bool = True,
    dry_run: bool = False,
) -> dict | list:
    if dry_run:
        return {"dry_run": True, "count": len(events), "sample": events[:2]}

    aid = athlete_id()
    qs = "?upsert=true" if upsert else ""
    url = f"{API_BASE}/athlete/{aid}/events/bulk{qs}"
    body = json.dumps(events).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": auth_header(),
            "Content-Type": "application/json",
            "User-Agent": "LofotenLightAgent/1.0 (intervals push)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
            if not raw:
                return {"status": resp.status}
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:2000]
        raise RuntimeError(f"Intervals API {e.code}: {detail}") from e
