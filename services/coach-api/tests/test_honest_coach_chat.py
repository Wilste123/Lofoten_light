"""Honest / recommendation-forward coach voice — all chat surfaces.

Unit tests on context builders + system prompt content (no live LLM).
When athlete states an impossible combo, instructions + knowledge must include
realism constraints (feil-og-fixes §9, load, lav-frekvens, nybegynner-svøm).
"""

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
    extract_agreements_update,
)
from db import db_session, init_db, insert_athlete, update_athlete
from knowledge_ctx import (
    detect_athlete_signals,
    knowledge_selection_meta,
    load_knowledge_bundle,
    select_knowledge_paths,
)
from setup_plan import build_setup_chat_system, extract_setup_fields, merge_draft


REPO = Path(__file__).resolve().parents[3]
KDIR = REPO / "knowledge"

# Fixture-style query: ambitious tri goal + poor form + no experience + 2/week
IMPOSSIBLE_BLOB = (
    "triatlon 5:30 i mai, dårlig form, null erfaring, 2 økter/uke"
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    athletes = tmp_path / "athletes"
    athletes.mkdir()
    monkeypatch.setattr(config, "DATABASE_PATH", db)
    monkeypatch.setattr(config, "ATHLETES_DATA_DIR", athletes)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config, "KNOWLEDGE_DIR", KDIR)
    init_db(db)
    with TestClient(main_mod.app) as c:
        yield c, athletes, db


