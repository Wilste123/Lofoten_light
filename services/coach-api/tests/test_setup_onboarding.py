"""Tests for adaptive knowledge-grounded setup / onboarding."""

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
from db import db_session, get_athlete, init_db, list_plan_blocks
from knowledge_ctx import detect_athlete_signals, select_knowledge_paths
from setup_plan import build_setup_preview, extract_setup_fields, normalize_plan_blocks


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


def test_signals_beginner_vs_returning():
    b = detect_athlete_signals("Jeg er helt nybegynner og har aldri trent")
    assert b["beginner"] is True
    r = detect_athlete_signals("Comeback etter pause — tidligere syklist")
    assert r["returning"] is True
    i = detect_athlete_signals("Isjas og ryggplager, rehab")
    assert i["injury"] is True


def test_knowledge_paths_diverge():
    beginner = select_knowledge_paths(
        mode="plan", query_text="nybegynner aldri trent kan ikke svømme"
    )
    returning = select_knowledge_paths(
        mode="plan", query_text="comeback etter pause tidligere elite"
    )
    injury = select_knowledge_paths(
        mode="plan", query_text="skade isjas belastning ACWR"
    )
    assert "svom/nybegynner-til-triatlet.md" in beginner
    assert "lop/oppbygging-etter-pause.md" in returning
    assert "skader/belastningsstyring-acwr.md" in injury
    assert "coach/coach-filosofi.md" in beginner
    assert "triathlon/periodisering-mot-2027.md" in beginner


def test_preview_beginner_differs_from_returning(tmp_path):
    # Use real knowledge dir from repo
    kdir = config.KNOWLEDGE_DIR
    beg = build_setup_preview(
        {
            "display_name": "Ada",
            "goal_text": "Komme i gang med jogging",
            "background_notes": "Helt nybegynner, aldri trent systematisk",
            "weekly_hours_target": 4,
        },
        knowledge_dir=kdir,
        api_key="",
        enrich=False,
        today=date(2026, 9, 28),
    )
    ret = build_setup_preview(
        {
            "display_name": "Bo",
            "goal_text": "Comeback mot halviron",
            "background_notes": "Tidligere syklist, comeback etter pause",
            "injury_notes": "",
            "weekly_hours_target": 10,
        },
        knowledge_dir=kdir,
        api_key="",
        enrich=False,
        today=date(2026, 9, 28),
    )
    assert beg["signals"]["beginner"] is True
    assert ret["signals"]["returning"] is True
    assert beg["plan_blocks"][0]["title"] != ret["plan_blocks"][0]["title"] or beg[
        "plan_blocks"
    ][0]["theme"] != ret["plan_blocks"][0]["theme"]
    assert beg["weekly_hours_target"] <= ret["weekly_hours_target"]
    assert "nybegynner" in beg["athlete_archetype"] or beg["signals"]["beginner"]


def test_setup_chat_and_preview_confirm_reset(client):
    c, athletes = client
    chat = c.post(
        "/v1/setup/chat",
        json={
            "message": "Hei — jeg er nybegynner, mål er 5k om et år, ca 4 t i uka, ingen skader.",
            "draft": {
                "display_name": "Ada",
                "username": "ada-test",
                "coach_display_name": "Rocky",
            },
            "history": [],
        },
    )
    assert chat.status_code == 200, chat.text
    body = chat.json()
    assert "reply" in body
    assert body["draft"]["display_name"] == "Ada"
    assert "knowledge" in body
    assert "paths" in body["knowledge"]

    preview = c.post(
        "/v1/setup/plan/preview",
        json={
            "display_name": "Ada",
            "username": "ada-test",
            "goal_text": "5k om et år",
            "background_notes": "nybegynner",
            "weekly_hours_target": 4,
            "enrich_with_llm": False,
        },
    )
    assert preview.status_code == 200, preview.text
    prev = preview.json()
    assert len(prev["plan_blocks"]) >= 2
    assert prev["intervals_sync"]["will_push"] is False

    confirm = c.post(
        "/v1/setup/confirm",
        json={
            "display_name": "Ada",
            "username": "ada-test",
            "coach_display_name": "Rocky",
            "goal_text": "5k om et år",
            "background_notes": "nybegynner",
            "weekly_hours_target": 4,
            "plan_blocks": prev["plan_blocks"],
            "athlete_patch": prev["athlete_patch"],
            "prepare_intervals_sync": False,
        },
    )
    assert confirm.status_code == 200, confirm.text
    data = confirm.json()
    aid = data["athlete"]["id"]
    assert data["written_to_intervals"] is False
    assert (athletes / aid / "profile.md").is_file()
    assert len(data["plan_blocks"]) >= 2

    # Seed william still works via login path
    # Reset requires double confirm
    bad = c.post(
        "/v1/athlete/me/setup/reset",
        headers={"X-Athlete-Id": aid},
        json={"acknowledge_wipe": True, "confirm_phrase": "nei"},
    )
    assert bad.status_code == 400

    ok = c.post(
        "/v1/athlete/me/setup/reset",
        headers={"X-Athlete-Id": aid},
        json={"acknowledge_wipe": True, "confirm_phrase": "SLETT"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["needs_setup"] is True
    assert ok.json()["deleted_plan_blocks"] >= 1
    with db_session(config.DATABASE_PATH) as conn:
        assert list_plan_blocks(conn, aid) == []
        ath = get_athlete(conn, aid)
        assert ath["goal_text"] == ""


def test_extract_setup_fields():
    reply = (
        "Flott — da starter vi rolig.\n\n"
        "```setup_extract\n"
        '{"ready_for_plan": true, "goal_text": "5k", "injury_notes": null, '
        '"weekly_hours_target": 4}\n'
        "```"
    )
    display, extracted = extract_setup_fields(reply)
    assert "Flott" in display
    assert "setup_extract" not in display
    assert extracted["ready_for_plan"] is True
    assert extracted["goal_text"] == "5k"
    assert "injury_notes" not in extracted
    assert extracted["weekly_hours_target"] == 4.0


def test_normalize_rejects_bad_blocks():
    blocks = normalize_plan_blocks(
        [{"title": "x"}],  # missing dates
        season_start=date(2026, 9, 28),
        goal_race=date(2027, 6, 1),
        weekly_hours=6,
        signals={"beginner": True},
    )
    assert len(blocks) >= 2
    assert blocks[0]["start_date"]
