"""Live transcript fixes on supabase: confirm phrases, NOTES-off sync, replace, builder, roll.

Covers:
1. Confirm phrases («det ser bra ut», «bekreft», «ok sync») attach card — never silent persist claim
2. Sync near-window payload excludes grov NOTES by default
3. Weekly cap full → replace offer (not dead-end)
4. Øktbygger route + UI marker present
5. «rull videre» / «neste måned» → plan_roll card
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
from athlete_constraints import ICU_SYNC_WEEKS, validate_workouts_against_constraints
from chat_service import (
    user_confirms_intervals_plan_sync,
    user_confirms_pending_write,
)
from db import (
    db_session,
    init_db,
    insert_planned_session_rows,
    list_planned_sessions,
    upsert_athlete_secrets,
)
from plan_workouts import build_plan_sync_bundle
from two_tier_plan import user_requests_explicit_roll


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
        yield c, athletes, db


def _confirm_setup(c, *, username="live-fix", sessions=3):
    preview = c.post(
        "/v1/setup/plan/preview",
        json={
            "display_name": "William",
            "username": username,
            "goal_text": "Lofoten Half Extreme 2027",
            "background_notes": f"Form OK, {sessions} økter i uka, løp og styrke",
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


def test_confirm_phrases_include_det_ser_bra_ut_and_ok_sync():
    offer = {
        "role": "assistant",
        "content": (
            "Struktur i morgen: 40 min løp. Oppvarming + hoveddel. "
            "Bekreft så legger jeg det inn."
        ),
    }
    for phrase in (
        "det ser bra ut",
        "ser bra ut",
        "bekreft",
        "ja lagre",
        "lagre",
    ):
        assert user_confirms_pending_write(phrase, [offer]) is True, phrase

    sync_offer = {
        "role": "assistant",
        "content": (
            "Bekreft Sync-forhåndsvisningen. Jeg synker nærvinduet "
            "fra lagrede planned_sessions."
        ),
    }
    assert user_confirms_intervals_plan_sync("ok sync", [sync_offer]) is True
    assert user_confirms_intervals_plan_sync("ok", [sync_offer]) is True


def test_chat_confirm_phrase_reattaches_card(client):
    c, _a, _db = client
    setup = _confirm_setup(c, username="confirm-phrase")
    aid = setup["athlete"]["id"]
    headers = {"X-Athlete-Id": aid}
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    prose = (
        f"Ok — her er struktur for {tomorrow}:\n"
        "- Oppvarming 10 min\n- Hoveddel 25 min Z2\n"
        "Bekreft så legger jeg det inn."
    )
    with (
        patch("main.call_llm", return_value=prose),
        patch(
            "main.resolve_wellness_bundle",
            return_value={"recovery_signals": {"available": False}},
        ),
    ):
        r1 = c.post(
            "/v1/chat",
            headers=headers,
            json={"message": "lag økt i morgen"},
        )
    assert r1.status_code == 200
    assert (r1.json().get("workout_proposal") or {}).get("workouts")

    with patch("main.call_llm") as llm:
        r2 = c.post(
            "/v1/chat",
            headers=headers,
            json={"message": "det ser bra ut"},
        )
        llm.assert_not_called()
    assert r2.status_code == 200, r2.text
    b2 = r2.json()
    assert b2.get("pending_write_reopen") is True
    has_card = bool(
        (b2.get("workout_proposal") or {}).get("workouts")
        or b2.get("workout_replace_proposal")
    )
    assert has_card, "confirm phrase must re-attach preview/replace card"
    low = (b2.get("reply") or "").lower()
    assert "jeg har oppdatert" not in low
    assert "synket" not in low or "ikke" in low


def test_sync_bundle_excludes_grov_notes_by_default():
    blocks = [
        {
            "id": "b1",
            "title": "B0 Startblokk",
            "theme": "base",
            "start_date": "2026-09-01",
            "end_date": "2027-08-20",
            "weekly_hours": 6,
            "layer": "grov",
        }
    ]
    planned = [
        {
            "id": "ps1",
            "session_date": date.today().isoformat(),
            "sport": "run",
            "name": "Rolig løp",
            "duration_minutes": 40,
            "description": "Z2",
            "start_time": "07:00",
            "external_id": "ll-coach-w-test1",
            "source": "plan",
            "status": "planned",
        }
    ]
    # Default / explicit False — no NOTES flood
    bundle = build_plan_sync_bundle(
        blocks,
        athlete={"sessions_per_week": 3, "allowed_disciplines": ["run"]},
        include_notes=False,
        allow_degraded=True,
        planned_sessions=planned,
        today=date.today(),
        weeks=ICU_SYNC_WEEKS,
    )
    assert int(bundle.get("notes_count") or 0) == 0
    cats = {e.get("category") for e in (bundle.get("events") or [])}
    assert "NOTE" not in cats
    # Opt-in still works
    with_notes = build_plan_sync_bundle(
        blocks,
        athlete={"sessions_per_week": 3},
        include_notes=True,
        allow_degraded=True,
        planned_sessions=planned,
        today=date.today(),
        weeks=ICU_SYNC_WEEKS,
    )
    assert int(with_notes.get("notes_count") or 0) > 0


def test_calendar_preview_defaults_include_notes_false(client):
    c, _a, db = client
    setup = _confirm_setup(c, username="sync-notes-off")
    aid = setup["athlete"]["id"]
    headers = {"X-Athlete-Id": aid}
    with db_session(db) as conn:
        upsert_athlete_secrets(
            conn,
            aid,
            intervals_api_key="test-key",
            intervals_athlete_id="i123",
        )
    # Force bundle with notes if include_notes wrongly True — assert API default
    captured = {}

    def _fake_bundle(*args, **kwargs):
        captured["include_notes"] = kwargs.get("include_notes")
        return {
            "events": [
                {
                    "external_id": "ll-coach-w-1",
                    "name": "Økt",
                    "category": "WORKOUT",
                    "start_date_local": f"{date.today().isoformat()}T07:00:00",
                }
            ],
            "events_preview": [{"name": "Økt", "category": "WORKOUT"}],
            "notes_count": 0,
            "workouts_count": 1,
            "zwo_count": 0,
            "count": 1,
            "weeks": ICU_SYNC_WEEKS,
            "builder": "test",
            "knowledge_paths": [],
            "from_stored_sessions": True,
            "kind": "stored",
            "description_no": "test",
        }

    with patch("main.build_plan_sync_bundle", side_effect=_fake_bundle):
        r = c.post(
            "/v1/athlete/me/intervals/calendar/preview",
            headers=headers,
            json={"op": "push"},
        )
    assert r.status_code == 200, r.text
    assert captured.get("include_notes") is False
    body = r.json()
    assert int(body.get("notes_count") or 0) == 0


def test_weekly_cap_offers_replace_not_dead_end(client):
    c, _a, db = client
    setup = _confirm_setup(c, username="cap-replace", sessions=3)
    aid = setup["athlete"]["id"]
    headers = {"X-Athlete-Id": aid}
    today = date.today()
    start = today - timedelta(days=today.weekday())
    # Fill this ISO week with 3 planned sessions (cap)
    rows = [
        {
            "session_date": (start + timedelta(days=i)).isoformat(),
            "sport": "run",
            "name": f"Ukeøkt {i}",
            "duration_minutes": 40,
            "description": "Z2",
            "source": "plan",
            "status": "planned",
        }
        for i in range(3)
    ]
    with db_session(db) as conn:
        insert_planned_session_rows(conn, aid, rows)
        existing = list_planned_sessions(
            conn,
            aid,
            start_date=start.isoformat(),
            end_date=(start + timedelta(days=6)).isoformat(),
        )
    assert len(existing) >= 3

    tomorrow = (today + timedelta(days=1)).isoformat()
    prose = (
        f"Ny økt {tomorrow}: 45 min løp. Oppvarming + hoveddel. "
        "Bekreft så legger jeg det inn."
    )
    with (
        patch("main.call_llm", return_value=prose),
        patch(
            "main.resolve_wellness_bundle",
            return_value={"recovery_signals": {"available": False}},
        ),
    ):
        r = c.post(
            "/v1/chat",
            headers=headers,
            json={"message": "lag økt i morgen"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    prop = body.get("workout_proposal") or {}
    replace = body.get("workout_replace_proposal") or {}
    assert prop.get("replace_required") or replace.get("replace_candidates"), body
    candidates = prop.get("replace_candidates") or replace.get("replace_candidates") or []
    assert candidates, "must offer replace candidates when week is full"
    assert not body.get("workout_proposal_blocked") or candidates

    # Preview with replace_session_ids persists path
    rid = candidates[0]["id"]
    prev = c.post(
        "/v1/athlete/me/intervals/workouts/preview",
        headers=headers,
        json={
            "workouts": [
                {
                    "date": tomorrow,
                    "name": "Ny erstatningsøkt",
                    "sport": "run",
                    "duration_minutes": 45,
                    "description": "Z2",
                }
            ],
            "prepare_intervals_sync": False,
            "replace_session_ids": [rid],
        },
    )
    assert prev.status_code == 200, prev.text
    pending = prev.json()
    assert pending.get("pending_id")
    assert rid in (pending.get("replace_session_ids") or [])

    conf = c.post(
        "/v1/athlete/me/intervals/calendar/confirm",
        headers=headers,
        json={"pending_id": pending["pending_id"]},
    )
    assert conf.status_code == 200, conf.text
    assert conf.json().get("planned_sessions_saved", 0) >= 1


def test_cap_gate_ask_mentions_replace():
    athlete = {
        "sessions_per_week": 3,
        "allowed_disciplines": ["run"],
        "agreements": ["3 økter/uke"],
    }
    gate = validate_workouts_against_constraints(
        athlete,
        [{"date": "2026-10-02", "name": "Extra", "sport": "run", "duration_minutes": 40}],
        existing_planned_this_week=3,
    )
    assert gate["cap_hit"] is True
    assert gate["ok"] is False
    ask = (gate.get("ask") or "").lower()
    assert "erstat" in ask or "replace" in ask


def test_builder_confirm_route_and_ui_marker(client):
    c, _a, db = client
    setup = _confirm_setup(c, username="builder-ui")
    aid = setup["athlete"]["id"]
    headers = {"X-Athlete-Id": aid}
    day = (date.today() + timedelta(days=2)).isoformat()
    with db_session(db) as conn:
        rows = insert_planned_session_rows(
            conn,
            aid,
            [
                {
                    "session_date": day,
                    "sport": "run",
                    "name": "Byggerøkt",
                    "duration_minutes": 40,
                    "description": "",
                    "source": "plan",
                    "status": "planned",
                    "external_id": f"ll-coach-w-{day.replace('-', '')}-bygger",
                }
            ],
        )
    sid = rows[0]["id"]
    conf = c.post(
        f"/v1/sessions/{sid}/builder/confirm",
        headers=headers,
        json={
            "name": "Byggerøkt",
            "date": day,
            "sport": "run",
            "steps": [
                {"type": "warmup", "duration_minutes": 10, "intensity": "Z2"},
                {"type": "work", "duration_minutes": 25, "intensity": "Z3"},
                {"type": "cooldown", "duration_minutes": 5},
            ],
            "prepare_intervals_sync": False,
        },
    )
    assert conf.status_code == 200, conf.text
    assert conf.json().get("builder_steps")
    assert len(conf.json()["builder_steps"]) == 3
    # Detail via evt:external_id should expose builder / app_planned
    evt_id = f"evt:ll-coach-w-{day.replace('-', '')}-bygger"
    detail = c.get(f"/v1/sessions/{evt_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    d = detail.json()
    assert d.get("editable") or d.get("session", {}).get("app_planned")
    assert "builder_steps" in d or "builder_steps" in (d.get("editable_fields") or {})
    # UI must surface Øktbygger label
    web = Path(__file__).resolve().parents[3] / "apps" / "coach-web" / "src" / "main.js"
    text = web.read_text(encoding="utf-8")
    assert "Øktbygger" in text
    assert "oktbygger-section" in text or "builder-panel" in text
    assert "/builder/confirm" in text


def test_rull_videre_surfaces_plan_roll_card(client):
    c, _a, _db = client
    setup = _confirm_setup(c, username="plan-roll")
    aid = setup["athlete"]["id"]
    headers = {"X-Athlete-Id": aid}
    assert user_requests_explicit_roll("rull videre")
    assert user_requests_explicit_roll("neste måned")

    with patch(
        "main.resolve_wellness_bundle",
        return_value={"recovery_signals": {"available": False}},
    ):
        r = c.post(
            "/v1/chat",
            headers=headers,
            json={"message": "rull videre"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    roll = body.get("plan_roll") or body.get("plan_proposal") or {}
    assert roll.get("op") == "plan_roll" or roll.get("scope") == "detalj"
    assert roll.get("sessions")
    assert body.get("confirm_required") is True
    # UI wires plan_roll / detalj
    web = Path(__file__).resolve().parents[3] / "apps" / "coach-web" / "src" / "main.js"
    text = web.read_text(encoding="utf-8")
    assert "plan_roll" in text or "scope === 'detalj'" in text or 'scope === "detalj"' in text
    assert "/plan/roll/confirm" in text


def test_athlete_events_schema_stub_exists(client):
    """Ticker table stub present — unread strip is next slice (no auto-apply)."""
    _c, _a, db = client
    with db_session(db) as conn:
        # SQLite: table created by init_db SCHEMA
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='athlete_events'"
        )
        row = cur.fetchone()
        assert row is not None, "athlete_events stub must exist in SCHEMA"
