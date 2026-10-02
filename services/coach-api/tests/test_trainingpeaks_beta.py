"""TrainingPeaks beta sync (mocked tpapi)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import config
import main as main_mod
from db import db_session, init_db, upsert_athlete_secrets
from trainingpeaks_beta.structure import structure_from_icu_event
from trainingpeaks_beta.sync import icu_event_to_tp_payload, preview_tp_push


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    athletes = tmp_path / "athletes"
    athletes.mkdir()
    monkeypatch.setattr(config, "DATABASE_PATH", db)
    monkeypatch.setattr(config, "DATABASE_URL", "")
    monkeypatch.setattr(config, "ATHLETES_DATA_DIR", athletes)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config, "TRAININGPEAKS_BETA_ENABLED", True)
    init_db(db)
    with TestClient(main_mod.app) as c:
        yield c, db


def test_structure_from_intervals_text():
    ev = {
        "category": "WORKOUT",
        "type": "Run",
        "_sport": "run",
        "target": "HR",
        "description": (
            "Warmup\n---intervals---\n"
            "Main Set 2x\n"
            "- 3m 70-75% LTHR\n"
            "- 2m 50% LTHR\n"
        ),
        "_duration_minutes": 45,
    }
    s = structure_from_icu_event(ev)
    assert s is not None
    assert "percentOfThresholdHr" in s
    assert "repetition" in s


def test_preview_tp_push_filters_notes():
    events = [
        {"category": "NOTE", "name": "Note"},
        {
            "category": "WORKOUT",
            "name": "Easy run",
            "type": "Run",
            "_sport": "run",
            "start_date_local": "2026-10-05T07:00:00",
            "_duration_minutes": 40,
            "description": "- 40m 65% LTHR",
        },
    ]
    out = preview_tp_push(events, athlete_id="12345")
    assert out["workouts_count"] == 1
    payload = icu_event_to_tp_payload(events[1], "12345")
    assert payload["workoutTypeValueId"] == 3
    assert payload["athleteId"] == "12345"


def _onboard(c) -> str:
    r = c.post(
        "/v1/onboarding",
        json={
            "display_name": "TP Beta",
            "username": "tp-beta-user",
            "coach_display_name": "Rocky",
            "goal_text": "Tri",
            "injury_notes": "",
            "notes": "",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["athlete"]["id"]


def test_tp_calendar_preview_confirm_mocked(client, monkeypatch):
    c, db = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}
    with db_session(db) as conn:
        upsert_athlete_secrets(
            conn,
            aid,
            intervals_api_key="k",
            intervals_athlete_id="i1",
            tp_auth_cookie="Production_tpAuth=test",
            tp_user_id="999",
            tp_sync_enabled=True,
        )
    c.post(
        "/v1/athlete/me/plan-blocks",
        headers=headers,
        json={
            "title": "Base",
            "start_date": "2026-10-05",
            "end_date": "2026-10-26",
            "weekly_hours": 8,
        },
    )
    def _fake_create(*_a, **_k):
        return None

    monkeypatch.setattr("trainingpeaks_beta.sync.create_planned_workout", _fake_create)
    prev = c.post(
        "/v1/athlete/me/trainingpeaks/beta/calendar/preview",
        headers=headers,
        json={},
    )
    assert prev.status_code == 200, prev.text
    body = prev.json()
    assert body.get("beta") is True
    assert body.get("workouts_count", 0) >= 1
    conf = c.post(
        "/v1/athlete/me/trainingpeaks/beta/calendar/confirm",
        headers=headers,
        json={"pending_id": body["pending_id"]},
    )
    assert conf.status_code == 200, conf.text
    assert conf.json().get("pushed", 0) >= 1
