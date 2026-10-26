"""ICU HTTP DNS/network retry (US-8 / Copilot trust)."""

from __future__ import annotations

import socket
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from icu_http import call_with_icu_retry, is_retryable_icu_error, http_get_json


def test_dns_errors_are_retryable():
    assert is_retryable_icu_error(socket.gaierror(socket.EAI_NONAME, "Name or service not known"))
    assert is_retryable_icu_error(
        urllib.error.URLError(socket.gaierror(-2, "Name or service not known"))
    )
    assert is_retryable_icu_error(TimeoutError("timed out"))
    assert not is_retryable_icu_error(ValueError("bad key"))
    assert not is_retryable_icu_error(urllib.error.HTTPError("u", 401, "no", hdrs=None, fp=None))


def test_call_with_icu_retry_recovers():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.URLError(socket.gaierror(-2, "Name or service not known"))
        return {"ok": True}

    with patch("icu_http.time.sleep"):
        out = call_with_icu_retry(flaky, attempts=3, base_delay_sec=0.01)
    assert out == {"ok": True}
    assert calls["n"] == 3


def test_http_get_json_retries(monkeypatch):
    calls = {"n": 0}

    class FakeResp:
        def read(self):
            return b'[{"id":1}]'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=12):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.URLError(socket.gaierror(-2, "Name or service not known"))
        return FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with patch("icu_http.time.sleep"):
        data = http_get_json("https://intervals.icu/api/v1/x", {"Accept": "application/json"})
    assert data == [{"id": 1}]
    assert calls["n"] == 2
