"""Athlete type inference, mutable updates, half-marathon ≠ triathlon pack."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import config
import main as main_mod
from athlete_type import (
    TYPE_HALF_MARATHON,
    TYPE_GENERAL,
    TYPE_RUNNER,
    infer_athlete_type,
    propose_type_update,
)
from db import db_session, get_athlete, init_db, upsert_athlete_secrets
from plan_workouts import build_plan_week_rows, format_exc_nb
from setup_plan import build_setup_preview


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


def test_infer_half_marathon_not_triathlon():
    info = infer_athlete_type(
        "",
        {"goal_text": "Halvmaraton i juni", "schedule_notes": "6 timer i uka"},
    )
    assert info["athlete_type"] == TYPE_HALF_MARATHON
    assert info["split"]["run"] >= 0.7
    assert info["split"]["swim"] == 0.0


def test_format_exc_nb_keyerror_not_bare_2():
    msg = format_exc_nb(KeyError(2))
    assert "2" in msg
    assert "KeyError" in msg
    assert msg != "2"


def test_preview_half_marathon_season_split(tmp_path):
    prev = build_setup_preview(
        {
            "display_name": "Ada",
            "goal_text": "Halvmaraton om 6 måneder",
            "schedule_notes": "6 timer i uka",
            "background_notes": "løper",
            "weekly_hours_target": 6,
        },
        knowledge_dir=config.KNOWLEDGE_DIR,
        api_key="",
        enrich=False,
        today=date(2026, 9, 28),
    )
    assert prev["athlete_type"] == TYPE_HALF_MARATHON
    assert "halvmaraton" in prev["athlete_archetype"]
    targets = prev["season_targets"]
    assert targets["season_run_hours_target"] > targets["season_bike_hours_target"]
    assert targets["season_swim_hours_target"] == 0
    # Not the old triathlon pack ~37/116/69
    assert targets["season_bike_hours_target"] < 50


def test_run_templates_have_no_swim(client):
    blocks = [
        {
            "id": "b1",
            "title": "Base",
            "theme": "Aerob",
            "phase": "base",
            "start_date": "2026-09-28",
            "end_date": "2026-11-01",
            "weekly_hours": 6,
        }
    ]
    _week0, rows = build_plan_week_rows(
        blocks,
        signals={},
        weeks=1,
        today=date(2026, 9, 27),
        athlete={"athlete_type": TYPE_HALF_MARATHON, "goal_text": "HM"},
    )
    sports = {r["sport"].lower() for r in rows}
    assert "swim" not in sports
    assert "run" in sports


def test_confirm_survives_builder_failure_with_prepare(client):
    c, _athletes, db = client
    draft = {
        "display_name": "Ada",
        "username": "ada-hm",
        "coach_display_name": "Rocky",
        "goal_text": "Halvmaraton",
        "schedule_notes": "6 t/uke",
        "enrich_with_llm": False,
        "intervals_athlete_id": "i1",
        "intervals_api_key": "k1",
    }
    prev = c.post("/v1/setup/plan/preview", json=draft)
    assert prev.status_code == 200, prev.text
    pdata = prev.json()

    with patch(
        "main.build_plan_sync_bundle",
        side_effect=KeyError(2),
    ):
        conf = c.post(
            "/v1/setup/confirm",
            json={
                **draft,
                "plan_blocks": pdata["plan_blocks"],
                "athlete_patch": pdata["athlete_patch"],
                "prepare_intervals_sync": True,
            },
        )
    assert conf.status_code == 200, conf.text
    body = conf.json()
    assert body["athlete"]["setup_completed"] is True
    assert body["athlete"]["athlete_type"] == TYPE_HALF_MARATHON
    assert body["intervals_pending"] is None
    assert body["intervals_prep_error"]
    assert "KeyError" in body["intervals_prep_error"]


def test_mutable_type_update_endpoint(client):
    c, _a, db = client
    onboard = c.post(
        "/v1/onboarding",
        json={
            "display_name": "Bo",
            "username": "bo-run",
            "coach_display_name": "Rocky",
            "goal_text": "Komme i gang",
        },
    )
    assert onboard.status_code == 200
    aid = onboard.json()["athlete"]["id"]
    headers = {"X-Athlete-Id": aid}

    with db_session(db) as conn:
        from db import update_athlete

        update_athlete(
            conn,
            aid,
            {"athlete_type": TYPE_GENERAL, "setup_completed": True},
        )

    r = c.post(
        "/v1/athlete/me/athlete-type",
        headers=headers,
        json={
            "athlete_type": "runner",
            "reason": "mål skiftet til løping",
            "rebuild_plan_preview": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["to"] == TYPE_RUNNER
    assert data["athlete"]["athlete_type"] == TYPE_RUNNER
    assert "→" in (data["athlete"].get("athlete_type_notes") or "")
    assert data["plan_preview"] is not None

    # Propose further HM
    prop = propose_type_update(
        data["athlete"],
        suggested="half_marathon_runner",
    )
    assert prop is not None
    assert prop["to"] == TYPE_HALF_MARATHON
    assert prop["confirm_required"] is True


def test_reset_requires_icu_ack(client):
    c, _a, db = client
    onboard = c.post(
        "/v1/onboarding",
        json={
            "display_name": "Co",
            "username": "co-reset",
            "coach_display_name": "Rocky",
        },
    )
    aid = onboard.json()["athlete"]["id"]
    headers = {"X-Athlete-Id": aid}
    with db_session(db) as conn:
        from db import update_athlete

        update_athlete(conn, aid, {"setup_completed": True})
        upsert_athlete_secrets(conn, aid, intervals_api_key="k", intervals_athlete_id="i1")

    bad = c.post(
        "/v1/athlete/me/setup/reset",
        headers=headers,
        json={
            "acknowledge_wipe": True,
            "confirm_phrase": "SLETT",
            "delete_intervals_coach_events": True,
            "acknowledge_intervals_delete": False,
        },
    )
    assert bad.status_code == 400

    with patch("main.fetch_events", return_value=[]), patch(
        "main.delete_events_bulk"
    ) as mock_del:
        ok = c.post(
            "/v1/athlete/me/setup/reset",
            headers=headers,
            json={
                "acknowledge_wipe": True,
                "confirm_phrase": "SLETT",
                "delete_intervals_coach_events": True,
                "acknowledge_intervals_delete": True,
            },
        )
    assert ok.status_code == 200, ok.text
    assert ok.json()["athlete"]["setup_completed"] is False
    mock_del.assert_not_called()  # no matching events


def test_workout_remove_preview_scoped(client):
    c, _a, db = client
    onboard = c.post(
        "/v1/onboarding",
        json={
            "display_name": "Di",
            "username": "di-rm",
            "coach_display_name": "Rocky",
        },
    )
    aid = onboard.json()["athlete"]["id"]
    headers = {"X-Athlete-Id": aid}
    with db_session(db) as conn:
        upsert_athlete_secrets(conn, aid, intervals_api_key="k", intervals_athlete_id="i9")

    events = [
        {
            "external_id": "ll-coach-w-20261001-easy-0",
            "name": "Løp easy",
            "start_date_local": "2026-10-01T07:00:00",
            "category": "WORKOUT",
        },
        {
            "external_id": "other-user-event",
            "name": "Mine egne",
            "start_date_local": "2026-10-01T08:00:00",
            "category": "WORKOUT",
        },
    ]
    with patch("main.fetch_events", return_value=events):
        prev = c.post(
            "/v1/athlete/me/intervals/workouts/remove/preview",
            headers=headers,
            json={"dates": ["2026-10-01"]},
        )
    assert prev.status_code == 200, prev.text
    body = prev.json()
    assert body["op"] == "delete"
    assert body["confirm_required"] is True
    assert body["count"] == 1
    assert body["events"][0]["external_id"].startswith("ll-coach-")
