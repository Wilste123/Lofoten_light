"""Optional Intervals.icu connectivity check (no env dependency)."""

from __future__ import annotations

import base64
import concurrent.futures
import json
import urllib.error
import urllib.request

API_BASE = "https://intervals.icu/api/v1"

# Soft-verify budget — never block the request handler longer than this.
DEFAULT_TIMEOUT_S = 5.0


def _request_athlete(api_key: str, athlete_id: str, timeout_s: float) -> tuple[bool, str | None]:
    token = base64.b64encode(f"API_KEY:{api_key}".encode()).decode()
    url = f"{API_BASE}/athlete/{athlete_id}"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Basic {token}",
            "User-Agent": "LofotenCoachApi/0.1 (intervals smoke)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if resp.status >= 400:
                return False, f"Intervals svarte {resp.status}"
            try:
                json.loads(raw)
            except json.JSONDecodeError:
                return False, "Ugyldig svar fra Intervals"
            return True, None
    except urllib.error.HTTPError as e:
        return False, f"Intervals HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, f"Nettverk: {e.reason}"
    except TimeoutError:
        return False, "Tidsavbrudd mot Intervals"
    except Exception as e:  # noqa: BLE001 — soft fail for smoke
        return False, str(e) or "Ukjent feil"


def smoke_test_intervals(
    api_key: str,
    athlete_id: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> tuple[bool, str | None]:
    """
    GET /athlete/{id} with Basic API_KEY auth.

    Returns (ok, error_message). Network/auth/timeout failures are soft —
    caller still stores credentials. Hard wall-clock cap via thread so DNS
    stalls cannot hang the API handler.
    """
    key = (api_key or "").strip()
    aid = (athlete_id or "").strip()
    if not key or not aid:
        return False, "Mangler API-nøkkel eller athlete ID"

    # Slightly under wall budget so urlopen can finish before we give up.
    inner = max(1.0, float(timeout_s) - 0.4)
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        fut = pool.submit(_request_athlete, key, aid, inner)
        try:
            return fut.result(timeout=float(timeout_s))
        except concurrent.futures.TimeoutError:
            fut.cancel()
            return False, "Tidsavbrudd mot Intervals"
    finally:
        # Do not wait on a stuck network thread — soft-verify must return.
        pool.shutdown(wait=False, cancel_futures=True)