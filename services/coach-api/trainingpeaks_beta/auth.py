"""TrainingPeaks session cookie → short-lived bearer token (tpapi)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

TP_API_BASE = "https://tpapi.trainingpeaks.com"
_TIMEOUT = 25


def normalize_tp_auth_cookie(raw: str) -> str:
    """Keep Production_tpAuth=… from pasted cookie header or DevTools export."""
    text = (raw or "").strip()
    if not text:
        return ""
    m = re.search(r"(Production_tpAuth=[^;\s]+)", text, re.IGNORECASE)
    if m:
        return m.group(1)
    if "=" in text and not text.lower().startswith("cookie:"):
        return text.split(";")[0].strip()
    return text


def fetch_bearer_token(auth_cookie: str) -> str:
    cookie = normalize_tp_auth_cookie(auth_cookie)
    if not cookie:
        raise ValueError("Mangler Production_tpAuth-cookie")
    url = f"{TP_API_BASE}/users/v3/token"
    req = urllib.request.Request(
        url,
        headers={
            "Cookie": cookie,
            "Accept": "application/json",
            "User-Agent": "LofotenCoachApi/0.1 (TP beta sync)",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:400]
        raise RuntimeError(f"TP token HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"TP token nettverk: {exc}") from exc
    token = (data or {}).get("accessToken") or (data or {}).get("access_token")
    if not token:
        raise RuntimeError("TP token-svar mangler accessToken")
    return str(token)


def fetch_tp_user(bearer: str) -> dict[str, Any]:
    url = f"{TP_API_BASE}/users/v3/user"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {bearer}",
            "Accept": "application/json",
            "User-Agent": "LofotenCoachApi/0.1 (TP beta sync)",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:400]
        raise RuntimeError(f"TP user HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"TP user nettverk: {exc}") from exc
