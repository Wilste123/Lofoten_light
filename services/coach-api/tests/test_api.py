"""API smoke: onboarding → profile path → chat stub."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import config
import main as main_mod
from db import init_db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    athletes = tmp_path / "athletes"
    athletes.mkdir()
    monkeypatch.setattr(config, "DATABASE_PATH", db)
    monkeypatch.setattr(config, "ATHLETES_DATA_DIR", athletes)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    init_db(db)
    # Re-bind startup already ran — ensure tables
    with TestClient(main_mod.app) as c:
        yield c, athletes


def test_onboarding_writes_profile(client):
    c, athletes = client
    r = c.post(
        "/v1/onboarding",
        json={
            "display_name": "Testa",
            "coach_display_name": "Rocky",
            "coach_personality": "direkte",
            "accent_color": "#1a6b4a",
            "goal_text": "Base",
            "injury_notes": "Ingen",
            "ftp_tested": 200,
            "nutrition_ibs": "yes",
            "nutrition_gluten": "sensitive",
            "nutrition_lactose": True,
            "nutrition_notes": "Unngår gels med gluten før langøkt",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    aid = data["athlete"]["id"]
    assert data["athlete"]["nutrition_ibs"] == "yes"
    assert data["athlete"]["nutrition_gluten"] == "sensitive"
    assert data["athlete"]["nutrition_lactose"] is True
    profile_text = (athletes / aid / "profile.md").read_text(encoding="utf-8")
    assert (athletes / aid / "profile.md").is_file()
    assert "Testa" in profile_text
    assert "IBS" in profile_text
    assert "Sensitivitet" in profile_text or "sensitive" in profile_text.lower()
    assert "Unngår gels" in profile_text

    boot = c.post("/v1/session/bootstrap", json={"athlete_id": aid})
    assert boot.json()["needs_onboarding"] is False

    chat = c.post(
        "/v1/chat",
        headers={"X-Athlete-Id": aid},
        json={"message": "Hva bør jeg fokusere på denne uka?"},
    )
    assert chat.status_code == 200
    assert "reply" in chat.json()
    assert len(chat.json()["reply"]) > 10

    patch = c.patch(
        "/v1/athlete/me",
        headers={"X-Athlete-Id": aid},
        json={
            "weekly_focus": "Z2 + svømteknikk",
            "nutrition_gluten": "celiac",
            "notes": "Oppdatert notat",
        },
    )
    assert patch.status_code == 200
    text = (athletes / aid / "profile.md").read_text(encoding="utf-8")
    assert "Z2 + svømteknikk" in text
    assert "Cøliaki" in text
    assert "Oppdatert notat" in text