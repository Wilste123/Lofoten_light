"""Chat AI smoothness — model default, talk-mode (no card spam), OPV prompt."""

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
    HONEST_COACH_VOICE,
    build_system_prompt,
    resolve_openai_model,
    session_thread_memory,
    should_offer_soft_plan_roll,
    user_accepts_agreement_change,
    user_message_is_talk_mode,
)
from db import db_session, init_db, update_athlete


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
    init_db(db)
    with TestClient(main_mod.app) as c:
        yield c, athletes, db


def _onboard(c) -> str:
    r = c.post(
        "/v1/setup/confirm",
        json={
            "display_name": "Test",
            "username": "smooth-test",
            "coach_display_name": "Ole",
            "goal_text": "Komme i form",
            "weekly_hours_target": 5,
            "sessions_per_week": 3,
            "plan_blocks": [
                {
                    "key": "b1",
                    "title": "Base",
                    "theme": "Vane",
                    "phase": "base",
                    "start_date": "2026-10-01",
                    "end_date": "2026-11-01",
                    "weekly_hours": 5,
                    "sort_order": 0,
                }
            ],
            "prepare_intervals_sync": False,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["athlete"]["id"]


def test_default_model_is_gpt4o_not_mini():
    assert resolve_openai_model("") == "gpt-4o"
    assert resolve_openai_model(None) == "gpt-4o"
    assert resolve_openai_model("gpt-4o-mini") == "gpt-4o-mini"
    assert resolve_openai_model("mini") == "gpt-4o-mini"
    assert config.OPENAI_MODEL == "gpt-4o" or "gpt-4o" in resolve_openai_model(
        config.OPENAI_MODEL
    )


def test_honest_voice_is_opv_conversation_first():
    low = HONEST_COACH_VOICE.lower()
    assert "hovedtrener" in low or "opv" in low
    assert "samtale først" in low or "spam" in low
    assert "ikke realistisk" in low
    assert "2019" in HONEST_COACH_VOICE or "410" in HONEST_COACH_VOICE


def test_talk_mode_vs_write_and_agreement():
    assert user_message_is_talk_mode("jeg er sliten i dag, hva synes du?")
    assert user_message_is_talk_mode("forklar hvorfor Z2 er viktig")
    assert not user_message_is_talk_mode("legg inn rolig løp i morgen 40 min")
    assert not user_message_is_talk_mode("juster uka — lett")
    assert user_accepts_agreement_change("Ok, da tar vi 4 økter")
    assert not user_message_is_talk_mode("Ok, da tar vi 4 økter")
    assert not should_offer_soft_plan_roll("jeg er sliten")
    assert should_offer_soft_plan_roll("rull videre neste måned")


def test_session_thread_memory_keeps_agreements():
    hist = [
        {"role": "user", "content": "Ok, da tar vi 4 økter/uke"},
        {
            "role": "assistant",
            "content": "Avtalt: 4 økter/uke. FTP 210 W er dagens grunnlag.",
        },
        {"role": "user", "content": "hvordan var været?"},
    ]
    mem = session_thread_memory(hist)
    assert "4 økter" in mem
    assert "FTP 210" in mem or "Avtalt" in mem


def test_system_prompt_has_write_protocol_and_thread_memory(tmp_path):
    athlete = {
        "display_name": "Ada",
        "coach_display_name": "Ole",
        "coach_personality": "direkte",
        "goal_text": "triatlon",
        "sessions_per_week": 4,
        "athlete_type": "triathlete",
        "agreements": ["4 økter/uke", "svøm først"],
        "injury_notes": "",
        "schedule_notes": "",
        "fitness_notes": "",
        "notes": "",
    }
    athletes = tmp_path / "athletes"
    athletes.mkdir()
    prompt = build_system_prompt(
        athlete,
        KDIR,
        overview_stub={},
        athletes_dir=athletes,
        query_text="hvordan går det",
        history=[
            {"role": "user", "content": "Avtalt: ikke rør kalenderen"},
            {"role": "assistant", "content": "Ok — jeg rører ikke Intervals."},
        ],
    )
    assert "Skrivemodus" in prompt or "workout_proposal" in prompt
    assert "Tråd-minne" in prompt
    assert "ikke rør" in prompt.lower() or "Intervals" in prompt
    assert "Samtale først" in prompt or "spam" in prompt.lower()
    assert HONEST_COACH_VOICE[:40] in prompt


def test_talk_mode_drops_unsolicited_workout_card(client):
    c, _athletes, _db = client
    aid = _onboard(c)
    llm_reply = (
        "Du høres sliten ut — hold Z2 i kveld.\n"
        "```workout_proposal\n"
        '{"workouts":[{"name":"Z2 jog","date":"2026-10-27",'
        '"sport":"run","duration_minutes":40,"description":"lett","start_time":"18:00"}]}\n'
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
            headers={"X-Athlete-Id": aid},
            json={"message": "jeg er sliten i dag, hva synes du?"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("talk_mode") is True
    assert not (data.get("workout_proposal") or {}).get("workouts")
    assert "workout_proposal" not in (data.get("reply") or "")
    assert data.get("llm_model") == "gpt-4o"


def test_write_intent_still_gets_card(client):
    c, _athletes, _db = client
    aid = _onboard(c)
    llm_reply = (
        "Her er en rolig løpetur.\n"
        "```workout_proposal\n"
        '{"workouts":[{"name":"Rolig løp","date":"2026-10-27",'
        '"sport":"run","duration_minutes":40,"description":"Z2","start_time":"07:00"}]}\n'
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
            headers={"X-Athlete-Id": aid},
            json={"message": "legg inn rolig løp i morgen 40 min"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("talk_mode") is not True
    assert data["workout_proposal"]["workouts"][0]["name"]
    assert data.get("confirm_required") is True


def test_agreement_accept_keeps_agreements_card(client):
    c, _athletes, _db = client
    aid = _onboard(c)
    llm_reply = (
        "Avtalt: 4 økter/uke.\n"
        "```agreements_update\n"
        '{"sessions_per_week":4,"agreements":["4 økter/uke"],"reason":"Forhandlet"}\n'
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
            headers={"X-Athlete-Id": aid},
            json={"message": "Ok, da tar vi 4 økter"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["agreements_proposal"]["sessions_per_week"] == 4
    assert data["confirm_required"] is True
