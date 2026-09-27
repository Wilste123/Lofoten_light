"""Plan sync workouts via CLI builder + knowledge templates."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import config
import main as main_mod
from db import db_session, init_db, upsert_athlete_secrets
from plan_workouts import (
    build_plan_sync_bundle,
    build_plan_week_icu_events,
    knowledge_paths_for_workouts,
    signals_from_athlete,
)


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
        yield c, athletes, db


def _onboard(c) -> str:
    r = c.post(
        "/v1/onboarding",
        json={
            "display_name": "Testa",
            "username": "testa-planw",
            "coach_display_name": "Rocky",
            "goal_text": "Triathlon comeback",
            "injury_notes": "",
            "notes": "tidligere syklist comeback etter pause",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["athlete"]["id"]


def test_knowledge_paths_include_ukemaler_and_conditional():
    paths = knowledge_paths_for_workouts(
        {
            "goal_text": "Lofoten half",
            "notes": "nybegynner aldri trent",
            "injury_notes": "",
        }
    )
    assert "coach/ukemaler.md" in paths
    assert "triathlon/periodisering-mot-2027.md" in paths
    assert "svom/nybegynner-til-triatlet.md" in paths


def test_builder_emits_zwo_and_planned_shape():
    blocks = [
        {
            "id": "b1",
            "title": "Re-etablering",
            "theme": "Kontakt alle ben",
            "start_date": "2026-09-28",
            "end_date": "2026-10-25",
            "weekly_hours": 8.5,
        }
    ]
    events = build_plan_week_icu_events(
        blocks,
        signals={"returning": True, "beginner": False, "injury": False},
        weeks=1,
        today=date(2026, 9, 28),
    )
    assert len(events) >= 5
    assert all(e["category"] == "WORKOUT" for e in events)
    assert all(str(e["external_id"]).startswith("ll-coach-w-") for e in events)
    # At least one bike ZWO attached via CLI builder
    with_zwo = [e for e in events if e.get("file_contents") and e.get("filename")]
    assert len(with_zwo) >= 1
    assert any("Ride" == e.get("type") for e in events)
    # Run/swim get planned Intervals syntax (description enriched)
    runish = [e for e in events if e.get("type") == "Run"]
    assert runish
    assert "###" in (runish[0].get("description") or "") or "Warmup" in (
        runish[0].get("description") or ""
    )


def test_beginner_differs_from_injury_templates():
    blocks = [
        {
            "id": "b1",
            "title": "Grunnlag",
            "theme": "etablering",
            "start_date": "2026-09-28",
            "end_date": "2026-11-01",
            "weekly_hours": 4,
        }
    ]
    beg = build_plan_week_icu_events(
        blocks,
        signals={"beginner": True},
        weeks=1,
        today=date(2026, 9, 28),
    )
    inj = build_plan_week_icu_events(
        blocks,
        signals={"injury": True, "beginner": False},
        weeks=1,
        today=date(2026, 9, 28),
    )
    beg_names = {e["name"] for e in beg}
    inj_names = {e["name"] for e in inj}
    assert beg_names != inj_names
    assert any("prehab" in n.lower() or "ST04" in n or "isjas" in n.lower() for n in inj_names)


def test_bundle_includes_notes_and_workouts():
    blocks = [
        {
            "id": "b1",
            "title": "Base",
            "theme": "base",
            "start_date": "2026-09-28",
            "end_date": "2026-10-25",
            "weekly_hours": 8,
        }
    ]
    bundle = build_plan_sync_bundle(
        blocks,
        athlete={"notes": "comeback etter pause", "goal_text": "triatlon"},
        weeks=2,
        today=date(2026, 9, 28),
    )
    assert bundle["workouts_count"] >= 8
    assert bundle["notes_count"] >= 1
    assert bundle["zwo_count"] >= 1
    assert bundle["builder"].endswith("build_workout_event")
    assert "coach/ukemaler.md" in bundle["knowledge_paths"]


def test_calendar_preview_push_uses_builder(client, monkeypatch):
    c, _athletes, db = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}
    with db_session(db) as conn:
        upsert_athlete_secrets(
            conn, aid, intervals_api_key="k", intervals_athlete_id="i1"
        )

    created = c.post(
        "/v1/athlete/me/plan-blocks",
        headers=headers,
        json={
            "title": "Base 1",
            "theme": "Re-etablering kontakt",
            "start_date": "2026-09-28",
            "end_date": "2026-10-25",
            "weekly_hours": 8,
        },
    )
    assert created.status_code == 200

    preview = c.post(
        "/v1/athlete/me/intervals/calendar/preview",
        headers=headers,
        json={"op": "push"},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["confirm_required"] is True
    assert body["workouts_count"] >= 5
    assert body["notes_count"] >= 1
    assert body["zwo_count"] >= 1
    assert any(e.get("category") == "WORKOUT" for e in body["events"])
    assert any(
        str(e.get("external_id") or "").startswith("ll-coach-w-") for e in body["events"]
    )

    captured = {}

    def _fake_post(api_key, athlete_id, events, **kwargs):
        captured["events"] = events
        return {"count": len(events)}

    monkeypatch.setattr(main_mod, "post_events_bulk", _fake_post)
    conf = c.post(
        "/v1/athlete/me/intervals/calendar/confirm",
        headers=headers,
        json={"pending_id": body["pending_id"]},
    )
    assert conf.status_code == 200, conf.text
    assert conf.json()["pushed"] == body["count"]
    assert any(e.get("category") == "WORKOUT" for e in captured["events"])
    assert any(e.get("file_contents") for e in captured["events"])


def test_setup_preview_shows_workouts_not_notes_only(client):
    c, *_ = client
    preview = c.post(
        "/v1/setup/plan/preview",
        json={
            "display_name": "Ada",
            "username": "ada-w",
            "goal_text": "5k",
            "background_notes": "nybegynner",
            "weekly_hours_target": 4,
            "enrich_with_llm": False,
        },
    )
    assert preview.status_code == 200, preview.text
    sync = preview.json()["intervals_sync"]
    assert sync["kind"] == "calendar_notes_and_library_workouts"
    assert sync["workouts_count"] >= 3
    assert sync.get("builder")
    assert any(
        (e.get("category") == "WORKOUT") or e.get("preview_no")
        for e in (sync.get("workouts_preview") or sync.get("events_preview") or [])
    )


def test_signals_from_athlete_injury():
    s = signals_from_athlete({"injury_notes": "isjas og ryggplager"})
    assert s["injury"] is True
