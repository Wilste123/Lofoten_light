"""Knowledge-first context pack inject (Fly / rethink parity)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import config
import main as main_mod
from chat_service import build_system_prompt
from context_pack import KNOWLEDGE_FIRST_HEADER, build_context_pack, pack_for_system_prompt

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
            "username": "pack-test",
            "coach_display_name": "Ole",
            "goal_text": "Half Extreme Lofoten 2027",
            "weekly_hours_target": 12,
            "sessions_per_week": 5,
            "injury_notes": "Rygg — unngå hardt sittende sykkel hvis flamme",
            "agreements": ["svøm først"],
            "plan_blocks": [],
            "prepare_intervals_sync": False,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["athlete"]["id"]


def test_build_context_pack_has_sources_rules_no_web():
    athlete = {
        "display_name": "William",
        "goal_text": "Lofoten 2027",
        "injury_notes": "Rygg",
        "agreements": ["svøm først"],
        "sessions_per_week": 5,
        "athlete_type": "triathlete",
    }
    pack = build_context_pack(
        KDIR,
        athlete=athlete,
        overview_stub={"ctl": 42},
        include_overview_json=True,
    )
    md = pack["markdown"]
    assert "SOURCES / RULES" in md
    assert "Forbidden" in md or "web search" in md.lower()
    assert "mangler" in md.lower()
    assert "William" in md
    assert "coach/coach-filosofi.md" in "\n".join(pack["paths_used"]) or "filosofi" in md
    assert pack["chars"] > 500


def test_system_prompt_injects_pack():
    athlete = {
        "display_name": "William",
        "coach_display_name": "Ole",
        "coach_personality": "opv",
        "goal_text": "Lofoten 2027",
        "sessions_per_week": 5,
        "athlete_type": "triathlete",
        "agreements": ["svøm først"],
        "injury_notes": "Rygg",
        "fitness_notes": "Z2-uke",
        "schedule_notes": "Jobb",
        "allowed_disciplines": ["run", "bike", "swim"],
        "notes": "",
    }
    prompt = build_system_prompt(
        athlete,
        KDIR,
        overview_stub={"wellness_signals": {"ctl": 40}},
        athletes_dir=Path("/tmp"),
        query_text="hva i morgen?",
    )
    assert "Context pack (knowledge-first)" in prompt
    assert "SOURCES / RULES" in prompt
    assert "web search" in prompt.lower() or "Knowledge-first" in prompt
    assert "Ingen web search" in prompt or "ikke" in prompt.lower()
    # Compact pack for prompt skips heavy overview JSON duplicate
    compact = pack_for_system_prompt(KDIR, athlete=athlete)
    assert KNOWLEDGE_FIRST_HEADER.splitlines()[0] in compact


def test_get_context_pack_endpoint(client):
    c, _athletes, _db = client
    aid = _onboard(c)
    r = c.get("/v1/context/pack", headers={"X-Athlete-Id": aid})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "markdown" in data
    assert data["meta"]["knowledge_first"] is True
    assert data["meta"]["web_search"] is False
    assert "SOURCES / RULES" in data["markdown"]
    assert "Half Extreme" in data["markdown"] or "William" in data["markdown"]
