"""Coach write path — kill prose-only / hallucinated Intervals success.

Transcript patterns that must die:
1. «kan du lage en økt for i morgen» → workout_proposal card (not prose-only)
2. Multi-day adjust fre–lør / helg → plan_proposal week card
3. «oppdater til intervals» + «ok» → real sync endpoint / intervals_pending;
   never «jeg har oppdatert» / «manuelt i Intervals» without confirm→API
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
from athlete_constraints import ICU_SYNC_WEEKS
from chat_service import (
    extract_workout_proposal,
    infer_plan_update_fallback,
    infer_workout_proposal_fallback,
    plan_week_target_from_message,
    reconcile_workout_sports,
    reopen_pending_write_reply,
    sanitize_unconfirmed_write_claims,
    user_confirms_pending_write,
    user_requests_intervals_plan_sync,
    user_requests_plan_adjust,
    user_requests_plan_week_build,
    user_requests_session_change,
    write_intent_kind,
)
from db import db_session, init_db, upsert_athlete_secrets


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


def _confirm_setup(c, *, username="write-path", sessions=3):
    preview = c.post(
        "/v1/setup/plan/preview",
        json={
            "display_name": "William",
            "username": username,
            "goal_text": "Halvmaraton 2027",
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
            "goal_text": "Halvmaraton 2027",
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


def _stored_sync_bundle(*, workouts=4):
    events = [
        {
            "external_id": f"ll-coach-w-{i}",
            "name": f"Økt {i}",
            "category": "WORKOUT",
            "start_date_local": f"2026-10-{1 + i:02d}T07:00:00",
        }
        for i in range(workouts)
    ]
    return {
        "events": events,
        "events_preview": [
            {
                "external_id": e["external_id"],
                "name": e["name"],
                "category": e["category"],
                "preview_no": e["name"],
                "start_date_local": e.get("start_date_local"),
            }
            for e in events
        ],
        "workouts_preview": [
            {"name": e["name"], "category": "WORKOUT"} for e in events
        ],
        "notes_count": 0,
        "workouts_count": workouts,
        "zwo_count": 0,
        "count": workouts,
        "weeks": ICU_SYNC_WEEKS,
        "builder": "test",
        "knowledge_paths": [],
        "from_stored_sessions": True,
        "kind": "calendar_notes_and_stored_workouts",
        "description_no": "fra planned_sessions",
        "icu_sync_weeks": ICU_SYNC_WEEKS,
        "error": None,
    }


def test_lag_plan_neste_uke_triggers_plan_path():
    msg = "Lag en plan for neste uke"
    assert user_requests_plan_week_build(msg)
    assert user_requests_plan_adjust(msg)
    assert write_intent_kind(msg) == "plan"
    fb = infer_plan_update_fallback(msg)
    assert fb and fb["scope"] == "week"
    assert fb.get("week_start") == "next_week"
    assert plan_week_target_from_message(msg) == "next_week"


def test_day_swap_and_lett_uke_open_plan_card_intent():
    """QA: day swap / lett uke must hit plan_adjust fallback (confirm card), not prose-only."""
    for msg in (
        "Bytt tirsdag → onsdag (foreldremøte)",
        "Kan du bytte tirsdag til onsdag?",
        "flytt tirsdagsøkta til onsdag",
    ):
        assert user_requests_plan_adjust(msg), msg
        assert write_intent_kind(msg) == "plan", msg
        fb = infer_plan_update_fallback(msg)
        assert fb and fb["scope"] == "week", msg
        assert fb.get("day_swap") is True, msg
        assert fb.get("ease_load") is False, msg

    for msg in (
        "Sliten — lett uke",
        "Jeg er sliten, kan vi ha en lett uke?",
        "lette neste økter pga høy belastning",
    ):
        assert user_requests_plan_adjust(msg), msg
        assert write_intent_kind(msg) == "plan", msg
        fb = infer_plan_update_fallback(msg)
        assert fb and fb["scope"] == "week", msg
        assert fb.get("ease_load") is True, msg


def test_uke_replace_and_uka_scope_intents():
    """QA BLOCKED: erstatt uka / juster uka → week confirm card, not full/prose."""
    from chat_service import (
        user_requests_dont_touch_calendar,
        user_requests_intervals_review,
        user_wants_week_rebuild,
    )

    for msg in (
        "erstatt uka",
        "erstatt hele uka",
        "juster uka",
        "juster denne uka",
        "bygg om uken",
        "oppdater uka",
    ):
        assert user_requests_plan_adjust(msg), msg
        fb = infer_plan_update_fallback(msg)
        assert fb and fb["scope"] == "week", (msg, fb)
        assert user_wants_week_rebuild(msg), msg

    assert user_requests_dont_touch_calendar("ikke rør kalenderen — bare lagre")
    assert user_requests_dont_touch_calendar("uten å synce til intervals")
    assert not user_requests_dont_touch_calendar("legg inn økt i morgen")

    assert user_requests_intervals_review("sjekk Intervals-kalenderen min")
    assert user_requests_intervals_review("gjennomgå hva som ligger på ICU denne uka")
    assert not user_requests_intervals_review("sync planen til intervals")


def test_reconcile_wrong_fence_sport_swim_for_run():
    reply = (
        "Forslag:\n```workout_proposal\n"
        '{"workouts":[{"name":"løpetur rolig","date":"2026-10-04",'
        '"sport":"swim","duration_minutes":40,"description":"rolig"}]}\n```'
    )
    _disp, prop = extract_workout_proposal(reply)
    assert prop and prop["workouts"][0]["sport"] == "swim"
    fixed = reconcile_workout_sports(prop, "legg inn rolig løp i morgen 40 min")
    assert fixed["workouts"][0]["sport"] == "run"


def test_intent_detect_create_tomorrow_and_weekend():
    assert user_requests_session_change("kan du lage en økt for i morgen")
    assert user_requests_session_change("lage en økt i morgen 40 min")
    assert write_intent_kind("kan du lage en økt for i morgen") == "session"
    assert not user_requests_intervals_plan_sync("kan du lage en økt for i morgen")

    for msg in (
        "juster fre og lør",
        "juster fredag og lørdag",
        "endre helgen",
        "juster helga",
        "oppdater fre-lør",
    ):
        assert user_requests_plan_adjust(msg), msg
        assert write_intent_kind(msg) == "plan", msg
        fb = infer_plan_update_fallback(msg)
        assert fb and fb["scope"] == "week", msg

    for msg in (
        "oppdater dette til intervals",
        "oppdater til intervals",
        "legg inn dette i intervals",
        "oppdater intervals",
    ):
        assert user_requests_intervals_plan_sync(msg), msg
        assert write_intent_kind(msg) == "sync", msg
        assert not user_requests_session_change(msg), msg


def test_sanitize_blocks_success_and_manual_intervals():
    honest = sanitize_unconfirmed_write_claims(
        "Jeg har oppdatert Intervals. Øktene er synket.",
        has_confirm_card=False,
    )
    assert "jeg har oppdatert" not in honest.lower()
    assert "forhåndsvis" in honest.lower() or "bekreft" in honest.lower()
    assert "manuelt" not in honest.lower() or "ikke redigere" in honest.lower()

    with_card = sanitize_unconfirmed_write_claims(
        "Forslag klart. Rediger manuelt i Intervals hvis du vil.",
        has_confirm_card=True,
    )
    assert "manuelt i intervals" not in with_card.lower()
    assert "bekreft" in with_card.lower() or "forhåndsvis" in with_card.lower()


def test_ok_after_prose_write_reopens_card_not_llm_success():
    offer = {
        "role": "assistant",
        "content": (
            "Struktur i morgen: 40 min løp. Oppvarming + hoveddel. "
            "Bekreft så legger jeg det inn."
        ),
    }
    assert user_confirms_pending_write("ok", [offer]) is True
    assert user_confirms_pending_write("ja", [offer]) is True
    assert user_confirms_pending_write("oppdater", [offer]) is True
    reply, prop, plan = reopen_pending_write_reply([offer], today=date(2026, 10, 1))
    assert prop and prop.get("workouts")
    assert "kort" in reply.lower() or "forhåndsvis" in reply.lower()
    assert "jeg har oppdatert" not in reply.lower()
    assert plan is None


def test_chat_create_tomorrow_always_attaches_proposal(client):
    c, _a, _db = client
    setup = _confirm_setup(c, username="create-tmr")
    aid = setup["athlete"]["id"]
    headers = {"X-Athlete-Id": aid}
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    # LLM returns prose only — no fence (live bug)
    prose = (
        f"Ok — her er struktur for {tomorrow}:\n"
        "- Oppvarming 10 min\n- Hoveddel 25 min Z2\n- Nedkjøling 5 min\n"
        "Bekreft så legger jeg det inn."
    )
    with (
        patch("main.call_llm", return_value=prose) as llm,
        patch(
            "main.resolve_wellness_bundle",
            return_value={"recovery_signals": {"available": False}},
        ),
    ):
        r = c.post(
            "/v1/chat",
            headers=headers,
            json={"message": "kan du lage en økt for i morgen"},
        )
    assert r.status_code == 200, r.text
    llm.assert_called()
    body = r.json()
    workouts = (body.get("workout_proposal") or {}).get("workouts") or []
    assert workouts, "must attach confirmable workout_proposal (not prose-only)"
    assert body.get("confirm_required") is True
    assert workouts[0]["date"] == tomorrow
    low = (body.get("reply") or "").lower()
    assert "jeg har oppdatert" not in low
    assert "synket" not in low or "ikke" in low


def test_chat_lag_plan_neste_uke_skips_llm_and_uses_sot(client):
    c, _a, _db = client
    setup = _confirm_setup(c, username="neste-uke")
    aid = setup["athlete"]["id"]
    headers = {"X-Athlete-Id": aid}
    with (
        patch("main.call_llm") as llm,
        patch(
            "main.resolve_wellness_bundle",
            return_value={"recovery_signals": {"available": False}},
        ),
    ):
        r = c.post(
            "/v1/chat",
            headers=headers,
            json={"message": "Lag en plan for neste uke"},
        )
    llm.assert_not_called()
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("week_plan_from_sot") is True
    prop = body.get("plan_proposal") or {}
    low = (body.get("reply") or "").lower()
    assert prop.get("scope") == "week" or "allerede" in low or "kalender" in low
    low = (body.get("reply") or "").lower()
    assert "hvilke dager" not in low
    assert "trenger jeg litt mer informasjon" not in low


def test_chat_adjust_fri_sun_attaches_week_plan(client):
    c, _a, _db = client
    setup = _confirm_setup(c, username="adj-fri")
    aid = setup["athlete"]["id"]
    headers = {"X-Athlete-Id": aid}

    prose = (
        "Forslag fre–lør: lettere løp fredag, rolig langtur lørdag. "
        "Skal jeg oppdatere Intervals?"
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
            json={"message": "juster fre og lør"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    prop = body.get("plan_proposal") or {}
    assert prop.get("scope") == "week" or prop.get("sessions") is not None, body
    assert body.get("confirm_required") is True
    low = (body.get("reply") or "").lower()
    assert "jeg har oppdatert" not in low
    assert "manuelt i intervals" not in low


def test_oppdater_til_intervals_then_ok_requires_sync_endpoint(client):
    """«oppdater til intervals» + «ok» cannot claim success without sync pending/API."""
    c, _a, db = client
    setup = _confirm_setup(c, username="sync-ok")
    aid = setup["athlete"]["id"]
    headers = {"X-Athlete-Id": aid}

    with db_session(db) as conn:
        upsert_athlete_secrets(
            conn, aid, intervals_api_key="k", intervals_athlete_id="i1"
        )

    bundle = _stored_sync_bundle(workouts=4)

    with (
        patch("main.call_llm") as llm,
        patch("main._sync_bundle_preferring_stored", return_value=bundle),
    ):
        r1 = c.post(
            "/v1/chat",
            headers=headers,
            json={"message": "oppdater dette til intervals"},
        )
        llm.assert_not_called()
    assert r1.status_code == 200, r1.text
    b1 = r1.json()
    assert b1.get("intervals_sync_intent") is True
    assert b1.get("intervals_pending") is not None
    assert b1["intervals_pending"]["confirm_required"] is True
    assert b1["intervals_pending"]["pending_id"]
    assert not (b1.get("workout_proposal") or {}).get("workouts")
    low1 = (b1.get("reply") or "").lower()
    assert "jeg har oppdatert" not in low1
    assert "manuelt" not in low1

    with (
        patch("main.call_llm") as llm2,
        patch("main._sync_bundle_preferring_stored", return_value=bundle),
    ):
        r2 = c.post(
            "/v1/chat",
            headers=headers,
            json={"message": "ok"},
        )
        llm2.assert_not_called()
    assert r2.status_code == 200, r2.text
    b2 = r2.json()
    assert b2.get("intervals_sync_intent") is True
    assert b2.get("intervals_pending") is not None
    assert b2["intervals_pending"]["pending_id"]
    low2 = (b2.get("reply") or "").lower()
    assert "jeg har oppdatert" not in low2
    assert "manuelt i intervals" not in low2

    pending_id = b2["intervals_pending"]["pending_id"]
    with patch("main.post_events_bulk", return_value={"count": 4}) as mock_post:
        done = c.post(
            "/v1/athlete/me/intervals/calendar/confirm",
            headers=headers,
            json={"pending_id": pending_id},
        )
    assert done.status_code == 200, done.text
    mock_post.assert_called_once()
    assert done.json().get("pushed", 0) >= 1 or done.json().get("op")


def test_ok_after_create_prose_never_hallucinates_success(client):
    c, _a, _db = client
    setup = _confirm_setup(c, username="ok-prose")
    aid = setup["athlete"]["id"]
    headers = {"X-Athlete-Id": aid}
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    prose = (
        f"Økt {tomorrow}: 40 min løp. Oppvarming + hoveddel. "
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
            json={"message": "kan du lage en økt for i morgen 40 min"},
        )
    assert r1.status_code == 200
    assert (r1.json().get("workout_proposal") or {}).get("workouts")

    # «ok» must NOT call LLM with success claim — reopen card
    with patch("main.call_llm") as llm:
        r2 = c.post(
            "/v1/chat",
            headers=headers,
            json={"message": "ok"},
        )
        llm.assert_not_called()
    assert r2.status_code == 200, r2.text
    b2 = r2.json()
    assert b2.get("pending_write_reopen") is True
    low = (b2.get("reply") or "").lower()
    assert "jeg har oppdatert" not in low
    assert "synket" not in low or "ikke" in low
    assert "manuelt i intervals" not in low
    # Card re-shown OR honest no-write message
    has_card = bool((b2.get("workout_proposal") or {}).get("workouts"))
    assert has_card or "ingenting" in low


def test_infer_tomorrow_without_fence():
    prop = infer_workout_proposal_fallback(
        "kan du lage en økt for i morgen",
        "Rolig tur. Bekreft.",
        today=date(2026, 10, 1),
    )
    assert prop and prop["workouts"][0]["date"] == "2026-10-02"
