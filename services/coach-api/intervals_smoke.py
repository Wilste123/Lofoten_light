"""Optional Intervals.icu connectivity check (no env dependency)."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

API_BASE = "https://intervals.icu/api/v1"


def smoke_test_intervals(api_key: str, athlete_id: str) -> tuple[bool, str | None]:
    """
    GET /athlete/{id} with Basic API_KEY auth.
    Returns (ok, error_message). Network/auth failures are soft — caller still stores.
    """
    key = (api_key or "").strip()
    aid = (athlete_id or "").strip()
    if not key or not aid:
        return False, "Mangler API-nøkkel eller athlete ID"
    token = base64.b64encode(f"API_KEY:{key}".encode()).decode()
    url = f"{API_BASE}/athlete/{aid}"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Basic {token}",
            "User-Agent": "LofotenCoachApi/0.1 (intervals smoke)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if resp.status >= 400:
                return False, f"Intervals svarte {resp.status}"
            # Confirm JSON parses; id field optional
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
