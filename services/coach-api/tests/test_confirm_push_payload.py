"""Confirm messaging + ICU payload via CLI builder (not thin 10min/JSON stub)."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import config
import main as main_mod
from chat_service import (
    confirm_write_success_reply_nb,
    extract_workout_proposal,
    infer_workout_proposal_fallback,
    strip_workout_json_from_prose,
    user_requests_confirm_and_push,
)
from intervals_calendar import build_workout_events
from plan_workouts import chat_workout_icu_description, icu_events_from_chat_workouts


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    athletes = tmp_path / "athletes"
    athletes.mkdir()
    monkeypatch.setattr(config, "DATABASE_PATH", db)
    monkeypatch.setattr(config, "ATHLETES_DATA_DIR", athletes)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    from db import init_db

    init_db(db)
    with TestClient(main_mod.app) as c:
        yield c, athletes, db


def _confirm_setup(c, *, username="push-fix", sessions=5):
    preview = c.post(
        "/v1/setup/plan/preview",
        json={
            "display_name": "William",
            "username": username,
            "goal_text": "Lofoten Half Extreme 2027",
            "background_notes": f"Form OK, {sessions} økter i uka, løp",
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
            "display_name": "William",
            "username": username,
            "goal_text": "Lofoten Half Extreme 2027",
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


def test_strip_json_fence_from_prose():
    raw = (
        "Her er 6x2 i morgen.\n\n"
        "```workout_proposal\n"
        '{"workouts":[{"name":"Intervaller 6x2","date":"2026-10-02",'
        '"sport":"run","duration_minutes":60,"description":"6x2"}]}\n'
        "```\n"
        "Bekreft."
    )
    display, prop = extract_workout_proposal(raw)
    assert prop and prop["workouts"][0]["duration_minutes"] == 60
    assert "```" not in display
    assert '"workouts"' not in display
    assert "bekreft" in display.lower()
    assert '"workouts"' not in strip_workout_json_from_prose(raw)


def test_infer_prefers_total_not_warmup_10min():
    tomorrow = (date(2026, 10, 1) + timedelta(days=1)).isoformat()
    prose = (
        f"Struktur {tomorrow}:\n"
        "- Oppvarming 10 min\n"
        "- Hoveddel 6x2 min\n"
        "- Nedkjøling 10 min\n"
        "Totalt 60 min. Bekreft."
    )
    prop = infer_workout_proposal_fallback(
        "lag økt i morgen løping 6x2",
        prose,
        today=date(2026, 10, 1),
    )
    assert prop and prop["workouts"]
    w = prop["workouts"][0]
    assert w["duration_minutes"] == 60
    assert "10min" not in (w["name"] or "").lower().replace(" ", "")
    assert "10 min" not in (w["name"] or "").lower() or "60" in (w["name"] or "")
    assert '"workouts"' not in (w.get("description") or "")
    # Must not dump the user message as description
    assert "lag økt i morgen" not in (w.get("description") or "")


def test_confirm_and_push_phrase():
    assert user_requests_confirm_and_push("bekreft og push til intervals")
    assert user_requests_confirm_and_push("Bekreft og sync")
    assert not user_requests_confirm_and_push("bekreft")
    assert not user_requests_confirm_and_push("ok")


def test_success_reply_matches_toast_shape():
    msg = confirm_write_success_reply_nb(
        saved=1, pushed=1, names=["Intervaller 6x2"]
    )
    assert "1 økt" in msg.lower() or "1 økt(er)" in msg
    assert "intervals" in msg.lower()
    assert "ikke oppdatert" not in msg.lower()


def test_icu_description_has_intervals_not_json():
    w = {
        "name": "Intervaller 6x2",
        "date": "2026-10-02",
        "sport": "run",
        "duration_minutes": 60,
        "description": 'Chat prose {"workouts":[{"duration_minutes":60}]}',
        "steps": [
            {"type": "warmup", "duration_minutes": 10, "intensity": "Z2"},
            {"type": "work", "duration_minutes": 2, "intensity": "Z4"},
            {"type": "recover", "duration_minutes": 2, "intensity": "Z1"},
            {"type": "work", "duration_minutes": 2, "intensity": "Z4"},
            {"type": "recover", "duration_minutes": 2, "intensity": "Z1"},
            {"type": "cooldown", "duration_minutes": 10},
        ],
    }
    desc = chat_workout_icu_description(w)
    assert "---intervals---" in desc
    assert '"workouts"' not in desc
    assert "Main Set" in desc or "2m" in desc


def test_build_workout_events_uses_cli_pipeline_duration_and_structure():
    """Web path must reuse build_workout_event — moving_time 60m, no JSON dump."""
    workouts = [
        {
            "name": "Intervaller 6x2",
            "date": (date.today() + timedelta(days=1)).isoformat(),
            "sport": "run",
            "duration_minutes": 60,
            "description": "6x2 intervaller",
            "start_time": "07:00",
            "steps": [
                {"type": "warmup", "duration_minutes": 10, "intensity": "75-85%"},
                {"type": "work", "duration_minutes": 2, "intensity": "90-95%"},
                {"type": "recover", "duration_minutes": 2, "intensity": "70-75%"},
                {"type": "work", "duration_minutes": 2, "intensity": "90-95%"},
                {"type": "recover", "duration_minutes": 2, "intensity": "70-75%"},
                {"type": "work", "duration_minutes": 2, "intensity": "90-95%"},
                {"type": "recover", "duration_minutes": 2, "intensity": "70-75%"},
                {"type": "work", "duration_minutes": 2, "intensity": "90-95%"},
                {"type": "recover", "duration_minutes": 2, "intensity": "70-75%"},
                {"type": "work", "duration_minutes": 2, "intensity": "90-95%"},
                {"type": "recover", "duration_minutes": 2, "intensity": "70-75%"},
                {"type": "work", "duration_minutes": 2, "intensity": "90-95%"},
                {"type": "recover", "duration_minutes": 2, "intensity": "70-75%"},
                {"type": "cooldown", "duration_minutes": 10, "intensity": "75-85%"},
            ],
        }
    ]
    events = build_workout_events(workouts)
    assert len(events) == 1
    ev = events[0]
    assert ev["category"] == "WORKOUT"
    assert ev["type"] == "Run"
    assert ev["name"] == "Intervaller 6x2"
    assert ev.get("moving_time") == 3600
    desc = ev.get("description") or ""
    assert '"workouts"' not in desc
    assert "```" not in desc
    # Structured steps — not a flat 10min stub
    assert "Main Set" in desc or "2m" in desc or "Warmup" in desc
    assert ev.get("_duration_minutes") == 60 or ev.get("moving_time") == 3600


def test_icu_events_from_chat_matches_planned_path_pipeline():
    """Library path still resolves via same builder as Cursor agent."""
    day = (date.today() + timedelta(days=1)).isoformat()
    events = icu_events_from_chat_workouts(
        [
            {
                "name": "Løp easy 40",
                "date": day,
                "sport": "run",
                "duration_minutes": 40,
                "planned_path": "workouts/planned/run/R01-easy-40.txt",
                "description": "workouts/planned/run/R01-easy-40.txt",
                "start_time": "07:00",
            }
        ]
    )
    assert len(events) == 1
    ev = events[0]
    assert ev["moving_time"] == 40 * 60
    assert ev["type"] == "Run"
    assert "LTHR" in (ev.get("description") or "") or "Warmup" in (
        ev.get("description") or ""
    )


def test_chat_confirm_push_one_shot_saves_same_session(client):
    c, _a, _db = client
    setup = _confirm_setup(c, username="oneshot-push")
    aid = setup["athlete"]["id"]
    headers = {"X-Athlete-Id": aid}
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    fence = (
        f"6x2 i morgen.\n\n```workout_proposal\n"
        f'{{"workouts":[{{"name":"Intervaller 6x2","date":"{tomorrow}",'
        f'"sport":"run","duration_minutes":60,'
        f'"description":"Oppvarming 10 + 6x2 + nedkjøling",'
        f'"steps":['
        f'{{"type":"warmup","duration_minutes":10}},'
        f'{{"type":"work","duration_minutes":2}},'
        f'{{"type":"recover","duration_minutes":2}},'
        f'{{"type":"work","duration_minutes":2}},'
        f'{{"type":"recover","duration_minutes":2}},'
        f'{{"type":"work","duration_minutes":2}},'
        f'{{"type":"recover","duration_minutes":2}},'
        f'{{"type":"work","duration_minutes":2}},'
        f'{{"type":"recover","duration_minutes":2}},'
        f'{{"type":"work","duration_minutes":2}},'
        f'{{"type":"recover","duration_minutes":2}},'
        f'{{"type":"work","duration_minutes":2}},'
        f'{{"type":"recover","duration_minutes":2}},'
        f'{{"type":"cooldown","duration_minutes":10}}'
        f']}}]}}\n```\nBekreft.'
    )
    with (
        patch("main.call_llm", return_value=fence),
        patch(
            "main.resolve_wellness_bundle",
            return_value={"recovery_signals": {"available": False}},
        ),
    ):
        r1 = c.post(
            "/v1/chat",
            headers=headers,
            json={"message": "lag 6x2 løpeøkt i morgen"},
        )
    assert r1.status_code == 200, r1.text
    b1 = r1.json()
    assert (b1.get("workout_proposal") or {}).get("workouts")
    assert '"workouts"' not in (b1.get("reply") or "")
    w0 = b1["workout_proposal"]["workouts"][0]
    assert w0["duration_minutes"] == 60
    assert w0["name"] != "Løping 10min"

    # One-shot without Intervals secrets → local save, success wording
    r2 = c.post(
        "/v1/chat",
        headers=headers,
        json={"message": "bekreft og push til intervals"},
    )
    assert r2.status_code == 200, r2.text
    b2 = r2.json()
    assert b2.get("confirm_push_done") or b2.get("write_success") or b2.get(
        "planned_sessions_saved"
    )
    low = (b2.get("reply") or "").lower()
    assert "lagret" in low or "bekreftet" in low
    assert "ikke oppdatert" not in low
    assert "har ikke oppdatert" not in low


def test_preview_payload_fields_not_10min_stub(client):
    c, _a, db = client
    setup = _confirm_setup(c, username="preview-payload")
    aid = setup["athlete"]["id"]
    headers = {"X-Athlete-Id": aid}
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    prev = c.post(
        "/v1/athlete/me/intervals/workouts/preview",
        headers=headers,
        json={
            "workouts": [
                {
                    "name": "Intervaller 6x2",
                    "date": tomorrow,
                    "sport": "run",
                    "duration_minutes": 60,
                    "description": "6x2",
                    "start_time": "07:00",
                    "steps": [
                        {"type": "warmup", "duration_minutes": 10},
                        {"type": "work", "duration_minutes": 2},
                        {"type": "recover", "duration_minutes": 2},
                        {"type": "work", "duration_minutes": 2},
                        {"type": "recover", "duration_minutes": 2},
                        {"type": "cooldown", "duration_minutes": 10},
                    ],
                }
            ],
            "prepare_intervals_sync": False,
        },
    )
    assert prev.status_code == 200, prev.text
    body = prev.json()
    sess = (body.get("sessions") or [None])[0]
    assert sess
    assert sess["name"] == "Intervaller 6x2"
    assert sess["duration_minutes"] == 60
    # Pending payload should carry structured events even when ICU off (built for plan)
    from db import db_session, get_pending_action

    with db_session(db) as conn:
        pending = get_pending_action(conn, aid, body["pending_id"])
    assert pending
    payload = pending.get("payload") or {}
    rows = payload.get("planned_sessions") or []
    assert rows and rows[0]["duration_minutes"] == 60
    assert rows[0]["name"] == "Intervaller 6x2"
    desc = rows[0].get("description") or ""
    assert '"workouts"' not in desc
    assert "10min" not in rows[0]["name"].lower()
