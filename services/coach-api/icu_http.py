"""Shared Intervals.icu HTTP helpers — DNS/network retry for cloud robustness.

US-8 / Copilot trust: transient DNS and connection failures should not
surface as a one-shot hard fail when a short retry would succeed.
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Callable

# Transient DNS / connection failures worth retrying (US-8).
_RETRYABLE_DNS_MARKERS = (
    "name or service not known",
    "temporary failure in name resolution",
    "nodename nor servname",
    "getaddrinfo failed",
    "name resolution",
    "errno  -2",
    "errno -2",
    "errno  -3",
    "errno -3",
    "network is unreachable",
    "connection reset",
    "connection refused",
    "timed out",
    "timeout",
)


def is_retryable_icu_error(exc: BaseException) -> bool:
    """True for DNS / transient network errors worth a short retry."""
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, socket.gaierror):
        return True
    if isinstance(exc, socket.timeout):
        return True
    if isinstance(exc, urllib.error.HTTPError):
        # Retry 502/503/504 only — not auth or client errors.
        return int(getattr(exc, "code", 0) or 0) in (502, 503, 504)
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, (socket.gaierror, socket.timeout, TimeoutError)):
            return True
        text = str(reason or exc).lower()
        return any(m in text for m in _RETRYABLE_DNS_MARKERS)
    text = str(exc).lower()
    return any(m in text for m in _RETRYABLE_DNS_MARKERS)


def call_with_icu_retry(
    fn: Callable[[], Any],
    *,
    attempts: int = 3,
    base_delay_sec: float = 0.4,
) -> Any:
    """Run ``fn`` with short backoff on DNS/transient ICU network errors."""
    last: BaseException | None = None
    tries = max(1, int(attempts))
    for i in range(tries):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — classify then re-raise
            last = exc
            if i >= tries - 1 or not is_retryable_icu_error(exc):
                raise
            time.sleep(base_delay_sec * (2**i))
    assert last is not None
    raise last


def http_get_json(
    url: str,
    headers: dict[str, str],
    *,
    timeout: int = 12,
    attempts: int = 3,
) -> Any:
    """GET JSON with DNS/network retry. Raises on non-retryable failure."""

    def _once() -> Any:
        req = urllib.request.Request(url, method="GET", headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        if not raw:
            return []
        return json.loads(raw)

    return call_with_icu_retry(_once, attempts=attempts)
