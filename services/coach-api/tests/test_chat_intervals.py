"""Chat Intervals snapshot + workout proposal preview→confirm."""

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
from chat_service import (
    extract_workout_proposal,
    infer_plan_update_fallback,
    infer_workout_proposal_fallback,
)
from db import (
    count_planned_sessions,
    db_session,
    init_db,
    list_planned_sessions,
    upsert_athlete_secrets,
)
from intervals_calendar import build_workout_events
from sessions_service import sessions_snapshot_for_chat


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
            "username": "testa",
            "coach_display_name": "Rocky",
            "goal_text": "Base",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["athlete"]["id"]


def test_extract_workout_proposal_strips_fence():
    raw = (
        "Legg inn en rolig Z2-tur tirsdag.\n\n"
        "```workout_proposal\n"
        '{"workouts":[{"name":"Z2 75min","date":"2026-09-30","sport":"bike",'
        '"duration_minutes":75,"description":"Jeven Z2","start_time":"07:00"}]}\n'
        "```"
    )
    display, proposal = extract_workout_proposal(raw)
    assert "workout_proposal" not in display
    assert "Z2-tur" in display
    assert proposal is not None
    assert len(proposal["workouts"]) == 1
    assert proposal["workouts"][0]["name"] == "Z2 75min"
    assert proposal["workouts"][0]["sport"] == "bike"


def test_extract_workout_proposal_none_without_fence():
    display, proposal = extract_workout_proposal("Bare råd uten sync.")
    assert display == "Bare råd uten sync."
    assert proposal is None


def test_infer_workout_proposal_when_llm_skips_fence():
    from datetime import date

    msg = "Kan du legge inn en rolig løpetur i morgen 40 min?"
    reply = (
        "Her er forslaget:\n\n"
        "**Økt:** Løp rolig\n"
        "**Varighet:** 40 minutter\n"
        "**Dato:** 2026-10-05\n"
        "**Beskrivelse:** Rolig Z2.\n"
    )
    prop = infer_workout_proposal_fallback(msg, reply, today=date(2026, 9, 29))
    assert prop is not None
    assert prop["inferred"] is True
    w = prop["workouts"][0]
    assert w["name"] == "Løp rolig"
    assert w["date"] == "2026-10-05"
    assert w["sport"] == "run"
    assert w["duration_minutes"] == 40


def test_infer_plan_update_week_ease():
    prop = infer_plan_update_fallback("Kan du lette denne uka litt?")
    assert prop is not None
    assert prop["rebuild"] is True
    assert prop["scope"] == "week"
    assert prop["ease_load"] is True


