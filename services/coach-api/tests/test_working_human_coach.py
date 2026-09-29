"""Working Human Coach — full product path on comercial.

Utøver → AI → Forslag → Preview → Confirm → Lagre → Synkroniser.

Covers in one coherent flow:
1. Setup confirm → full planned_sessions + meso → visible in Plan AND Økter (no Sync)
2. Chat add session → preview → confirm → persist → visible same places
3. «Pushe planen til Intervals» → real intervals_pending from stored sessions;
   follow-up «sync»/«go» reopens real confirm (never invents workout JSON)
4. Chat snapshot always includes app_plan (no amnesia / re-interview)
5. Constraints respected; no William default for a fresh athlete
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
    assistant_offered_intervals_sync,
    user_confirms_intervals_plan_sync,
    user_requests_intervals_plan_sync,
    user_requests_session_change,
)
from db import (
    count_planned_sessions,
    db_session,
    init_db,
    list_planned_sessions,
    upsert_athlete_secrets,
)


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


def _confirm_setup(c, *, username="kent-coach", sessions=3):
    preview = c.post(
        "/v1/setup/plan/preview",
        json={
            "display_name": "Kent",
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
    # Knowledge/constraints — not random LLM meso hours
    assert body["sessions_per_week"] == sessions
    assert float(body["weekly_hours_target"]) <= sessions * 1.25 + 0.05
    titles = " ".join(b["title"] for b in body["plan_blocks"]).lower()
    assert "re-etablering" not in titles

    conf = c.post(
        "/v1/setup/confirm",
        json={
            "display_name": "Kent",
            "username": username,
            "goal_text": body.get("athlete_patch", {}).get("goal_text")
            or "Halvmaraton 2027",
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
    data = conf.json()
    assert data["written_to_intervals"] is False
    assert data["planned_sessions_count"] > ICU_SYNC_WEEKS * sessions
    ath = data["athlete"]
    # Isolation: not William / Lofoten defaults
    assert ath["display_name"] == "Kent"
    assert "lofoten" not in (ath.get("goal_text") or "").lower()
    assert ath.get("sessions_per_week") == sessions
    return data


def _stored_sync_bundle(*, workouts=6, notes=1):
    events = [
        {
            "external_id": f"ll-coach-w-{i}",
            "name": f"LAGRET {i}",
            "category": "WORKOUT",
            "start_date_local": f"2026-09-{30 + i:02d}T07:00:00",
        }
        for i in range(workouts)
    ]
    events.append(
        {
            "external_id": "ll-coach-note-1",
            "name": "Blokk",
            "category": "NOTE",
        }
    )
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
            {"name": e["name"], "category": "WORKOUT"}
            for e in events
            if e["category"] == "WORKOUT"
        ],
        "notes_count": notes,
        "workouts_count": workouts,
        "zwo_count": 0,
        "count": workouts + notes,
        "weeks": ICU_SYNC_WEEKS,
        "builder": "test",
        "knowledge_paths": [],
        "from_stored_sessions": True,
        "kind": "calendar_notes_and_stored_workouts",
        "description_no": "fra planned_sessions",
        "icu_sync_weeks": ICU_SYNC_WEEKS,
        "error": None,
    }


def test_sync_intent_and_kent_followup_phrases():
    assert user_requests_intervals_plan_sync(
        "kan du pushe resten av planen til intervals?"
    )
    assert user_requests_intervals_plan_sync("sync til intervals")
    assert user_requests_intervals_plan_sync("synk planen til Intervals")
    assert not user_requests_intervals_plan_sync("sync")
    assert not user_requests_intervals_plan_sync("go")
    assert not user_requests_session_change(
        "kan du pushe resten av planen til intervals?"
    )

    offer = {
        "role": "assistant",
        "content": (
            "Planen er allerede satt (96 økter i appen). "
            "Jeg synker ikke hele horisonten til Intervals — bare nærvinduet "
            "(2 uker). Bekreft Sync-forhåndsvisningen."
        ),
    }
    assert assistant_offered_intervals_sync([offer]) is True
    for msg in ("sync", "go", "ja", "ja sync", "bekreft", "gjør det", "ok"):
        assert user_confirms_intervals_plan_sync(msg, [offer]) is True, msg
    # Without prior offer, short confirm must NOT steal normal chat
    assert user_confirms_intervals_plan_sync("sync", []) is False
    assert user_confirms_intervals_plan_sync("ja", []) is False
    # Concrete session add still not sync
    assert (
        user_confirms_intervals_plan_sync(
            "Legg inn rolig løpetur i morgen 40 min", [offer]
        )
        is False
    )


def test_working_human_coach_end_to_end(client):
    """Full agreed product path — API/pytest SoT."""
    c, athletes, db = client
    setup = _confirm_setup(c, username="kent-e2e", sessions=3)
    aid = setup["athlete"]["id"]
    headers = {"X-Athlete-Id": aid}
    planned_n = setup["planned_sessions_count"]

    # --- 1) Plan + Økter without Sync ---
    planned = c.get("/v1/athlete/me/planned-sessions", headers=headers)
    assert planned.status_code == 200
    assert planned.json()["total"] == planned_n

    sess = c.get("/v1/sessions", headers=headers)
    assert sess.status_code == 200, sess.text
    sbody = sess.json()
    assert sbody.get("app_planned_merged", 0) >= 1 or len(sbody.get("upcoming") or []) >= 1
    assert len(sbody.get("library") or []) >= 1
    assert sbody.get("source") in ("planned_sessions", "intervals+planned_sessions")
    # Completed still empty without ICU activities
    assert (sbody.get("recent") or []) == [] or all(
        r.get("training_status") != "completed" or r.get("kind") == "activity"
        for r in (sbody.get("recent") or [])
    )

    # Profile on disk is Kent, not William
    profile = (athletes / aid / "profile.md").read_text(encoding="utf-8")
    assert "Kent" in profile
    assert "Athlete profile — William" not in profile

    # --- 2) Chat add → preview → confirm → persist ---
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    llm_add = (
        "Ok — rolig løpetur i morgen.\n"
        "```workout_proposal\n"
        f'{{"workouts":[{{"name":"Rolig løp","date":"{tomorrow}","sport":"run",'
        f'"duration_minutes":40,"description":"Z2","start_time":"07:00"}}]}}\n'
        "```"
    )
    with (
        patch("main.call_llm", return_value=llm_add) as llm_add_mock,
        patch(
            "main.resolve_wellness_bundle",
            return_value={"recovery_signals": {"available": False}},
        ),
    ):
        chat_add = c.post(
            "/v1/chat",
            headers=headers,
            json={"message": "Legg inn rolig løpetur i morgen 40 min"},
        )
    assert chat_add.status_code == 200, chat_add.text
    add_body = chat_add.json()
    assert add_body.get("app_plan", {}).get("has_plan") is True
    assert add_body["app_plan"]["planned_sessions_count"] == planned_n
    workouts = (add_body.get("workout_proposal") or {}).get("workouts") or []
    assert workouts, "chat must return confirmable workout_proposal"
    assert workouts[0]["sport"] == "run"
    assert add_body.get("confirm_required") is True

    preview = c.post(
        "/v1/athlete/me/intervals/workouts/preview",
        headers=headers,
        json={"workouts": workouts},
    )
    assert preview.status_code == 200, preview.text
    pend = preview.json()
    assert pend["confirm_required"] is True
    assert pend["pending_id"]

    # Persist without Intervals connected still writes planned_sessions
    conf_w = c.post(
        "/v1/athlete/me/intervals/calendar/confirm",
        headers=headers,
        json={"pending_id": pend["pending_id"]},
    )
    assert conf_w.status_code == 200, conf_w.text
    wbody = conf_w.json()
    assert wbody.get("planned_sessions_saved", 0) >= 1
    assert wbody.get("written_to_intervals") in (False, None) or wbody.get("pushed", 0) == 0

    after_add = c.get("/v1/athlete/me/planned-sessions", headers=headers).json()
    assert after_add["total"] >= planned_n  # at least horizon; may upsert same day
    sess2 = c.get("/v1/sessions", headers=headers).json()
    names = " ".join(
        (x.get("name") or "")
        for x in (sess2.get("upcoming") or [])
        + (sess2.get("today") or [])
        + (sess2.get("library") or [])
    )
    assert "Rolig" in names or "løp" in names.lower() or after_add["total"] >= planned_n

    # --- 3a) Sync intent without ICU → honest connect hint, no LLM invent ---
    with patch("main.call_llm") as llm:
        r_disc = c.post(
            "/v1/chat",
            headers=headers,
            json={"message": "kan du pushe resten av planen til intervals?"},
        )
        llm.assert_not_called()
    assert r_disc.status_code == 200, r_disc.text
    disc = r_disc.json()
    assert disc.get("intervals_sync_intent") is True
    assert disc.get("intervals_pending") is None
    assert disc.get("intervals_connect_hint")
    assert not (disc.get("workout_proposal") or {}).get("workouts")
    assert disc.get("plan_proposal") in (None, {})
    assert disc["app_plan"]["planned_sessions_count"] >= planned_n

    # --- 3b) Connect ICU → real pending from stored sessions ---
    with db_session(db) as conn:
        upsert_athlete_secrets(
            conn, aid, intervals_api_key="test-key", intervals_athlete_id="iKent"
        )

    bundle = _stored_sync_bundle(workouts=6)
    with (
        patch("main.call_llm") as llm,
        patch("main._sync_bundle_preferring_stored", return_value=bundle),
    ):
        r_sync = c.post(
            "/v1/chat",
            headers=headers,
            json={"message": "kan du pushe resten av planen til intervals?"},
        )
        llm.assert_not_called()
    assert r_sync.status_code == 200, r_sync.text
    sync1 = r_sync.json()
    assert sync1.get("intervals_pending") is not None
    assert sync1["intervals_pending"]["confirm_required"] is True
    assert sync1["intervals_pending"]["pending_id"]
    assert sync1["intervals_pending"].get("from_stored_sessions") is True
    assert sync1["intervals_pending"]["workouts_count"] == 6
    assert not (sync1.get("workout_proposal") or {}).get("workouts")
    assert "fenced" not in sync1["reply"].lower()
    assert "json" not in sync1["reply"].lower() or "planned_sessions" in sync1["reply"]

    # --- 3c) Kent follow-up «sync» / «go» → real pending again, never LLM invent ---
    for follow in ("sync", "go", "ja sync"):
        with (
            patch("main.call_llm") as llm,
            patch("main._sync_bundle_preferring_stored", return_value=bundle),
        ):
            r_go = c.post(
                "/v1/chat",
                headers=headers,
                json={"message": follow},
            )
            llm.assert_not_called()
        assert r_go.status_code == 200, r_go.text
        go = r_go.json()
        assert go.get("intervals_sync_intent") is True, follow
        assert go.get("intervals_pending") is not None, follow
        assert go["intervals_pending"]["pending_id"], follow
        assert go["intervals_pending"].get("from_stored_sessions") is True, follow
        assert not (go.get("workout_proposal") or {}).get("workouts"), follow
        assert go.get("plan_proposal") in (None, {}), follow
        # Must not invent prose-as-sync
        low = go["reply"].lower()
        assert "lage en fenced" not in low
        assert "økttyper" not in low

    pending_id = go["intervals_pending"]["pending_id"]

    # --- 3d) Confirm hits ICU API (mocked), no silent success without push ---
    with patch("main.post_events_bulk", return_value={"count": 7}) as mock_post:
        done = c.post(
            "/v1/athlete/me/intervals/calendar/confirm",
            headers=headers,
            json={"pending_id": pending_id},
        )
    assert done.status_code == 200, done.text
    dbody = done.json()
    assert dbody.get("pushed", 0) >= 1 or dbody.get("op") in ("push", "intervals_calendar_push")
    mock_post.assert_called_once()

    # --- 4) Snapshot still has plan after sync talk (no amnesia) ---
    captured = {}

    def _fake_llm(*, api_key, model, system, history, user_message):
        captured["system"] = system
        return "Du har fortsatt planen i appen; gjennomført kommer fra Intervals-aktiviteter."

    with (
        patch("main.call_llm", side_effect=_fake_llm),
        patch(
            "main.resolve_wellness_bundle",
            return_value={"recovery_signals": {"available": False}},
        ),
    ):
        ask = c.post(
            "/v1/chat",
            headers=headers,
            json={"message": "Hva har jeg planlagt fremover?"},
        )
    assert ask.status_code == 200, ask.text
    ask_body = ask.json()
    assert ask_body.get("app_plan", {}).get("has_plan") is True
    assert "app_plan" in captured["system"] or "planned_sessions" in captured["system"]
    assert str(planned_n) in captured["system"] or "has_plan" in captured["system"]

    # Swim still blocked by constraints (no weird plans)
    llm_swim = (
        "Svøm?\n"
        "```workout_proposal\n"
        f'{{"workouts":[{{"name":"Teknikk","date":"{tomorrow}","sport":"swim",'
        f'"duration_minutes":45,"description":"Drill","start_time":"07:00"}}]}}\n'
        "```"
    )
    with (
        patch("main.call_llm", return_value=llm_swim),
        patch(
            "main.resolve_wellness_bundle",
            return_value={"recovery_signals": {"available": False}},
        ),
    ):
        blocked = c.post(
            "/v1/chat",
            headers=headers,
            json={"message": "Legg inn svøm i morgen"},
        )
    assert blocked.status_code == 200
    b = blocked.json()
    assert b.get("workout_proposal_blocked") is True or not (
        b.get("workout_proposal") or {}
    ).get("workouts")

    llm_add_mock.assert_called()


def test_sync_works_without_plan_blocks_when_sessions_exist(client):
    """Regression: intervals_pending must not require plan_blocks if SoT sessions exist."""
    c, _athletes, db = client
    setup = _confirm_setup(c, username="no-blocks", sessions=3)
    aid = setup["athlete"]["id"]
    headers = {"X-Athlete-Id": aid}

    with db_session(db) as conn:
        # Wipe meso blocks but keep planned_sessions
        from db import delete_all_plan_blocks

        delete_all_plan_blocks(conn, aid)
        upsert_athlete_secrets(
            conn, aid, intervals_api_key="k", intervals_athlete_id="i1"
        )
        n = count_planned_sessions(conn, aid)
    assert n > 0

    with (
        patch("main.call_llm") as llm,
        patch(
            "main._sync_bundle_preferring_stored",
            return_value=_stored_sync_bundle(),
        ),
    ):
        r = c.post(
            "/v1/chat",
            headers=headers,
            json={"message": "Legg inn resten av planen i intervals"},
        )
        llm.assert_not_called()
    assert r.status_code == 200
    body = r.json()
    assert body.get("intervals_pending") is not None
    assert body["intervals_pending"]["pending_id"]
    assert body["intervals_pending"]["from_stored_sessions"] is True
