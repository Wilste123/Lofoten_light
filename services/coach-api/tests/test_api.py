"""API smoke: onboarding → profile path → chat stub + Intervals secrets."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import config
import main as main_mod
from db import db_session, get_athlete_secrets, init_db


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
        yield c, athletes


def _onboard(c) -> str:
    r = c.post(
        "/v1/onboarding",
        json={
            "display_name": "Testa",
            "coach_display_name": "Rocky",
            "coach_personality": "direkte",
            "accent_color": "#1a6b4a",
            "goal_text": "Base",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["athlete"]["id"]


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


def test_intervals_secrets_get_put_masked(client, monkeypatch):
    c, _athletes = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}

    empty = c.get("/v1/athlete/me/intervals", headers=headers)
    assert empty.status_code == 200
    assert empty.json()["connected"] is False
    assert empty.json()["api_key_hint"] is None

    monkeypatch.setattr(
        main_mod,
        "smoke_test_intervals",
        lambda key, icu: (True, None),
    )

    secret = "super-secret-intervals-key-xyz9"
    put = c.put(
        "/v1/athlete/me/intervals",
        headers=headers,
        json={
            "intervals_athlete_id": "i999",
            "intervals_api_key": secret,
            "verify": True,
        },
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["connected"] is True
    assert body["intervals_athlete_id"] == "i999"
    assert body["api_key_hint"] == "••••xyz9"
    assert secret not in str(body)
    assert body["verified"] is True

    got = c.get("/v1/athlete/me/intervals", headers=headers)
    assert got.status_code == 200
    g = got.json()
    assert g["connected"] is True
    assert g["api_key_hint"] == "••••xyz9"
    assert "intervals_api_key" not in g
    assert secret not in str(g)

    ov = c.get("/v1/overview", headers=headers)
    assert ov.status_code == 200
    assert ov.json()["intervals_linked"] is True
    assert "i999" in ov.json()["intervals_hint"]

    with db_session(config.DATABASE_PATH) as conn:
        row = get_athlete_secrets(conn, aid)
    assert row["intervals_api_key"] == secret


def test_intervals_requires_auth(client):
    c, _ = client
    assert c.get("/v1/athlete/me/intervals").status_code == 401
    assert (
        c.put(
            "/v1/athlete/me/intervals",
            json={"intervals_athlete_id": "i1", "intervals_api_key": "k"},
        ).status_code
        == 401
    )


def test_intervals_stores_even_when_verify_fails(client, monkeypatch):
    c, _ = client
    aid = _onboard(c)
    monkeypatch.setattr(
        main_mod,
        "smoke_test_intervals",
        lambda key, icu: (False, "Intervals HTTP 401"),
    )
    r = c.put(
        "/v1/athlete/me/intervals",
        headers={"X-Athlete-Id": aid},
        json={
            "intervals_athlete_id": "i1",
            "intervals_api_key": "badkey1234",
            "verify": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["connected"] is True
    assert r.json()["verified"] is False
    assert "401" in (r.json().get("verify_error") or "")
