"""Coach chat depth — athlete-specific prescriptions, not ChatGPT fluff.

Acceptance failure (William live): «super-økt» → thin VO2/strength essay,
dato+varighet nudge, then generic template after «løping»; challenge
«er 4x3 på 90% en superøkt?» only lightly edited the fluff.
"""

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
    HONEST_COACH_VOICE,
    _PRESCRIPTION_PROTOCOL_NB,
    apply_workout_defaults,
    build_system_prompt,
    infer_workout_proposal_fallback,
    user_continues_prescription,
    user_message_is_talk_mode,
    user_requests_prescription,
    user_requests_session_change,
    write_intent_kind,
)


REPO = Path(__file__).resolve().parents[3]
KDIR = REPO / "knowledge"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    athletes = tmp_path / "athletes"
    athletes.mkdir()
    monkeypatch.setattr(config, "DATABASE_PATH", db)
    monkeypatch.setattr(config, "ATHLETES_DATA_DIR", athletes)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config, "OPENAI_MODEL", "gpt-4o")
    monkeypatch.setattr(config, "KNOWLEDGE_DIR", KDIR)
    from db import init_db

    init_db(db)
    with TestClient(main_mod.app) as c:
        yield c, athletes, db


def _onboard(c) -> str:
    r = c.post(
        "/v1/setup/confirm",
        json={
            "display_name": "William",
            "username": "depth-test",
            "coach_display_name": "Ole",
            "goal_text": "Half Extreme Lofoten 2027",
            "weekly_hours_target": 12,
            "sessions_per_week": 5,
            "injury_notes": "Rygg — unngå hardt sittende sykkel hvis flamme",
            "agreements": ["svøm først", "ikke rør kalender uten OK"],
            "plan_blocks": [
                {
                    "key": "b1",
                    "title": "Base",
                    "theme": "Kontinuitet",
                    "phase": "base",
                    "start_date": "2026-10-01",
                    "end_date": "2026-12-01",
                    "weekly_hours": 10,
                    "sort_order": 0,
                }
            ],
            "prepare_intervals_sync": False,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["athlete"]["id"]


def test_super_okt_is_prescription_not_talk_mode():
    msg = "Gi meg en forskningsbasert super-økt med real payoff"
    assert user_requests_prescription(msg)
    assert user_requests_session_change(msg)
    assert write_intent_kind(msg) == "session"
    assert not user_message_is_talk_mode(msg)
    # Casual sparring still talk-mode
    assert user_message_is_talk_mode("jeg er sliten, hva synes du?")


def test_loping_followup_continues_prescription():
    hist = [
        {
            "role": "assistant",
            "content": (
                "Jeg trenger en bekreftbar økt (dato + varighet). "
                "Si f.eks. legg inn rolig løp — forhåndsvisningskort."
            ),
        }
    ]
    assert user_continues_prescription("løping", hist)
    assert user_requests_session_change("løping", hist)
    assert not user_message_is_talk_mode("løping", hist)
    assert user_message_is_talk_mode("løping")  # no history → talk


def test_system_prompt_has_prescription_bar_and_athlete_anchors(tmp_path):
    athletes = tmp_path / "athletes"
    athletes.mkdir()
    athlete = {
        "display_name": "William",
        "coach_display_name": "Ole",
        "coach_personality": "opv",
        "goal_text": "Lofoten 2027",
        "sessions_per_week": 5,
        "athlete_type": "triathlete",
        "agreements": ["svøm først", "rygg: forsiktig"],
        "injury_notes": "Rygg — flamme ved sittende hardøkt",
        "fitness_notes": "Ukens fokus: Z2 + én kvalitet",
        "schedule_notes": "Jobb til 16",
        "allowed_disciplines": ["run", "bike", "swim"],
        "notes": "",
    }
    prompt = build_system_prompt(
        athlete,
        KDIR,
        overview_stub={"wellness_signals": {"ctl": 40, "atl": 35}},
        athletes_dir=athletes,
        query_text="gi meg en super-økt",
    )
    assert _PRESCRIPTION_PROTOCOL_NB[:40] in prompt
    assert "95–100" in prompt or "VO₂" in prompt or "VO2" in prompt
    assert "Rygg" in prompt
    assert "svøm først" in prompt
    assert "Ukens fokus" in prompt or "Z2" in prompt
    assert "Ikke «Lykke til»" in HONEST_COACH_VOICE or "ikke tippy" in HONEST_COACH_VOICE.lower()
    assert "stretch" in _PRESCRIPTION_PROTOCOL_NB.lower() or "styrke" in _PRESCRIPTION_PROTOCOL_NB.lower()
    assert "4×3" in prompt or "90 %" in prompt or "superøkt" in prompt.lower()


def test_infer_super_okt_defaults_tomorrow_and_vo2_intensity():
    today = date(2026, 10, 26)
    prop = infer_workout_proposal_fallback(
        "Gi meg en forskningsbasert super-økt",
        "Her er en kvalitetsøkt for aerob kapasitet.",
        today=today,
    )
    assert prop and prop["workouts"]
    w = prop["workouts"][0]
    assert w["date"] == (today + timedelta(days=1)).isoformat()
    assert w["duration_minutes"] >= 50
    assert w["sport"] == "run"
    desc = (w.get("description") or "").lower()
    steps = w.get("steps") or []
    work_ints = " ".join(
        str(s.get("intensity") or "") for s in steps if s.get("type") == "work"
    )
    assert (
        "95" in desc
        or "100" in desc
        or "vo2" in desc
        or "95" in work_ints
        or "vo2" in work_ints.lower()
    )
    # Must not be a soft 90% sold as VO2
    assert "90%" not in work_ints.replace(" ", "")


def test_apply_defaults_fills_missing_date_duration():
    today = date(2026, 10, 26)
    prop = apply_workout_defaults(
        {
            "workouts": [
                {
                    "name": "VO2 5x3",
                    "date": "",
                    "sport": "run",
                    "duration_minutes": None,
                    "description": "5x3 @ 95-100%",
                }
            ]
        },
        user_message="super-økt løping",
        reply="",
        today=today,
    )
    assert prop and prop.get("defaults_applied")
    w = prop["workouts"][0]
    assert w["date"] == "2026-10-27"
    assert w["duration_minutes"] == 60


def test_chat_super_okt_gets_preview_card_not_date_nudge(client):
    c, _athletes, _db = client
    aid = _onboard(c)
    # Thin LLM essay (old failure) — fallback must still open a card
    llm_reply = (
        "Her er en forskningsbasert kvalitetsøkt.\n\n"
        "**Oppvarming:** 10–15 min lett jogg, dynamisk stretching, "
        "hofteåpnere, foam roll.\n"
        "**Hoveddel:** 4×3 min @ 90% innsats.\n"
        "**Styrke:** knebøy, utfall, planke.\n"
        "**Nedkjøling:** stretch og pust.\n\n"
        "Lykke til!"
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
            headers={"X-Athlete-Id": aid},
            json={
                "message": "Gi meg en forskningsbasert super-økt med real payoff"
            },
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("talk_mode") is not True
    workouts = (data.get("workout_proposal") or {}).get("workouts") or []
    assert workouts, data.get("reply")
    assert data.get("confirm_required") is True
    reply = data.get("reply") or ""
    assert "dato + varighet" not in reply.lower()
    w0 = workouts[0]
    assert w0.get("date")
    assert w0.get("duration_minutes")
    # Fallback rebuilt real VO2 intensity — not soft 90% as «super»
    blob = f"{w0.get('description') or ''} {w0.get('name') or ''}".lower()
    step_ints = " ".join(
        str(s.get("intensity") or "")
        for s in (w0.get("steps") or [])
        if isinstance(s, dict)
    ).lower()
    assert "95" in blob or "vo2" in blob or "95" in step_ints or "vo2" in step_ints


def test_chat_loping_followup_opens_card(client):
    c, _athletes, _db = client
    aid = _onboard(c)
    hist_assistant = (
        "Jeg trenger en bekreftbar økt (dato + varighet) for forhåndsvisningskort."
    )
    from db import add_message, db_session

    with db_session(config.get_db()) as conn:
        add_message(conn, aid, "user", "Gi meg en super-økt")
        add_message(conn, aid, "assistant", hist_assistant)

    llm_reply = "Ok — løpe-VO2 i morgen."
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
            headers={"X-Athlete-Id": aid},
            json={"message": "løping"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("talk_mode") is not True
    workouts = (data.get("workout_proposal") or {}).get("workouts") or []
    assert workouts
    assert workouts[0]["sport"] in ("run", "løp", "lop")
