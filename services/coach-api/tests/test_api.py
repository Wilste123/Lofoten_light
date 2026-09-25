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


def test_intervals_keeps_key_when_blank_and_verify_endpoint(client, monkeypatch):
    c, _ = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}
    calls = {"n": 0}

    def _ok(key, icu, **_kw):
        calls["n"] += 1
        assert key == "keep-me-secret-key99"
        return True, None

    monkeypatch.setattr(main_mod, "smoke_test_intervals", _ok)

    put1 = c.put(
        "/v1/athlete/me/intervals",
        headers=headers,
        json={
            "intervals_athlete_id": "i42",
            "intervals_api_key": "keep-me-secret-key99",
            "verify": False,
        },
    )
    assert put1.status_code == 200
    assert put1.json()["verified"] is None

    put2 = c.put(
        "/v1/athlete/me/intervals",
        headers=headers,
        json={
            "intervals_athlete_id": "i42",
            "intervals_api_key": "",
            "verify": True,
        },
    )
    assert put2.status_code == 200, put2.text
    assert put2.json()["connected"] is True
    assert put2.json()["verified"] is True
    assert put2.json()["api_key_hint"] == "••••ey99"

    with db_session(config.DATABASE_PATH) as conn:
        row = get_athlete_secrets(conn, aid)
    assert row["intervals_api_key"] == "keep-me-secret-key99"

    v = c.post("/v1/athlete/me/intervals/verify", headers=headers)
    assert v.status_code == 200
    assert v.json()["verified"] is True
    assert calls["n"] >= 2


def test_intervals_verify_requires_stored(client):
    c, _ = client
    aid = _onboard(c)
    r = c.post("/v1/athlete/me/intervals/verify", headers={"X-Athlete-Id": aid})
    assert r.status_code == 400


def test_smoke_test_intervals_hard_timeout(monkeypatch):
    import intervals_smoke as smoke

    def _hang(*_a, **_k):
        import time

        time.sleep(30)
        return True, None

    monkeypatch.setattr(smoke, "_request_athlete", _hang)
    ok, err = smoke.smoke_test_intervals("k", "i1", timeout_s=0.3)
    assert ok is False
    assert err and "Tidsavbrudd" in err


def test_overview_progress_demo_and_season_targets(client):
    c, _ = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}

    ov = c.get("/v1/overview", headers=headers)
    assert ov.status_code == 200
    data = ov.json()
    assert data["progress"]["source"] == "demo"
    bike = next(d for d in data["progress"]["disciplines"] if d["id"] == "bike")
    assert bike["completed_hours"] == 175.0
    assert bike["target_hours"] == 500.0  # demo default
    assert bike["compliance_pct"] == 35.0
    assert data["periodization"]["current_block"] is None
    assert data["periodization"]["days_to_goal"] is None

    patch = c.patch(
        "/v1/athlete/me",
        headers=headers,
        json={
            "season_bike_hours_target": 500,
            "season_swim_hours_target": 100,
            "season_run_hours_target": 150,
            "season_strength_hours_target": 50,
            "season_start_date": "2026-01-01",
            "goal_race_date": "2027-08-20",
        },
    )
    assert patch.status_code == 200
    a = patch.json()["athlete"]
    assert a["season_bike_hours_target"] == 500
    assert a["goal_race_date"] == "2027-08-20"

    ov2 = c.get("/v1/overview", headers=headers)
    assert ov2.json()["season_targets"]["bike"] == 500
    assert ov2.json()["periodization"]["goal_race_date"] == "2027-08-20"
    assert ov2.json()["periodization"]["days_to_goal"] is not None


def test_plan_blocks_crud_and_overview_strip(client):
    c, _ = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}

    empty = c.get("/v1/athlete/me/plan-blocks", headers=headers)
    assert empty.status_code == 200
    assert empty.json()["blocks"] == []

    created = c.post(
        "/v1/athlete/me/plan-blocks",
        headers=headers,
        json={
            "title": "Base 1",
            "theme": "Aerob + svøm",
            "start_date": "2026-09-01",
            "end_date": "2026-09-28",
            "weekly_hours": 8,
        },
    )
    assert created.status_code == 200, created.text
    bid = created.json()["block"]["id"]
    assert created.json()["block"]["title"] == "Base 1"

    c.post(
        "/v1/athlete/me/plan-blocks",
        headers=headers,
        json={
            "title": "Base 2",
            "theme": "Bygg",
            "start_date": "2026-09-29",
            "end_date": "2026-10-26",
            "weekly_hours": 10,
        },
    )

    patched = c.patch(
        f"/v1/athlete/me/plan-blocks/{bid}",
        headers=headers,
        json={"theme": "Aerob kapasitet"},
    )
    assert patched.status_code == 200
    assert patched.json()["block"]["theme"] == "Aerob kapasitet"

    ov = c.get("/v1/overview", headers=headers)
    assert ov.status_code == 200
    peri = ov.json()["periodization"]
    assert peri["blocks_count"] == 2
    # Current depends on today's date; at least one of current/next should be set
    assert peri["current_block"] is not None or peri["next_block"] is not None

    deleted = c.delete(f"/v1/athlete/me/plan-blocks/{bid}", headers=headers)
    assert deleted.status_code == 200
    left = c.get("/v1/athlete/me/plan-blocks", headers=headers)
    assert len(left.json()["blocks"]) == 1


def test_overview_progress_from_intervals_when_linked(client, monkeypatch):
    """Credentials + mocked ICU activities → source intervals (not demo hours)."""
    c, _ = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}

    monkeypatch.setattr(
        main_mod,
        "smoke_test_intervals",
        lambda key, icu: (True, None),
    )
    put = c.put(
        "/v1/athlete/me/intervals",
        headers=headers,
        json={
            "intervals_athlete_id": "i42",
            "intervals_api_key": "live-key-for-progress",
            "verify": False,
        },
    )
    assert put.status_code == 200

    c.patch(
        "/v1/athlete/me",
        headers=headers,
        json={
            "season_bike_hours_target": 500,
            "season_swim_hours_target": 100,
            "season_run_hours_target": 150,
            "season_strength_hours_target": 50,
            "season_start_date": "2026-01-01",
            "goal_race_date": "2027-08-20",
        },
    )

    acts = [
        {
            "id": "r1",
            "type": "Ride",
            "moving_time": 3600 * 10,
            "start_date_local": "2026-03-01T08:00:00",
        },
        {
            "id": "s1",
            "type": "Swim",
            "moving_time": 3600,
            "start_date_local": "2026-03-02T07:00:00",
        },
    ]

    def _fake_fetch(api_key, athlete_id, oldest, newest, **kwargs):
        assert athlete_id == "i42"
        assert api_key == "live-key-for-progress"
        return acts

    import progress_compliance as pc

    monkeypatch.setattr(pc, "fetch_intervals_activities", _fake_fetch)
    pc.clear_progress_cache()

    ov = c.get("/v1/overview", headers=headers)
    assert ov.status_code == 200
    progress = ov.json()["progress"]
    assert progress["source"] == "intervals"
    assert progress["activity_count"] == 2
    bike = next(d for d in progress["disciplines"] if d["id"] == "bike")
    assert bike["completed_hours"] == 10.0
    assert bike["compliance_pct"] == 2.0
    peri = ov.json()["periodization"]
    assert peri["days_to_goal"] is not None
    assert peri["goal_race_date"] == "2027-08-20"
