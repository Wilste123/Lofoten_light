"""Align onboarding: goal year, no false re-etablering, persist Du fields, preview===sync."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import config
import main as main_mod
from db import db_session, get_athlete, init_db
from knowledge_ctx import detect_athlete_signals
from plan_workouts import build_plan_sync_bundle, events_preview_for_plan_sync
from setup_plan import (
    build_setup_preview,
    compose_goal_text,
    default_season_window,
    infer_goal_race_date,
    merge_confirm_athlete_patch,
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
        yield c, athletes


def test_goal_year_2028_sets_season_end_in_2028():
    today = date(2026, 9, 28)
    inferred = infer_goal_race_date(goal_text="Triatlon 2028", today=today)
    assert inferred is not None
    assert inferred.year == 2028
    start, race = default_season_window(
        today=today,
        goal_text="triatlon 2028",
        signals={},
    )
    assert race.year == 2028
    # Must not invent ~May 2027 (32 weeks from Sep 2026)
    assert race != date(2027, 5, 10)
    assert (race - start).days > 400


def test_trained_4x_week_no_reetablering_title():
    kdir = config.KNOWLEDGE_DIR
    prev = build_setup_preview(
        {
            "display_name": "Will",
            "goal_text": "Triatlon 2028",
            "background_notes": "Form er OK, trener allerede 4 økter i uka",
            "schedule_notes": "4 økter/uke",
            "sessions_per_week": 4,
            "fitness_notes": "Form OK — trener allerede",
            "athlete_type": "triathlete",
        },
        knowledge_dir=kdir,
        api_key="",
        enrich=False,
        today=date(2026, 9, 28),
    )
    assert prev["signals"].get("fitness_ok") is True
    assert prev["signals"].get("returning") is False
    titles = " ".join(b["title"] for b in prev["plan_blocks"]).lower()
    assert "re-etablering" not in titles
    assert prev["goal_race_date"].startswith("2028")
    assert prev["athlete_patch"]["goal_text"]
    assert prev["athlete_patch"]["agreements"]
    assert prev["athlete_patch"]["sessions_per_week"] == 4


def test_compose_goal_from_conversation_cues():
    assert "2028" in compose_goal_text({}, text="Jeg vil gjøre triatlon i 2028")
    assert "Triatlon" in compose_goal_text({"goal_text": ""}, text="triatlon 2028")


def test_fitness_ok_not_returning_on_form_ok():
    s = detect_athlete_signals("Form er OK, trener allerede 4 ganger i uka")
    assert s["fitness_ok"] is True
    assert s["returning"] is False
    # Broad «tidligere» alone must not mark returning
    s2 = detect_athlete_signals("Jeg har tidligere tenkt på triathlon, form ok")
    assert s2["returning"] is False


def test_preview_workouts_identical_to_sync_bundle():
    athlete = {
        "athlete_type": "half_marathon_runner",
        "goal_text": "Halvmaraton",
        "allowed_disciplines": ["run", "strength"],
        "sessions_per_week": 3,
        "schedule_notes": "3 økter kun løp og styrke",
    }
    blocks = [
        {
            "id": "b1",
            "title": "Base",
            "theme": "aerob",
            "phase": "base",
            "start_date": "2026-09-28",
            "end_date": "2026-12-01",
            "weekly_hours": 5,
        }
    ]
    prev = events_preview_for_plan_sync(blocks, athlete=athlete, weeks=2)
    bundle = build_plan_sync_bundle(
        blocks, athlete=athlete, weeks=2, include_notes=True, today=date(2026, 9, 28)
    )
    assert prev["workouts_count"] == bundle["workouts_count"]
    prev_names = [(e.get("name"), e.get("start_date_local") or e.get("day")) for e in prev["workouts_preview"]]
    sync_names = [
        (e.get("name"), str(e.get("start_date_local") or "")[:10])
        for e in bundle["workout_events"]
    ]
    # Same set of workout identities (name + day)
    assert len(prev_names) == len(sync_names)
    sports = {e.get("type") or e.get("sport") for e in bundle["workout_events"]}
    assert "Swim" not in sports
    assert "Ride" not in sports


def test_confirm_persists_du_fields(client):
    c, athletes = client
    preview = c.post(
        "/v1/setup/plan/preview",
        json={
            "display_name": "Will",
            "username": "will-du",
            "goal_text": "",
            "background_notes": "Triatlon 2028, form OK, 4 økter i uka",
            "schedule_notes": "4 økter/uke",
            "sessions_per_week": 4,
            "injury_notes": "Lett knesmerte ved bakke",
            "enrich_with_llm": False,
        },
    )
    assert preview.status_code == 200, preview.text
    prev = preview.json()
    assert prev["athlete_patch"]["goal_text"]
    assert "2028" in prev["goal_race_date"]

    confirm = c.post(
        "/v1/setup/confirm",
        json={
            "display_name": "Will",
            "username": "will-du",
            "coach_display_name": "Rocky",
            "background_notes": "Triatlon 2028, form OK, 4 økter i uka",
            "schedule_notes": "4 økter/uke",
            "sessions_per_week": 4,
            "injury_notes": "Lett knesmerte ved bakke",
            "plan_blocks": prev["plan_blocks"],
            "athlete_patch": prev["athlete_patch"],
            "prepare_intervals_sync": False,
            "enrich_with_llm": False,
        },
    )
    assert confirm.status_code == 200, confirm.text
    data = confirm.json()
    ath = data["athlete"]
    assert ath["goal_text"], "Du → Mål must not be empty"
    assert "2028" in (ath["goal_race_date"] or "")
    assert ath["injury_notes"]
    assert ath["agreements"]
    assert ath["notes"] or ath["fitness_notes"]
    assert ath["weekly_focus"]
    assert ath["sessions_per_week"] == 4
    profile = (athletes / ath["id"] / "profile.md").read_text(encoding="utf-8")
    assert ath["goal_text"][:20] in profile or "Triatlon" in profile


def test_merge_confirm_fills_blank_patch():
    patch = merge_confirm_athlete_patch(
        {"goal_text": "", "weekly_focus": ""},
        {
            "goal_text": "",
            "background_notes": "triatlon 2028",
            "schedule_notes": "4 økter i uka",
            "sessions_per_week": 4,
            "injury_notes": "kne",
        },
        today=date(2026, 9, 28),
    )
    assert patch["goal_text"]
    assert patch["agreements"]
    assert patch["injury_notes"] == "kne"
    assert patch["sessions_per_week"] == 4


def test_plan_adjust_preview_confirm(client):
    c, athletes = client
    # Seed athlete via confirm
    preview = c.post(
        "/v1/setup/plan/preview",
        json={
            "display_name": "Ada",
            "username": "ada-adj",
            "goal_text": "Halvmaraton 2027",
            "schedule_notes": "3 økter kun løp og styrke",
            "sessions_per_week": 3,
            "allowed_disciplines": ["run", "strength"],
            "enrich_with_llm": False,
        },
    )
    prev = preview.json()
    conf = c.post(
        "/v1/setup/confirm",
        json={
            "display_name": "Ada",
            "username": "ada-adj",
            "goal_text": "Halvmaraton 2027",
            "schedule_notes": "3 økter kun løp og styrke",
            "sessions_per_week": 3,
            "allowed_disciplines": ["run", "strength"],
            "plan_blocks": prev["plan_blocks"],
            "athlete_patch": prev["athlete_patch"],
            "prepare_intervals_sync": False,
        },
    )
    aid = conf.json()["athlete"]["id"]
    # Update Du fields — including sessions_per_week + earlier goal
    c.patch(
        "/v1/athlete/me",
        headers={"X-Athlete-Id": aid},
        json={
            "goal_text": "Halvmaraton juni 2027 — sub 1:45",
            "injury_notes": "Achilles rolig",
            "agreements": ["Ingen terskel denne uka"],
            "notes": "Jobb-reise onsdag",
            "weekly_focus": "Lett kontinuitet",
            "sessions_per_week": 5,
            "goal_race_date": "2027-06-15",
            "allowed_disciplines": ["run"],
        },
    )
    adj = c.post(
        "/v1/athlete/me/plan/adjust/preview",
        headers={"X-Athlete-Id": aid},
        json={"enrich_with_llm": False},
    )
    assert adj.status_code == 200, adj.text
    body = adj.json()
    assert body["plan_blocks"]
    assert "seed_chat_prompt" in body
    # Must re-read saved 5/week — not stale setup «3 økter»
    assert body.get("sessions_per_week") == 5
    assert "5 økter" in (body.get("constraints_summary_nb") or "")
    assert "3 økter" not in (body.get("constraints_summary_nb") or "")
    sync = body.get("intervals_sync") or {}
    assert sync.get("workouts_count") == 10  # 5 × 2 weeks
    assert "2 uker" in (body.get("workout_horizon_note_nb") or "")
    done = c.post(
        "/v1/athlete/me/plan/adjust/confirm",
        headers={"X-Athlete-Id": aid},
        json={
            "plan_blocks": body["plan_blocks"],
            "athlete_patch": body.get("athlete_patch") or {},
            "prepare_intervals_sync": False,
        },
    )
    assert done.status_code == 200, done.text
    assert done.json()["written_to_intervals"] is False
    with db_session(config.DATABASE_PATH) as conn:
        ath = get_athlete(conn, aid)
        assert ath["sessions_per_week"] == 5
        assert "sub 1:45" in (ath["goal_text"] or "") or ath["goal_text"]
        agr = " ".join(ath.get("agreements") or [])
        assert "5 økter/uke" in agr
        assert "3 økter/uke" not in agr
