"""Week check («sjekk uka mi») + ukesopp save — Copilot US-1 / pass-3."""

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
    user_requests_ukesopp,
    user_requests_week_check,
    week_check_summary_nb,
)
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
    with TestClient(main_mod.app) as c:
        yield c


def _onboard(c, username: str = "weekcheck") -> str:
    r = c.post(
        "/v1/onboarding",
        json={
            "display_name": "Week Check",
            "username": username,
            "coach_display_name": "Rocky",
            "goal_text": "Base",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["athlete"]["id"]


def test_week_check_intent_vs_ukesopp():
    assert user_requests_week_check("sjekk uka mi")
    assert user_requests_week_check("analyser uken")
    assert user_requests_week_check("hva har jeg gjort denne uka")
    assert not user_requests_week_check("legg inn løp i morgen")
    assert user_requests_ukesopp("Kan vi ta ukesopp?")
    assert not user_requests_ukesopp("sjekk uka mi")
    assert user_requests_ukesopp("hvordan gikk uka?")


def test_week_check_summary_honest_when_unlinked():
    reply = week_check_summary_nb(
        name="William",
        week_start="2026-10-06",
        week_end="2026-10-12",
        planned_lines=["2026-10-07 · Rolig løp"],
        completed_lines=[],
        missed_lines=[],
        wellness_bits=[],
        intervals_linked=False,
        sessions_planned=1,
        sessions_done=0,
        compliance_pct=0.0,
    )
    assert "Intervals er ikke koblet" in reply
    assert "NOTE" in reply
    assert "Ingen endring lagret" in reply


def test_week_check_chat_endpoint(client):
    aid = _onboard(client, "weekcheck1")
    with patch(
        "main.resolve_wellness_bundle",
        return_value={"recovery_signals": {"available": False, "note": "Ingen"}},
    ), patch(
        "tb_score.fetch_tb_for_athlete",
        return_value={
            "available": True,
            "tb_score": 71,
            "band": "gul",
            "recommendation": "Plan B på intervall",
            "plan_b_nb": "Plan B: Z2 i stedet for terskel",
        },
    ):
        chat = client.post(
            "/v1/chat",
            headers={"X-Athlete-Id": aid},
            json={"message": "sjekk uka mi"},
        )
    assert chat.status_code == 200, chat.text
    body = chat.json()
    assert body.get("written_to_intervals") is False
    assert "week_check" in body
    assert "Ukesjekk" in body.get("reply", "")
    wc = body["week_check"]
    assert wc.get("written_to_intervals") is False
    assert "tb" in wc
    assert "load" in wc
    assert "TB-Score" in body.get("reply", "") or wc["tb"].get("tb_score") == 71


def test_ukesopp_save_endpoint(client):
    aid = _onboard(client, "ukesaves1")
    bad = client.post(
        "/v1/ukesopp/save",
        headers={"X-Athlete-Id": aid},
        json={
            "week_start": "2026-10-06",
            "week_end": "2026-10-12",
            "answers": [],
        },
    )
    assert bad.status_code == 422
    ok = client.post(
        "/v1/ukesopp/save",
        headers={"X-Athlete-Id": aid},
        json={
            "week_start": "2026-10-06",
            "week_end": "2026-10-12",
            "answers": ["3/4", "passe", "langtur", "mer søvn"],
        },
    )
    assert ok.status_code == 200, ok.text
    data = ok.json()
    assert data["saved"] is True
    assert data["written_to_intervals"] is False
    assert data["answer_count"] == 4
