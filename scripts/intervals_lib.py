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

STRENGTH_TXT_RE = re.compile(
    r"(workouts/planned/strength/[A-Za-z0-9._-]+\.txt)"
)

PLANNED_SESSION_RE = re.compile(
    r"(workouts/planned/(?:run|swim|bike|other)/[A-Za-z0-9._-]+\.txt)"
)


def format_strength_txt_for_intervals(path: Path) -> str:
    """Body after '---' is coach text for Intervals; else whole file minus metadata headers."""
    raw = path.read_text(encoding="utf-8")
    if "\n---\n" in raw:
        return raw.split("\n---\n", 1)[1].strip()
    lines: list[str] = []
    for line in raw.splitlines():
        if not line.strip():
            if lines:
                break
            continue
        if re.match(r"^[a-z_]+:\s", line):
            continue
        lines.append(line)
    return "\n".join(lines).strip() if lines else raw.strip()


def resolve_strength_description(description: str, repo_root: Path) -> str | None:
    if not description:
        return None
    for m in STRENGTH_TXT_RE.finditer(description):
        rel = m.group(1)
        candidate = repo_root / rel
        if candidate.is_file():
            return format_strength_txt_for_intervals(candidate)
    return None


def read_planned_meta(path: Path) -> dict[str, str]:
    meta: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() == "---":
            break
        if ":" in line and line[0] not in (" ", "\t", "-"):
            key, val = line.split(":", 1)
            meta[key.strip()] = val.strip()
    return meta


def format_planned_session_for_intervals(path: Path) -> str:
    """Coach (markdown) + Intervals.icu workout block. Run/swim: syntax must be parser-safe."""
    raw = path.read_text(encoding="utf-8")
    if "---intervals---" not in raw:
        return format_strength_txt_for_intervals(path)
    head, intervals = raw.split("---intervals---", 1)
    coach = head.split("---", 1)[-1].strip() if "---" in head else head.strip()
    intervals = intervals.strip()
    sport = read_planned_meta(path).get("sport", "")
    if sport == "run":
        from run_intervals_syntax import lint_run_intervals_block

        issues = lint_run_intervals_block(intervals)
        if issues:
            raise ValueError(f"{path}: Intervals løp-syntax: " + "; ".join(issues[:3]))
    if coach:
        return f"### Fra treneren\n\n{coach}\n\n---\n\n{intervals}"
    return intervals


def resolve_planned_session_path(
    description: str, sport: str, repo_root: Path
) -> Path | None:
    if not description:
        return None
    for m in PLANNED_SESSION_RE.finditer(description):
        candidate = repo_root / m.group(1)
        if candidate.is_file():
            return candidate
    sport_l = (sport or "").lower()
    if sport_l not in ("run", "swim", "bike", "other"):
        return None
    stem = _zwo_stem_from_description(description)
    if stem:
        candidate = repo_root / f"workouts/planned/{sport_l}/{stem}.txt"
        if candidate.is_file():
            return candidate
    return None


def _zwo_stem_from_description(description: str) -> str | None:
    for m in ZWO_PATH_RE.finditer(description or ""):
        rel = m.group(1) or m.group(2)
        if not rel:
            continue
        name = rel if rel.endswith(".zwo") else f"{rel}.zwo"
        return Path(name).stem
    return None


def resolve_bike_zwo_path(
    description: str,
    sport: str,
    repo_root: Path,
    explicit_path: str | None = None,
) -> Path | None:
    """Bike ZWO from description or from linked planned/bike/*.txt (zwo: line or stem)."""
    found = resolve_zwo_path(description, sport, repo_root, explicit_path)
    if found:
        return found
    for m in PLANNED_SESSION_RE.finditer(description or ""):
        if "/bike/" not in m.group(1):
            continue
        planned = repo_root / m.group(1)
        if not planned.is_file():
            continue
        for line in planned.read_text(encoding="utf-8").splitlines():
            if line.startswith("zwo:"):
                rel = line.split(":", 1)[1].strip()
                cand = repo_root / rel
                if cand.is_file():
                    return cand
        stem = planned.stem
        cand = repo_root / f"workouts/zwo/bike/{stem}.zwo"
        if cand.is_file():
            return cand
    return None


def resolve_planned_session(description: str, sport: str, repo_root: Path) -> str | None:
    """Full Intervals description for run/swim/bike (not strength)."""
    path = resolve_planned_session_path(description, sport, repo_root)
    if path:
        return format_planned_session_for_intervals(path)
    return None


def planned_intervals_target(path: Path) -> str | None:
    return read_planned_meta(path).get("intervals_target")


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


def api_get(path: str, *, timeout: int = 60) -> bytes:
    """GET Intervals.icu API path (e.g. /athlete/0/wellness.csv?oldest=...)."""
    path = path if path.startswith("/") else f"/{path}"
    url = f"{API_BASE}{path}"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": auth_header(),
            "User-Agent": "LofotenLightAgent/1.0 (intervals api)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:2000]
        raise RuntimeError(f"Intervals API {e.code}: {detail}") from e


def fetch_wellness_csv(oldest: str, newest: str) -> bytes:
    aid = athlete_id()
    return api_get(
        f"/athlete/{aid}/wellness.csv?oldest={oldest}&newest={newest}",
        timeout=60,
    )


def put_wellness(day: str, fields: dict) -> dict:
    """Create/update one wellness row (day = YYYY-MM-DD). Only include fields to change."""
    aid = athlete_id()
    url = f"{API_BASE}/athlete/{aid}/wellness/{day}"
    body = json.dumps(fields).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="PUT",
        headers={
            "Authorization": auth_header(),
            "Content-Type": "application/json",
            "User-Agent": "LofotenLightAgent/1.0 (intervals wellness)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {"status": resp.status}
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:2000]
        raise RuntimeError(f"Intervals API {e.code}: {detail}") from e


def put_wellness_bulk(rows: list[dict]) -> dict | list:
    """Bulk wellness update. Each row must include id (YYYY-MM-DD) plus fields."""
    if not rows:
        return {"updated": 0}
    aid = athlete_id()
    url = f"{API_BASE}/athlete/{aid}/wellness-bulk"
    body = json.dumps(rows).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="PUT",
        headers={
            "Authorization": auth_header(),
            "Content-Type": "application/json",
            "User-Agent": "LofotenLightAgent/1.0 (intervals wellness)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {"status": resp.status}
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:2000]
        raise RuntimeError(f"Intervals API {e.code}: {detail}") from e


def delete_events_bulk(external_ids: list[str]) -> dict:
    """Delete calendar events by external_id (agent plan ids ll-agent-…)."""
    if not external_ids:
        return {"eventsDeleted": 0}
    aid = athlete_id()
    url = f"{API_BASE}/athlete/{aid}/events/bulk-delete"
    unique = sorted(set(external_ids))
    body = json.dumps([{"external_id": eid} for eid in unique]).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="PUT",
        headers={
            "Authorization": auth_header(),
            "Content-Type": "application/json",
            "User-Agent": "LofotenLightAgent/1.0 (intervals delete)",
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
