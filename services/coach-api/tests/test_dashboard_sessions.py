"""Dashboard body-metrics toggle + session completion persistence."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import config
import main as main_mod
from db import (
    db_session,
    get_session_completion,
    init_db,
    list_session_completions,
)
from wellness import analyze_body, analyze_sleep


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    athletes = tmp_path / "athletes"
    athletes.mkdir()
    monkeypatch.setattr(config, "DATABASE_PATH", db)
    monkeypatch.setattr(config, "ATHLETES_DATA_DIR", athletes)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    init_db(db)
    with TestClient(main_mod.app) as c:
        yield c, athletes


def _onboard(c) -> str:
    r = c.post(
        "/v1/onboarding",
        json={
            "display_name": "Testa",
            "username": "testa",
            "coach_display_name": "Rocky",
            "goal_text": "Base",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["athlete"]["id"]


def test_show_body_metrics_default_true_and_toggle_hides_body(client):
    c, _athletes = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}

    me = c.get("/v1/athlete/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["athlete"]["show_body_metrics"] is True

    fake_wellness = {
        "window": {"start": "2026-09-14", "end": "2026-09-27"},
        "source": "intervals",
        "fetch_error": False,
        "fetch_error_detail": None,
        "sleep": {"available": True, "avg_hours": 7.2, "note": "OK"},
        "body": {
            "available": True,
            "latest_weight_kg": 78.5,
            "latest_body_fat_pct": 14.2,
            "note": "stabil",
        },
        "load_wellness": {"available": True, "ctl": 40, "atl": 35, "readiness": 8},
    }

    with patch("main.resolve_wellness_bundle", return_value=fake_wellness):
        dash = c.get("/v1/dashboard", headers=headers)
    assert dash.status_code == 200, dash.text
    body = dash.json()
    assert body["show_body_metrics"] is True
    assert body["body_hidden"] is False
    assert body["body"]["latest_weight_kg"] == 78.5
    assert body["compliance_app_computed"] is True
    assert body["compliance_written_to_intervals"] is False

    patch_r = c.patch(
        "/v1/athlete/me",
        headers=headers,
        json={"show_body_metrics": False},
    )
    assert patch_r.status_code == 200
    assert patch_r.json()["athlete"]["show_body_metrics"] is False

    def _bundle_hidden(secrets, *, days=14, today=None, include_body=True):
        out = dict(fake_wellness)
        if not include_body:
            out["body"] = None
            out["body_hidden"] = True
        return out

    with patch("main.resolve_wellness_bundle", side_effect=_bundle_hidden):
        dash2 = c.get("/v1/dashboard", headers=headers)
    assert dash2.status_code == 200
    data2 = dash2.json()
    assert data2["show_body_metrics"] is False
    assert data2["body_hidden"] is True
    assert data2["body"] is None


def test_session_completion_persists_and_profile_note(client):
    c, athletes = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}
    sid = "act:icu-42"

    r = c.post(
        f"/v1/sessions/{sid}/completion",
        headers=headers,
        json={
            "status": "skipped",
            "reason": "tired",
            "note": "Kort natt",
            "session_name": "Z2 sykkel",
            "session_date": "2026-09-26",
            "discipline": "bike",
        },
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["written_to_intervals"] is False
    assert payload["completion"]["status"] == "skipped"
    assert payload["completion"]["external_session_id"] == sid
    assert "Øktlogg" in (payload["athlete_notes"] or "")
    assert "Z2 sykkel" in (payload["athlete_notes"] or "")

    with db_session(config.DATABASE_PATH) as conn:
        row = get_session_completion(conn, aid, sid)
        assert row is not None
        assert row["status"] == "skipped"
        assert row["reason"] == "tired"
        rows = list_session_completions(conn, aid)
        assert len(rows) == 1

    profile = (athletes / aid / "profile.md").read_text(encoding="utf-8")
    assert "Z2 sykkel" in profile or "Øktlogg" in profile or "skipped" in profile

    # Upsert updates status
    r2 = c.post(
        f"/v1/sessions/{sid}/completion",
        headers=headers,
        json={"status": "completed", "reason": "", "note": "Tok den neste dag"},
    )
    assert r2.status_code == 200
    assert r2.json()["completion"]["status"] == "completed"

    recent = c.get("/v1/sessions/completions/recent", headers=headers)
    assert recent.status_code == 200
    assert len(recent.json()["completions"]) == 1


def test_sessions_soft_fail_without_credentials(client):
    c, _athletes = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}
    r = c.get("/v1/sessions", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "none"
    assert data["recent"] == []
    assert "Compliance" in data["compliance_note"]


def test_analyze_sleep_and_body_helpers():
    rows = [
        {"id": "2026-09-20", "sleepSecs": 7 * 3600, "sleepScore": 80, "weight": 79.0},
        {"id": "2026-09-21", "sleepSecs": 6 * 3600, "sleepScore": 70, "weight": 78.8, "bodyFat": 14.5},
        {"id": "2026-09-22", "sleepSecs": 8 * 3600, "sleepScore": 85, "weight": 78.6, "bodyFat": 14.3},
    ]
    sleep = analyze_sleep(rows)
    assert sleep["available"] is True
    assert sleep["days_with_data"] == 3
    assert sleep["short_nights"] == 1
    body = analyze_body(rows)
    assert body["available"] is True
    assert body["latest_weight_kg"] == 78.6
    assert body["latest_body_fat_pct"] == 14.3
