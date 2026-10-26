"""Coach ticker — athlete_events unread strip + CTL alert + email opt-in path."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import config
import main as main_mod
from db import (
    count_unread_athlete_events,
    db_session,
    init_db,
    insert_athlete_event,
    list_athlete_events,
)
from ticker import (
    KIND_CTL_OVERLOAD,
    KIND_SESSIONS_SAVED,
    evaluate_ctl_overload,
    evaluate_readiness_soft,
    emit_sessions_saved,
    send_event_email,
    within_cooldown,
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "ticker.db"
    athletes = tmp_path / "athletes"
    athletes.mkdir()
    monkeypatch.setattr(config, "DATABASE_PATH", db)
    monkeypatch.setattr(config, "ATHLETES_DATA_DIR", athletes)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setattr(config, "DATABASE_URL", "")
    # Ensure get_db uses sqlite path
    monkeypatch.setenv("DATABASE_PATH", str(db))
    init_db(db)
    with TestClient(main_mod.app) as c:
        yield c, db


def _onboard(c, username: str = "ticker-a") -> str:
    r = c.post(
        "/v1/onboarding",
        json={
            "display_name": "Ticker",
            "username": username,
            "coach_display_name": "Ole",
            "coach_personality": "direkte",
            "accent_color": "#1a6b4a",
            "goal_text": "Base",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["athlete"]["id"]


def test_ctl_overload_bands():
    assert evaluate_ctl_overload(ctl=100, atl=120) is None
    soft = evaluate_ctl_overload(ctl=100, atl=135)
    assert soft and soft["payload"]["severity"] == "soft"
    hard = evaluate_ctl_overload(ctl=100, atl=160)
    assert hard and hard["payload"]["severity"] == "hard"
    assert hard["payload"]["auto_apply"] is False


def test_readiness_soft_only_before_hard_day():
    assert (
        evaluate_readiness_soft(
            sleep_avg_hours=5.5, hard_day_ahead=False
        )
        is None
    )
    hit = evaluate_readiness_soft(
        sleep_avg_hours=5.5, hard_day_ahead=True
    )
    assert hit and hit["kind"] == "readiness_soft"
    assert hit["payload"]["auto_apply"] is False


def test_events_list_and_mark_read(client):
    c, db = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}
    with db_session(db) as conn:
        emit_sessions_saved(conn, aid, count=2, source="test")
        assert count_unread_athlete_events(conn, aid) == 1

    listed = c.get("/v1/athlete/me/events?refresh=false", headers=headers)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["auto_apply"] is False
    assert body["human_coach"] is True
    assert body["unread_count"] >= 1
    ev = body["events"][0]
    assert ev["kind"] == KIND_SESSIONS_SAVED
    assert ev["unread"] is True

    marked = c.post(
        f"/v1/athlete/me/events/{ev['id']}/read",
        headers=headers,
        json={},
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()["event"]["unread"] is False
    assert marked.json()["unread_count"] == 0


def test_email_opt_in_patch_and_send_path_without_key(client, monkeypatch):
    c, db = client
    aid = _onboard(c, username="ticker-mail")
    headers = {"X-Athlete-Id": aid}

    bad = c.patch(
        "/v1/athlete/me",
        headers=headers,
        json={"email": "not-an-email", "notify_email": True},
    )
    assert bad.status_code == 400

    ok = c.patch(
        "/v1/athlete/me",
        headers=headers,
        json={"email": "william@example.com", "notify_email": True},
    )
    assert ok.status_code == 200, ok.text
    ath = ok.json()["athlete"]
    assert ath["email"] == "william@example.com"
    assert ath["notify_email"] is True
    assert ok.json()["email_notify"]["opt_in"] is True
    assert ok.json()["email_notify"]["resend_configured"] is False

    # Send path returns clear reason — no invented secrets
    status = send_event_email(
        ath,
        {
            "kind": KIND_SESSIONS_SAVED,
            "title": "Test",
            "payload": {"message": "hello"},
        },
    )
    assert status["sent"] is False
    assert status["reason"] == "no_resend_key"


def test_ctl_event_emitted_via_refresh_helper(client):
    c, db = client
    aid = _onboard(c, username="ticker-ctl")
    with db_session(db) as conn:
        from ticker import maybe_emit_ctl_from_load

        row = maybe_emit_ctl_from_load(
            conn, aid, {"available": True, "ctl": 80.0, "atl": 130.0}
        )
        assert row is not None
        assert row["kind"] == KIND_CTL_OVERLOAD
        # Cooldown blocks duplicate
        again = maybe_emit_ctl_from_load(
            conn, aid, {"available": True, "ctl": 80.0, "atl": 130.0}
        )
        assert again is None
        assert within_cooldown(conn, aid, KIND_CTL_OVERLOAD)


def test_web_has_ticker_strip_no_auto_apply():
    web = Path(__file__).resolve().parents[3] / "apps" / "coach-web" / "src" / "main.js"
    text = web.read_text(encoding="utf-8")
    assert "renderTickerStrip" in text
    assert "/v1/athlete/me/events" in text
    assert "aldri auto-apply" in text.lower() or "never auto-apply" in text.lower()
    assert "notify_email" in text


def test_athlete_events_schema_and_helpers(client):
    c, db = client
    aid = _onboard(c, username="ticker-schema")
    with db_session(db) as conn:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='athlete_events'"
        )
        assert cur.fetchone() is not None
        row = insert_athlete_event(
            conn,
            aid,
            kind=KIND_SESSIONS_SAVED,
            title="schema stub",
            payload={"auto_apply": False},
        )
        assert row["id"]
        assert row["athlete_id"] == aid
        listed = list_athlete_events(conn, aid)
        assert any(e["id"] == row["id"] for e in listed)