def test_chat_infers_workout_proposal_without_fence(client):
    c, _athletes, _db = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}
    llm_reply = (
        "Ok.\n\n"
        "**Økt:** Easy 40\n"
        "**Varighet:** 40 minutter\n"
        "**Dato:** 2026-09-30\n"
        "**Beskrivelse:** Z2 løp.\n"
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
    ):
        r = c.post(
            "/v1/chat",
            headers=headers,
            json={"message": "Legg inn easy run tirsdag på Intervals"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["workout_proposal"]["workouts"][0]["name"] == "Easy 40"
    assert data["confirm_required"] is True
    assert data.get("proposal_inferred") is True


def test_sessions_snapshot_for_chat_compact():
    snap = sessions_snapshot_for_chat(
        {
            "source": "intervals",
            "window": {"start": "2026-09-13", "end": "2026-10-11"},
            "today": [
                {
                    "name": "I dag",
                    "date": "2026-09-27",
                    "kind": "event",
                    "bucket": "today",
                    "discipline_label": "Sykkel",
                    "duration_hours": None,
                    "completion": None,
                }
            ],
            "upcoming": [
                {
                    "name": "Langtur",
                    "date": "2026-09-28",
                    "kind": "event",
                    "bucket": "upcoming",
                    "discipline_label": "Sykkel",
                    "description": "x" * 500,
                    "completion": None,
                }
            ],
            "recent": [
                {
                    "name": "Svøm",
                    "date": "2026-09-26",
                    "kind": "activity",
                    "bucket": "recent",
                    "discipline_label": "Svømming",
                    "duration_hours": 0.8,
                    "completion": {"status": "completed"},
                }
            ],
        }
    )
    assert snap["source"] == "intervals"
    assert snap["upcoming"][0]["name"] == "Langtur"
    assert "description" not in snap["upcoming"][0]
    assert snap["recent"][0]["completion_status"] == "completed"


def test_build_workout_events():
    events = build_workout_events(
        [
            {
                "name": "Z2",
                "date": "2026-09-30",
                "sport": "bike",
                "duration_minutes": 60,
                "description": "Rolig",
                "start_time": "08:00",
            }
        ]
    )
    assert len(events) == 1
    assert events[0]["category"] == "WORKOUT"
    assert events[0]["type"] == "Ride"
    assert events[0]["moving_time"] == 3600
    assert events[0]["external_id"].startswith("ll-coach-w-")
    assert events[0]["start_date_local"].startswith("2026-09-30T08:00")


def test_chat_includes_sessions_snapshot(client):
    c, _athletes, _db = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}
    fake_bundle = {
        "window": {"start": "2026-09-13", "end": "2026-10-11"},
        "source": "intervals",
        "fetch_error": False,
        "recent": [
            {
                "id": "act:1",
                "external_id": "1",
                "kind": "activity",
                "bucket": "recent",
                "name": "Ride",
                "date": "2026-09-26",
                "discipline_label": "Sykkel",
                "duration_hours": 1.2,
                "completion": None,
            }
        ],
        "upcoming": [
            {
                "id": "evt:2",
                "external_id": "2",
                "kind": "event",
                "bucket": "upcoming",
                "name": "Svømteknikk",
                "date": "2026-09-29",
                "discipline_label": "Svømming",
                "completion": None,
            }
        ],
        "today": [],
    }
    captured = {}

    def _fake_llm(*, api_key, model, system, history, user_message):
        captured["system"] = system
        return "Du har Svømteknikk på mandag ifølge Intervals-snapshotet."

    with (
        patch("main.list_sessions", return_value=fake_bundle),
        patch("main.call_llm", side_effect=_fake_llm),
    ):
        r = c.post(
            "/v1/chat",
            headers=headers,
            json={"message": "Hva har jeg denne uka?"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["sessions_in_context"] is True
    assert data["sessions_source"] == "intervals"
    assert "Svømteknikk" in captured["system"]
    assert '"sessions"' in captured["system"] or "sessions" in captured["system"]


def test_chat_returns_workout_proposal(client):
    c, _athletes, _db = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}
    # Commercial default = run+strength — propose run (not bike/swim)
    llm_reply = (
        "Ok — rolig løpetur tirsdag.\n"
        "```workout_proposal\n"
        '{"workouts":[{"name":"Easy 40","date":"2026-09-30","sport":"run",'
        '"duration_minutes":40,"description":"Z2","start_time":"07:00"}]}\n'
        "```"
    )
    with (
        patch("main.list_sessions", return_value={"source": "none", "recent": [], "upcoming": [], "today": [], "window": None}),
        patch("main.call_llm", return_value=llm_reply),
    ):
        r = c.post(
            "/v1/chat",
            headers=headers,
            json={"message": "Legg inn easy run tirsdag på Intervals"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "workout_proposal" not in data["reply"]
    assert data["workout_proposal"]["workouts"][0]["name"] == "Easy 40"
    assert data["confirm_required"] is True


def test_chat_blocks_disallowed_sport_proposal(client):
    """Commercial run+strength athlete: swim proposal must not reach confirm."""
    c, _athletes, _db = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}
    llm_reply = (
        "Svøm?\n"
        "```workout_proposal\n"
        '{"workouts":[{"name":"Teknikk","date":"2026-09-30","sport":"swim",'
        '"duration_minutes":45,"description":"Drill","start_time":"07:00"}]}\n'
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
    ):
        r = c.post(
            "/v1/chat",
            headers=headers,
            json={"message": "Legg inn svøm tirsdag"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "workout_proposal" not in data
    assert data.get("workout_proposal_blocked") is True
    assert data.get("constraint_reasons")


def test_workout_preview_confirm_flow(client):
    c, _athletes, db = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}
    with db_session(db) as conn:
        upsert_athlete_secrets(
            conn,
            aid,
            intervals_api_key="test-key",
            intervals_athlete_id="i999",
        )

    preview = c.post(
        "/v1/athlete/me/intervals/workouts/preview",
        headers=headers,
        json={
            "workouts": [
                {
                    "name": "Easy run",
                    "date": "2026-09-30",
                    "sport": "run",
                    "duration_minutes": 40,
                    "description": "Rolig",
                    "start_time": "07:00",
                }
            ]
        },
    )
    assert preview.status_code == 200, preview.text
    pdata = preview.json()
    assert pdata["confirm_required"] is True
    assert pdata["op"] == "workout_push"
    assert pdata["count"] == 1
    pending_id = pdata["pending_id"]

    with patch("main.post_events_bulk", return_value={"count": 1}) as mock_post:
        conf = c.post(
            "/v1/athlete/me/intervals/calendar/confirm",
            headers=headers,
            json={"pending_id": pending_id},
        )
    assert conf.status_code == 200, conf.text
    assert conf.json()["pushed"] == 1
    assert conf.json()["op"] == "workout_push"
    assert conf.json().get("planned_sessions_saved") == 1
    mock_post.assert_called_once()
    args = mock_post.call_args
    assert args[0][0] == "test-key"
    assert args[0][1] == "i999"
    events = args[0][2]
    assert events[0]["category"] == "WORKOUT"
    assert events[0]["external_id"].startswith("ll-coach-w-")
    with db_session(db) as conn:
        n = count_planned_sessions(conn, aid)
        rows = list_planned_sessions(conn, aid)
    assert n == 1
    assert rows[0]["name"] == "Easy run"
    assert rows[0]["source"] == "chat"


def test_workout_preview_confirm_local_without_intervals(client):
    """Chat workouts must land in planned_sessions even without Intervals."""
    c, _athletes, db = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}
    preview = c.post(
        "/v1/athlete/me/intervals/workouts/preview",
        headers=headers,
        json={
            "workouts": [
                {
                    "name": "Local run",
                    "date": "2026-10-01",
                    "sport": "run",
                    "duration_minutes": 35,
                    "description": "Rolig",
                    "start_time": "08:00",
                }
            ],
            "prepare_intervals_sync": True,
        },
    )
    assert preview.status_code == 200, preview.text
    pdata = preview.json()
    assert pdata["persist_planned_sessions"] is True
    assert pdata["intervals_event_count"] == 0
    assert pdata["planned_sessions_count"] == 1
    pending_id = pdata["pending_id"]
    conf = c.post(
        "/v1/athlete/me/intervals/calendar/confirm",
        headers=headers,
        json={"pending_id": pending_id},
    )
    assert conf.status_code == 200, conf.text
    body = conf.json()
    assert body["planned_sessions_saved"] == 1
    assert body["pushed"] == 0
    with db_session(db) as conn:
        rows = list_planned_sessions(conn, aid)
    assert len(rows) == 1
    assert rows[0]["name"] == "Local run"


def test_workout_preview_refuses_disallowed_sport(client):
    c, _athletes, db = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}
    with db_session(db) as conn:
        upsert_athlete_secrets(
            conn,
            aid,
            intervals_api_key="test-key",
            intervals_athlete_id="i999",
        )
    preview = c.post(
        "/v1/athlete/me/intervals/workouts/preview",
        headers=headers,
        json={
            "workouts": [
                {
                    "name": "Z2",
                    "date": "2026-09-30",
                    "sport": "bike",
                    "duration_minutes": 60,
                }
            ]
        },
    )
    assert preview.status_code == 400
    assert "Avtale" in preview.text or "blokker" in preview.text.lower()
