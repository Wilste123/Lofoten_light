"""Coach plan quality: constraints-grounded meso + Plan/Økter same planned_sessions model."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import config
import main as main_mod
from db import count_planned_sessions, db_session, init_db, list_planned_sessions
from sessions_service import merge_planned_sessions, planned_session_to_public
from setup_plan import (
    build_setup_preview,
    clamp_blocks_weekly_hours,
    estimate_weekly_hours,
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


def test_weekly_hours_clamped_by_sessions_per_week():
    # Default without sessions would be ~8h; 3×/uke must stay modest
    h = estimate_weekly_hours(None, "", {}, sessions_per_week=3)
    assert 1.5 <= h <= 4.0
    # Explicit high hours still capped
    h2 = estimate_weekly_hours(12, "12 timer/uke", {}, sessions_per_week=3)
    assert h2 <= 4.0
    # 6× allows more volume
    h3 = estimate_weekly_hours(None, "", {}, sessions_per_week=6)
    assert h3 >= 3.0
    assert h3 <= 8.0
    assert h3 > h


def test_clamp_blocks_rejects_llm_hour_spikes():
    blocks = [
        {
            "title": "Base",
            "phase": "base",
            "start_date": "2026-09-28",
            "end_date": "2026-11-01",
            "weekly_hours": 18.0,
        }
    ]
    out = clamp_blocks_weekly_hours(blocks, weekly_hours=4.0, sessions_per_week=3)
    assert out[0]["weekly_hours"] <= 4.0 * 1.15 + 0.2


def test_setup_preview_deterministic_for_explicit_constraints():
    prev = build_setup_preview(
        {
            "display_name": "Kari",
            "goal_text": "Halvmaraton 2027",
            "schedule_notes": "3 økter/uke",
            "sessions_per_week": 3,
            "allowed_disciplines": ["run", "strength"],
            "fitness_notes": "Form OK",
            "athlete_type": "half_marathon_runner",
            "background_notes": "Form OK, løp og styrke",
        },
        knowledge_dir=config.KNOWLEDGE_DIR,
        api_key="",
        enrich=False,
        today=date(2026, 9, 28),
    )
    assert prev["sessions_per_week"] == 3
    assert prev["plan_source"] == "deterministic_fallback"
    titles = " ".join(b["title"] for b in prev["plan_blocks"]).lower()
    assert "re-etablering" not in titles
    for b in prev["plan_blocks"]:
        assert float(b["weekly_hours"]) <= 5.0


def test_merge_planned_into_empty_okter_bundle():
    today = date(2026, 9, 29)
    base = {
        "window": {
            "start": (today - timedelta(days=14)).isoformat(),
            "end": (today + timedelta(days=14)).isoformat(),
        },
        "source": "none",
        "upcoming": [],
        "today": [],
        "planned": [],
        "planned_not_done": [],
        "recent": [],
        "completed": [],
        "notes": [],
        "cancelled": [],
        "library": [],
        "compliance_note": "ICU only",
        "truth": {"completed_source": "intervals_activities"},
    }
    rows = [
        {
            "session_date": (today + timedelta(days=2)).isoformat(),
            "sport": "run",
            "name": "Løp easy 40",
            "duration_minutes": 40,
            "start_time": "07:00",
            "external_id": "ll-coach-w-20261001-lopeasy-0",
            "description": "- Warmup 10\n- Main easy\n- Cooldown 5",
        },
        {
            "session_date": (today + timedelta(days=4)).isoformat(),
            "sport": "strength",
            "name": "Styrke base",
            "duration_minutes": 35,
            "external_id": "ll-coach-w-20261003-styrke-1",
        },
    ]
    merged = merge_planned_sessions(base, rows, today=today)
    assert merged["app_planned_merged"] == 2
    assert merged["source"] == "planned_sessions"
    assert len(merged["upcoming"]) == 2
    assert len(merged["library"]) >= 1
    # Must not invent completed
    assert merged["completed"] == []
    assert merged["truth"]["completed_source"] == "intervals_activities"


def test_planned_session_to_public_shape():
    today = date(2026, 9, 29)
    pub = planned_session_to_public(
        {
            "session_date": (today + timedelta(days=1)).isoformat(),
            "sport": "run",
            "name": "Easy",
            "duration_minutes": 40,
            "external_id": "ll-coach-w-20260930-easy-0",
        },
        today=today,
        window_start=today - timedelta(days=7),
        window_end=today + timedelta(days=14),
    )
    assert pub is not None
    assert pub["calendar_role"] == "planned_workout"
    assert pub["training_status"] == "planned"
    assert pub["app_planned"] is True
    assert pub["id"].startswith("evt:")


def test_setup_confirm_visible_in_plan_and_okter(client):
    """After confirm: planned_sessions ≫ 0 AND GET /v1/sessions shows upcoming (no ICU)."""
    c, _athletes, _db = client
    preview = c.post(
        "/v1/setup/plan/preview",
        json={
            "display_name": "Ada",
            "username": "ada-planq",
            "goal_text": "Halvmaraton 2027",
            "background_notes": "Form OK, 4 økter i uka, løp og styrke",
            "schedule_notes": "4 økter/uke",
            "sessions_per_week": 4,
            "allowed_disciplines": ["run", "strength"],
            "fitness_notes": "Form OK",
            "athlete_type": "half_marathon_runner",
            "enrich_with_llm": False,
        },
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["sessions_per_week"] == 4
    # Hours coherent with 4×/uke
    assert float(body["weekly_hours_target"]) <= 4 * 1.25 + 0.05

    conf = c.post(
        "/v1/setup/confirm",
        json={
            "display_name": "Ada",
            "username": "ada-planq",
            "goal_text": body.get("athlete_patch", {}).get("goal_text")
            or "Halvmaraton 2027",
            "schedule_notes": "4 økter/uke",
            "sessions_per_week": 4,
            "allowed_disciplines": ["run", "strength"],
            "athlete_type": "half_marathon_runner",
            "plan_blocks": body["plan_blocks"],
            "athlete_patch": body.get("athlete_patch") or {},
            "prepare_intervals_sync": False,
        },
    )
    assert conf.status_code == 200, conf.text
    aid = conf.json()["athlete"]["id"]
    headers = {"X-Athlete-Id": aid}
    n = conf.json().get("planned_sessions_count") or 0
    assert n >= 8, conf.json()

    planned = c.get("/v1/athlete/me/planned-sessions", headers=headers)
    assert planned.status_code == 200
    assert planned.json()["total"] >= 8

    sess = c.get("/v1/sessions", headers=headers)
    assert sess.status_code == 200, sess.text
    data = sess.json()
    assert data.get("app_planned_merged", 0) >= 1 or len(data.get("upcoming") or []) >= 1
    assert len(data.get("upcoming") or []) + len(data.get("today") or []) >= 1
    assert data.get("source") in ("planned_sessions", "intervals+planned_sessions")
    # Library populated from app plan without Intervals
    assert len(data.get("library") or []) >= 1
    # Still no invented completed
    assert (data.get("completed") or []) == []


def test_chat_and_setup_share_constraint_hours(client):
    """Same athlete constraints → same hours band in preview vs persistable sessions."""
    c, _athletes, db = client
    preview = c.post(
        "/v1/setup/plan/preview",
        json={
            "display_name": "Bo",
            "username": "bo-planq",
            "goal_text": "Komme i form",
            "schedule_notes": "3 økter/uke",
            "sessions_per_week": 3,
            "allowed_disciplines": ["run", "strength"],
            "athlete_type": "general_endurance",
            "enrich_with_llm": False,
        },
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    conf = c.post(
        "/v1/setup/confirm",
        json={
            "display_name": "Bo",
            "username": "bo-planq",
            "goal_text": "Komme i form",
            "sessions_per_week": 3,
            "allowed_disciplines": ["run", "strength"],
            "athlete_type": "general_endurance",
            "plan_blocks": body["plan_blocks"],
            "athlete_patch": body.get("athlete_patch") or {},
            "prepare_intervals_sync": False,
        },
    )
    assert conf.status_code == 200, conf.text
    aid = conf.json()["athlete"]["id"]
    with db_session(db) as conn:
        rows = list_planned_sessions(conn, aid)
        n = count_planned_sessions(conn, aid)
    assert n == len(rows) >= 6
    sports = {str(r.get("sport") or "").lower() for r in rows[:20]}
    assert "swim" not in sports
    assert "bike" not in sports
    # ~3 sessions per week across horizon
    assert n / max(1, conf.json().get("plan_horizon_weeks") or 1) <= 4.5
