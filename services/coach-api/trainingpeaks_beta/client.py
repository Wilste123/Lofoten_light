"""Low-level TrainingPeaks fitness API (planned workouts)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from trainingpeaks_beta.auth import TP_API_BASE, fetch_bearer_token

_TIMEOUT = 60


def create_planned_workout(
    auth_cookie: str,
    athlete_id: str,
    payload: dict[str, Any],
) -> None:
    bearer = fetch_bearer_token(auth_cookie)
    url = f"{TP_API_BASE}/fitness/v6/athletes/{athlete_id}/workouts"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "LofotenCoachApi/0.1 (TP beta sync)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            if resp.status not in (200, 201, 204):
                raise RuntimeError(f"TP create workout uventet status {resp.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:600]
        raise RuntimeError(f"TP create workout HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"TP create workout nettverk: {exc}") from exc