def _onboard(c) -> str:
    r = c.post(
        "/v1/setup/confirm",
        json={
            "display_name": "Test",
            "username": "honest-test",
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


def test_honest_voice_constant_is_recommendation_forward():
    assert "ikke tippy" in HONEST_COACH_VOICE.lower() or "Selvsikker" in HONEST_COACH_VOICE
    assert "ikke realistisk" in HONEST_COACH_VOICE
    assert "alternativer" in HONEST_COACH_VOICE.lower()


def test_knowledge_paths_impossible_tri_include_realism():
    paths = select_knowledge_paths(mode="chat", query_text=IMPOSSIBLE_BLOB)
    assert "coach/maalrealisme.md" in paths
    assert "coach/feil-og-fixes.md" in paths
    assert "load-and-intensity.md" in paths
    assert "svom/nybegynner-til-triatlet.md" in paths
    assert (
        "lop/ukeplaner-lav-frekvens.md" in paths
        or "coach/ukeplaner-generell-utholdenhet.md" in paths
    )
    signals = detect_athlete_signals(IMPOSSIBLE_BLOB)
    assert signals["beginner"] is True
    assert signals["multisport"] is True
    assert signals["time_constrained"] is True


def test_knowledge_bundle_contains_minimum_volume_guidance():
    """Optional fixture: knowledge snippets mention triathlon volume realism."""
    bundle = load_knowledge_bundle(
        KDIR,
        query_text=IMPOSSIBLE_BLOB,
        draft={
            "goal_text": "triatlon",
            "sessions_per_week": 2,
            "background_notes": "null erfaring dårlig form",
            "athlete_type": "triathlete",
        },
        mode="chat",
        total_budget=8000,
    )
    low = bundle.lower()
    assert "maalrealisme" in low or "målrealisme" in low or "urealistisk" in low
    assert "økter" in low or "frekvens" in low or "dose" in low
    # Concrete guidance from knowledge (maalrealisme / lav-frekvens / feil-og-fixes)
    assert "2 økter" in low or "minstefrekvens" in low or "lav frekvens" in low or "dose" in low


def test_setup_chat_system_includes_honest_voice_and_realism_knowledge():
    system, meta = build_setup_chat_system(
        {
            "display_name": "Ada",
            "coach_display_name": "Rocky",
            "goal_text": "triatlon",
            "sessions_per_week": 2,
            "background_notes": "null erfaring, dårlig form",
        },
        knowledge_dir=KDIR,
        history_blob=IMPOSSIBLE_BLOB,
    )
    assert HONEST_COACH_VOICE[:40] in system
    assert "ikke realistisk" in system
    assert "anbefaling" in system.lower() or "anbefalingsorientert" in system
    assert "sessions_per_week" in system
    # Knowledge injection for realism
    assert "maalrealisme" in system.lower() or "urealistisk" in system.lower()
    paths = meta.get("paths") or []
    assert "coach/maalrealisme.md" in paths
    assert meta["signals"]["beginner"] is True


def test_main_chat_system_prompt_same_voice_and_adaptive_knowledge(tmp_path):
    """Bottom Coach-tab `/v1/chat` uses build_system_prompt — same honest voice."""
    athlete = {
        "display_name": "Ada",
        "coach_display_name": "Ole",
        "coach_personality": "direkte",
        "goal_text": "triatlon i mai",
        "sessions_per_week": 2,
        "athlete_type": "triathlete",
        "fitness_notes": "dårlig form",
        "notes": "null erfaring",
        "agreements": [],
        "injury_notes": "",
        "schedule_notes": "2 økter/uke",
    }
    athletes = tmp_path / "athletes"
    athletes.mkdir()
    prompt = build_system_prompt(
        athlete,
        KDIR,
        overview_stub={"sessions": {"upcoming": []}},
        athletes_dir=athletes,
        query_text=IMPOSSIBLE_BLOB,
    )
    assert HONEST_COACH_VOICE[:40] in prompt
    assert "ikke realistisk" in prompt
    assert "agreements_update" in prompt
    assert "2 økter/uke" in prompt or "Avtalt frekvens" in prompt
    assert "maalrealisme" in prompt.lower() or "urealistisk" in prompt.lower()
    assert "focused_session" in prompt  # session-detail path uses same prompt


def test_v1_chat_injects_honest_system_for_coach_tab(client):
    c, _athletes, _db = client
    aid = _onboard(c)
    with db_session(config.DATABASE_PATH) as conn:
        update_athlete(
            conn,
            aid,
            {
                "goal_text": "triatlon 5:30",
                "sessions_per_week": 2,
                "athlete_type": "triathlete",
                "fitness_notes": "dårlig form null erfaring",
            },
        )
    captured = {}

    def _fake_llm(*, api_key, model, system, history, user_message):
        captured["system"] = system
        return "Med to økter og null erfaring er ikke det realistisk. Alternativer: …"

    with (
        patch("main.list_sessions", return_value={
            "source": "none",
            "recent": [],
            "upcoming": [],
            "today": [],
            "window": None,
        }),
        patch("main.call_llm", side_effect=_fake_llm),
    ):
        r = c.post(
            "/v1/chat",
            headers={"X-Athlete-Id": aid},
            json={"message": IMPOSSIBLE_BLOB},
        )
    assert r.status_code == 200, r.text
    system = captured["system"]
    assert HONEST_COACH_VOICE[:40] in system
    assert "ikke realistisk" in system
    assert "maalrealisme" in system.lower() or "urealistisk" in system.lower()


def test_merge_draft_persists_negotiated_agreements():
    draft = {
        "display_name": "Ada",
        "goal_text": "Triatlon",
        "sessions_per_week": 2,
    }
    extracted = {
        "sessions_per_week": 4,
        "goal_race_date": "2027-09-15",
        "agreements": ["4 økter/uke etter forhandling", "Base først"],
        "ready_for_plan": True,
    }
    merged = merge_draft(draft, extracted)
    assert merged["sessions_per_week"] == 4
    assert merged["goal_race_date"] == "2027-09-15"
    agr = " ".join(merged.get("agreements") or [])
    assert "4 økter" in agr
    assert "2027-09-15" in agr or "Måldato" in agr


def test_extract_agreements_update_fence():
    reply = (
        "Vi avtaler fire økter og senere dato.\n"
        "```agreements_update\n"
        '{"sessions_per_week":4,"goal_race_date":"2027-09-15",'
        '"agreements":["4 økter/uke"],"reason":"Forhandlet etter urealistisk mai-mål"}\n'
        "```"
    )
    display, prop = extract_agreements_update(reply)
    assert "agreements_update" not in display
    assert prop is not None
    assert prop["sessions_per_week"] == 4
    assert prop["goal_race_date"] == "2027-09-15"
    assert prop["confirm_required"] is True


def test_extract_setup_agreements_field():
    reply = (
        "Ok — fire økter.\n"
        "```setup_extract\n"
        '{"ready_for_plan": true, "sessions_per_week": 4, '
        '"agreements": ["4 økter/uke", "Race senere"], '
        '"goal_text": "Triatlon", "injury_notes": null, "schedule_notes": null, '
        '"background_notes": null, "coach_respect_notes": null, '
        '"weekly_hours_target": null, "allowed_disciplines": ["run","swim","bike"], '
        '"fitness_notes": null, "season_start_date": null, "goal_race_date": "2027-09-15", '
        '"ftp_tested": null, "nutrition_ibs": null, "nutrition_gluten": null, '
        '"nutrition_lactose": null, "nutrition_notes": null, "notes": null, '
        '"athlete_type": "beginner_multi", "sport": null}\n'
        "```"
    )
    display, data = extract_setup_fields(reply)
    assert "setup_extract" not in display
    assert data["sessions_per_week"] == 4
    assert data["agreements"] == ["4 økter/uke", "Race senere"]
    assert data["goal_race_date"] == "2027-09-15"


def test_v1_chat_returns_agreements_proposal(client):
    c, _athletes, _db = client
    aid = _onboard(c)
    llm_reply = (
        "Avtalt: 4 økter/uke.\n"
        "```agreements_update\n"
        '{"sessions_per_week":4,"agreements":["4 økter/uke"],"reason":"Forhandlet"}\n'
        "```"
    )
    with (
        patch("main.list_sessions", return_value={
            "source": "none",
            "recent": [],
            "upcoming": [],
            "today": [],
            "window": None,
        }),
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
    assert "agreements_update" not in data["reply"]
