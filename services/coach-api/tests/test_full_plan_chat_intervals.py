"""Full plan-to-goal + chat → preview → confirm → persist (+ Intervals pending).

Architecture invariant: Utøver → AI → Forslag → Preview → Confirm → Lagre → Synkroniser.
No autonomous rewrite loops. SQLite planned_sessions is app SoT to goal_race_date;
Intervals WORKOUT sync stays near-term (ICU_SYNC_WEEKS).
"""

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
from athlete_constraints import ICU_SYNC_WEEKS, MAX_PLAN_HORIZON_WEEKS
from chat_service import extract_plan_update
from db import (
    count_planned_sessions,
    db_session,
    get_athlete,
    init_db,
    list_planned_sessions,
)
from plan_workouts import (
    build_plan_sync_bundle,
    persistable_plan_payload,
    plan_horizon_weeks,
    readiness_adjustment_hints,
)
from setup_plan import build_setup_preview


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


def _confirm_setup(c, *, username="plan-hz", goal_year=2027, sessions=4):
    preview = c.post(
        "/v1/setup/plan/preview",
        json={
            "display_name": "Ada",
            "username": username,
            "goal_text": f"Halvmaraton {goal_year}",
            "background_notes": f"Form OK, {sessions} økter i uka, løp og styrke",
            "schedule_notes": f"{sessions} økter/uke",
            "sessions_per_week": sessions,
            "allowed_disciplines": ["run", "strength"],
            "fitness_notes": "Form OK",
            "athlete_type": "half_marathon_runner",
            "enrich_with_llm": False,
        },
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    conf = c.post(
        "/v1/setup/confirm",
        json={
            "display_name": "Ada",
            "username": username,
            "goal_text": body.get("athlete_patch", {}).get("goal_text")
            or f"Halvmaraton {goal_year}",
            "schedule_notes": f"{sessions} økter/uke",
            "sessions_per_week": sessions,
            "allowed_disciplines": ["run", "strength"],
            "athlete_type": "half_marathon_runner",
            "plan_blocks": body["plan_blocks"],
            "athlete_patch": body.get("athlete_patch") or {},
            "prepare_intervals_sync": False,
            "enrich_with_llm": False,
        },
    )
    assert conf.status_code == 200, conf.text
    return conf.json()


def test_plan_horizon_weeks_to_goal():
    today = date(2026, 9, 28)
    athlete = {"goal_race_date": "2027-05-15"}
    blocks = [
        {
            "start_date": "2026-09-28",
            "end_date": "2027-05-14",
            "title": "Base",
            "weekly_hours": 6,
        }
    ]
    w = plan_horizon_weeks(blocks, athlete=athlete, today=today)
    assert w > ICU_SYNC_WEEKS
    assert w <= MAX_PLAN_HORIZON_WEEKS
    # ~33 weeks Sep→May
    assert 20 <= w <= 40


def test_persistable_payload_covers_goal_not_just_two_weeks():
    today = date(2026, 9, 28)
    athlete = {
        "athlete_type": "half_marathon_runner",
        "goal_text": "Halvmaraton 2027",
        "goal_race_date": "2027-05-15",
        "allowed_disciplines": ["run", "strength"],
        "sessions_per_week": 4,
    }
    prev = build_setup_preview(
        {
            "display_name": "Ada",
            "goal_text": athlete["goal_text"],
            "goal_race_date": athlete["goal_race_date"],
            "sessions_per_week": 4,
            "allowed_disciplines": ["run", "strength"],
            "athlete_type": "half_marathon_runner",
            "fitness_notes": "Form OK",
        },
        knowledge_dir=config.KNOWLEDGE_DIR,
        api_key="",
        enrich=False,
        today=today,
    )
    payload = persistable_plan_payload(
        prev["plan_blocks"], athlete={**athlete, **(prev.get("athlete_patch") or {})}, today=today
    )
    assert payload["weeks"] > ICU_SYNC_WEEKS
    assert payload["count"] > 4 * ICU_SYNC_WEEKS
    assert payload["icu_sync_weeks"] == ICU_SYNC_WEEKS
    # Sync bundle still near-term
    bundle = build_plan_sync_bundle(
        prev["plan_blocks"],
        athlete=athlete,
        weeks=ICU_SYNC_WEEKS,
        include_notes=True,
        today=today,
        allow_degraded=True,
    )
    assert bundle["weeks"] == ICU_SYNC_WEEKS
    assert bundle["workouts_count"] <= 4 * ICU_SYNC_WEEKS + 2


def test_setup_confirm_persists_full_horizon(client):
    c, _athletes, db = client
    data = _confirm_setup(c, username="full-hz")
    assert data["planned_sessions_count"] > 8  # more than 2w × 4
    assert data["plan_horizon_weeks"] > ICU_SYNC_WEEKS
    assert data["written_to_intervals"] is False
    aid = data["athlete"]["id"]
    with db_session(db) as conn:
        n = count_planned_sessions(conn, aid)
        sessions = list_planned_sessions(conn, aid)
        ath = get_athlete(conn, aid)
    assert n == data["planned_sessions_count"]
    assert sessions
    last = sessions[-1]["session_date"]
    goal = ath.get("goal_race_date") or ""
    assert goal
    # Last planned session should be near goal (within ~2 weeks)
    assert last <= goal
    assert last[:4] == goal[:4] or last >= "2026-12-01"

    listed = c.get(
        "/v1/athlete/me/planned-sessions",
        headers={"X-Athlete-Id": aid},
    )
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == n
    assert body["goal_race_date"] == goal


def test_readiness_hints_ease_and_soft_fail():
    empty = readiness_adjustment_hints({"available": False})
    assert empty["available"] is False
    assert empty["tone"] == "unknown"
    assert empty["recommendations_nb"] == []

    ease = readiness_adjustment_hints(
        {
            "available": True,
            "sleep_avg_hours": 5.5,
            "sleep_avg_score": 50,
            "readiness": 3,
            "ctl": 40,
            "atl": 60,
        }
    )
    assert ease["tone"] == "ease"
    assert ease["recommendations_nb"]
    assert any("Søvn" in r or "Readiness" in r for r in ease["recommendations_nb"])

    ok = readiness_adjustment_hints(
        {
            "available": True,
            "sleep_avg_hours": 7.5,
            "hrv_avg_7d": 55,
            "readiness": 8,
            "ctl": 40,
            "atl": 35,
        }
    )
    assert ok["tone"] == "ok"


def test_extract_plan_update_fence():
    reply = (
        "Vi bygger om grovplanen mot mai.\n"
        "```plan_update\n"
        '{"rebuild":true,"ease_load":true,"reason":"Dårlig søvn + ny måldato"}\n'
        "```"
    )
    display, prop = extract_plan_update(reply)
    assert "plan_update" not in display
    assert prop is not None
    assert prop["rebuild"] is True
    assert prop["ease_load"] is True
    assert prop["confirm_required"] is True


def test_chat_plan_update_preview_confirm_persist(client):
    c, _athletes, db = client
    setup = _confirm_setup(c, username="chat-plan")
    aid = setup["athlete"]["id"]
    before = setup["planned_sessions_count"]

    llm_reply = (
        "Ok — vi justerer planen mot måldato.\n"
        "```plan_update\n"
        '{"rebuild":true,"reason":"Utøver ba om planjustering"}\n'
        "```"
    )
    with (
        patch(
            "main.list_sessions",
            return_value={
                "source": "none",
                "recent": [],
                "upcoming": [],
                "today": [],
                "window": None,
            },
        ),
        patch("main.call_llm", return_value=llm_reply),
        patch(
            "main.resolve_wellness_bundle",
            return_value={
                "recovery_signals": {
                    "available": True,
                    "sleep_avg_hours": 5.8,
                    "readiness": 4,
                    "as_signals_only": True,
                },
                "sleep": {"available": True, "avg_hours": 5.8},
                "load_wellness": {"available": True, "readiness": 4},
            },
        ),
    ):
        r = c.post(
            "/v1/chat",
            headers={"X-Athlete-Id": aid},
            json={"message": "Kan du justere planen frem til måldato?"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("plan_proposal")
    prop = data["plan_proposal"]
    assert prop["plan_blocks"]
    assert prop["planned_sessions_count"] > ICU_SYNC_WEEKS
    assert prop["confirm_required"] is True
    assert "plan_update" not in data["reply"]
    # Readiness influenced recommendations (proposal, not auto-write)
    hints = prop.get("readiness_hints") or {}
    assert hints.get("available") is True
    assert hints.get("tone") == "ease"

    # Confirm → persist full horizon + no silent ICU write
    done = c.post(
        "/v1/athlete/me/plan/adjust/confirm",
        headers={"X-Athlete-Id": aid},
        json={
            "plan_blocks": prop["plan_blocks"],
            "athlete_patch": prop.get("athlete_patch") or {},
            "prepare_intervals_sync": False,
        },
    )
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["written_to_intervals"] is False
    assert body["planned_sessions_count"] >= before // 2  # still a real horizon
    assert body["intervals_pending"] is None

    with db_session(db) as conn:
        n = count_planned_sessions(conn, aid)
    assert n == body["planned_sessions_count"]


def test_plan_adjust_preview_includes_horizon_and_readiness(client):
    c, _athletes, _db = client
    setup = _confirm_setup(c, username="adj-hz")
    aid = setup["athlete"]["id"]
    with patch(
        "main.resolve_wellness_bundle",
        side_effect=RuntimeError("no wellness"),
    ):
        adj = c.post(
            "/v1/athlete/me/plan/adjust/preview",
            headers={"X-Athlete-Id": aid},
            json={"enrich_with_llm": False},
        )
    assert adj.status_code == 200, adj.text
    body = adj.json()
    assert body["planned_sessions_count"] > 8
    assert body["plan_horizon_weeks"] > ICU_SYNC_WEEKS
    assert "2 uker" in (body.get("workout_horizon_note_nb") or "") or "Intervals" in (
        body.get("workout_horizon_note_nb") or ""
    )
    # Soft-fail readiness
    rh = body.get("readiness_hints") or {}
    assert rh.get("available") is False
    sync = body.get("intervals_sync") or {}
    assert sync.get("workouts_count") == 4 * ICU_SYNC_WEEKS  # near-term only


def test_confirm_with_intervals_pending_uses_near_window(client):
    c, _athletes, db = client
    setup = _confirm_setup(c, username="sync-near")
    aid = setup["athlete"]["id"]
    with db_session(db) as conn:
        from db import upsert_athlete_secrets

        upsert_athlete_secrets(
            conn, aid, intervals_api_key="test-key", intervals_athlete_id="i123"
        )

    prev = c.post(
        "/v1/athlete/me/plan/adjust/preview",
        headers={"X-Athlete-Id": aid},
        json={"enrich_with_llm": False},
    ).json()

    with patch(
        "main.build_plan_sync_bundle",
        return_value={
            "events": [{"external_id": "ll-coach-w-1", "name": "Test"}],
            "events_preview": [{"external_id": "ll-coach-w-1", "name": "Test"}],
            "workouts_preview": [],
            "notes_count": 1,
            "workouts_count": 8,
            "zwo_count": 0,
            "count": 1,
            "weeks": ICU_SYNC_WEEKS,
            "builder": "test",
            "knowledge_paths": [],
            "error": None,
        },
    ):
        done = c.post(
            "/v1/athlete/me/plan/adjust/confirm",
            headers={"X-Athlete-Id": aid},
            json={
                "plan_blocks": prev["plan_blocks"],
                "athlete_patch": prev.get("athlete_patch") or {},
                "prepare_intervals_sync": True,
            },
        )
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["written_to_intervals"] is False
    assert body["planned_sessions_count"] > 8
    assert body["intervals_pending"] is not None
    assert body["intervals_pending"]["confirm_required"] is True


def test_planned_sessions_api_lists_horizon(client):
    c, _athletes, _db = client
    setup = _confirm_setup(c, username="hz-list")
    aid = setup["athlete"]["id"]
    r = c.get("/v1/athlete/me/planned-sessions", headers={"X-Athlete-Id": aid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == body["count"]
    assert body["count"] > 8
    assert body["sessions"][0]["session_date"]
    assert body["plan_horizon_weeks"] > ICU_SYNC_WEEKS


def test_sync_bundle_prefers_stored_planned_sessions(client):
    c, _athletes, db = client
    setup = _confirm_setup(c, username="stored-sync")
    aid = setup["athlete"]["id"]
    with db_session(db) as conn:
        from db import list_plan_blocks, list_planned_sessions, upsert_athlete_secrets

        blocks = list_plan_blocks(conn, aid)
        stored = list_planned_sessions(conn, aid)
        athlete = get_athlete(conn, aid)
        upsert_athlete_secrets(
            conn, aid, intervals_api_key="test-key", intervals_athlete_id="i999"
        )
    assert stored
    # Mutate a stored name so regenerated library would not match
    stored[0]["name"] = "LAGRET-TEST-ØKT"
    with db_session(db) as conn:
        from db import replace_planned_sessions

        replace_planned_sessions(conn, aid, stored)
        stored2 = list_planned_sessions(conn, aid)

    bundle = build_plan_sync_bundle(
        blocks,
        athlete=athlete,
        weeks=ICU_SYNC_WEEKS,
        include_notes=False,
        planned_sessions=stored2,
        allow_degraded=True,
    )
    assert bundle.get("from_stored_sessions") is True
    assert bundle["kind"] == "calendar_notes_and_stored_workouts"
    names = [e.get("name") for e in (bundle.get("workout_events") or [])]
    assert "LAGRET-TEST-ØKT" in names
    assert bundle["weeks"] == ICU_SYNC_WEEKS


def test_week_adjust_preview_confirm_keeps_rest_of_horizon(client):
    c, _athletes, db = client
    setup = _confirm_setup(c, username="week-adj")
    aid = setup["athlete"]["id"]
    with db_session(db) as conn:
        before = count_planned_sessions(conn, aid)
        before_sessions = list_planned_sessions(conn, aid)
    assert before > 8

    prev = c.post(
        "/v1/athlete/me/plan/week-adjust/preview",
        headers={"X-Athlete-Id": aid},
        json={"week_start": "this_week", "ease_load": True},
    )
    assert prev.status_code == 200, prev.text
    body = prev.json()
    assert body["scope"] == "week"
    assert body["ease_load"] is True
    assert body["confirm_required"] is True
    assert body["count"] >= 1
    assert body["unchanged_sessions_count"] < before

    conf = c.post(
        "/v1/athlete/me/plan/week-adjust/confirm",
        headers={"X-Athlete-Id": aid},
        json={
            "week_start": body["week_start"],
            "week_end": body["week_end"],
            "sessions": body["sessions"],
            "ease_load": True,
            "prepare_intervals_sync": False,
        },
    )
    assert conf.status_code == 200, conf.text
    done = conf.json()
    assert done["written_to_intervals"] is False
    assert done["scope"] == "week"
    assert done["replaced_count"] == body["count"]

    with db_session(db) as conn:
        after = count_planned_sessions(conn, aid)
        after_sessions = list_planned_sessions(conn, aid)
    # Horizon roughly preserved (not wiped to ICU-only window)
    assert after >= before // 2
    assert after > ICU_SYNC_WEEKS * 2
    # Sessions outside the adjusted week still present
    week_start = body["week_start"]
    week_end = body["week_end"]
    outside_before = [
        s["session_date"]
        for s in before_sessions
        if not (week_start <= s["session_date"] <= week_end)
    ]
    outside_after = [
        s["session_date"]
        for s in after_sessions
        if not (week_start <= s["session_date"] <= week_end)
    ]
    assert set(outside_before) == set(outside_after)


def test_extract_plan_update_week_scope():
    reply = (
        "Lett uke denne uka.\n"
        "```plan_update\n"
        '{"reason":"dårlig søvn","rebuild":true,"ease_load":true,'
        '"scope":"week","week_start":"this_week"}\n'
        "```"
    )
    display, prop = extract_plan_update(reply)
    assert "plan_update" not in display
    assert prop["scope"] == "week"
    assert prop["ease_load"] is True
    assert prop["week_start"] == "this_week"


def test_chat_week_plan_update_builds_week_proposal(client):
    c, _athletes, _db = client
    setup = _confirm_setup(c, username="chat-week")
    aid = setup["athlete"]["id"]
    llm_reply = (
        "Vi letter bare denne uka.\n"
        "```plan_update\n"
        '{"reason":"readiness lav","rebuild":true,"ease_load":true,'
        '"scope":"week","week_start":"this_week"}\n'
        "```"
    )
    with (
        patch(
            "main.list_sessions",
            return_value={
                "source": "none",
                "recent": [],
                "upcoming": [],
                "today": [],
                "window": None,
            },
        ),
        patch("main.call_llm", return_value=llm_reply),
        patch(
            "main.resolve_wellness_bundle",
            return_value={
                "recovery_signals": {
                    "available": True,
                    "sleep_avg_hours": 5.5,
                    "readiness": 3,
                    "as_signals_only": True,
                },
                "sleep": {"available": True, "avg_hours": 5.5},
                "load_wellness": {"available": True, "readiness": 3},
            },
        ),
    ):
        r = c.post(
            "/v1/chat",
            headers={"X-Athlete-Id": aid},
            json={"message": "Kan du lette denne uka?"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    prop = data.get("plan_proposal") or {}
    assert prop.get("scope") == "week"
    assert prop.get("sessions")
    assert prop.get("week_start")
    assert prop.get("confirm_required") is True
    assert not prop.get("plan_blocks")
