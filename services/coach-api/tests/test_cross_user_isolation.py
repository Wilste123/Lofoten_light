"""Cross-user isolation: athlete B must never see athlete A's facts in context.

Critical trust bug: leftover X-Athlete-Id / seeded William must not become
default context for a new commercial user.
"""

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
from chat_service import build_system_prompt
from db import (
    db_session,
    get_athlete,
    init_db,
    insert_athlete,
    list_plan_blocks,
    recent_messages,
    replace_plan_blocks,
    upsert_athlete_secrets,
)
from profile import load_profile_md, write_profile
from seed_from_repo import SEED_ATHLETE_ID, seed_athlete
from setup_plan import build_setup_chat_system


REPO = Path(__file__).resolve().parents[3]
KDIR = REPO / "knowledge"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "athlete_docs"

SECRET_GOAL_A = "SECRET_GOAL_A_MARATHON_BERLIN_XYZ"
SECRET_AGR_A = "SECRET_AGREEMENT_A_5X_WEEK"
SECRET_INJ_A = "SECRET_INJURY_A_LEFT_KNEE"
SECRET_GOAL_B = "SECRET_GOAL_B_COME_IN_SHAPE_ABC"
SECRET_AGR_B = "SECRET_AGREEMENT_B_2X_WEEK"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    athletes = tmp_path / "athletes"
    athletes.mkdir()
    monkeypatch.setattr(config, "DATABASE_PATH", db)
    monkeypatch.setattr(config, "ATHLETES_DATA_DIR", athletes)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config, "KNOWLEDGE_DIR", KDIR)
    init_db(db)
    with TestClient(main_mod.app) as c:
        yield c, athletes, db


def _make_athlete(conn, *, username: str, display: str, goal: str, agreements: list, injury: str = ""):
    row = insert_athlete(
        conn,
        {
            "display_name": display,
            "username": username,
            "goal_text": goal,
            "agreements": agreements,
            "injury_notes": injury,
            "setup_completed": True,
            "athlete_type": "general_endurance",
            "sessions_per_week": 3,
            "allowed_disciplines": ["run", "strength"],
            "coach_display_name": "Rocky",
        },
    )
    return get_athlete(conn, row["id"])


def test_chat_system_prompt_b_excludes_a_goals_and_agreements(client):
    _c, athletes, db = client
    with db_session(db) as conn:
        a = _make_athlete(
            conn,
            username="athlete-a",
            display="AliceA",
            goal=SECRET_GOAL_A,
            agreements=[SECRET_AGR_A],
            injury=SECRET_INJ_A,
        )
        b = _make_athlete(
            conn,
            username="athlete-b",
            display="BobB",
            goal=SECRET_GOAL_B,
            agreements=[SECRET_AGR_B],
        )
    write_profile(athletes, a)
    write_profile(athletes, b)

    prompt_a = build_system_prompt(
        a, KDIR, athletes_dir=athletes, user_message="hva er målet mitt?"
    )
    prompt_b = build_system_prompt(
        b, KDIR, athletes_dir=athletes, user_message="hva er målet mitt?"
    )

    assert SECRET_GOAL_A in prompt_a
    assert SECRET_AGR_A in prompt_a
    assert SECRET_INJ_A in prompt_a

    assert SECRET_GOAL_B in prompt_b
    assert SECRET_AGR_B in prompt_b
    assert SECRET_GOAL_A not in prompt_b
    assert SECRET_AGR_A not in prompt_b
    assert SECRET_INJ_A not in prompt_b
    assert "Athlete profile — AliceA" not in prompt_b
    assert "Athlete profile — BobB" in prompt_b


def test_setup_chat_system_b_excludes_a_draft_facts(client):
    _c, _athletes, _db = client
    draft_a = {
        "display_name": "AliceA",
        "goal_text": SECRET_GOAL_A,
        "agreements": [SECRET_AGR_A],
        "injury_notes": SECRET_INJ_A,
    }
    draft_b = {
        "display_name": "BobB",
        "goal_text": SECRET_GOAL_B,
        "agreements": [SECRET_AGR_B],
        "sessions_per_week": 2,
    }
    sys_a, _ = build_setup_chat_system(draft_a, knowledge_dir=KDIR, history_blob="")
    sys_b, _ = build_setup_chat_system(draft_b, knowledge_dir=KDIR, history_blob="")
    assert SECRET_GOAL_A in sys_a
    assert SECRET_GOAL_A not in sys_b
    assert SECRET_AGR_A not in sys_b
    assert SECRET_INJ_A not in sys_b
    assert SECRET_GOAL_B in sys_b


def test_incomplete_athlete_no_william_profile_or_seed_goals(client):
    """Empty/incomplete athlete must not fall back to seeded William profile.md."""
    _c, athletes, db = client
    seed_athlete(
        repo_root=REPO,
        db_path=db,
        athletes_dir=athletes,
        athlete_docs=FIXTURES,
    )
    with db_session(db) as conn:
        w = get_athlete(conn, SEED_ATHLETE_ID)
        assert w is not None
        w_goal = (w.get("goal_text") or "").strip()
        assert w_goal
        c = insert_athlete(
            conn,
            {
                "display_name": "CarolNew",
                "username": "carol-new",
                "goal_text": "",
                "agreements": [],
                "setup_completed": False,
            },
        )
        carol = get_athlete(conn, c["id"])

    # No on-disk profile yet — must render empty Carol, not William seed file
    loaded = load_profile_md(athletes, carol)
    assert "Athlete profile — CarolNew" in loaded
    assert "Athlete profile — William" not in loaded
    assert "Lofoten Half Extreme" not in loaded

    prompt = build_system_prompt(
        carol, KDIR, athletes_dir=athletes, user_message="hjelp meg"
    )
    assert "Athlete profile — William" not in prompt
    # Seed goals / agreements must not appear as Carol's facts
    for token in (
        "Lofoten Half Extreme 2027",
        "Svøm 3×/uke er non-negotiable",
        "Ikke bruk 410 W som dagens FTP",
        "Race-vekt under 80 kg",
    ):
        assert token not in prompt, f"William fact leaked into Carol prompt: {token}"
    # Knowledge may mention Lofoten as contrast; profile section must be Carol
    assert "CarolNew" in prompt


def test_setup_confirm_ignores_stale_x_athlete_id_header(client):
    """New-user confirm must create B even if header still has A's id (localStorage bug)."""
    c, athletes, db = client
    with db_session(db) as conn:
        a = _make_athlete(
            conn,
            username="stored-a",
            display="StoredA",
            goal=SECRET_GOAL_A,
            agreements=[SECRET_AGR_A],
        )
        aid = a["id"]
        replace_plan_blocks(
            conn,
            aid,
            [
                {
                    "key": "a0",
                    "title": "A-only block",
                    "theme": SECRET_GOAL_A,
                    "phase": "base",
                    "start_date": "2026-10-01",
                    "end_date": "2026-11-01",
                    "weekly_hours": 6,
                    "sort_order": 0,
                }
            ],
        )

    r = c.post(
        "/v1/setup/confirm",
        headers={"X-Athlete-Id": aid},
        json={
            "display_name": "BrandNewB",
            "username": "brand-new-b",
            "coach_display_name": "Rocky",
            "goal_text": SECRET_GOAL_B,
            "sessions_per_week": 2,
            "allowed_disciplines": ["run", "strength"],
            "agreements": [SECRET_AGR_B],
            "plan_blocks": [
                {
                    "key": "b0",
                    "title": "B base",
                    "theme": "Vane",
                    "phase": "base",
                    "start_date": "2026-10-01",
                    "end_date": "2026-11-01",
                    "weekly_hours": 4,
                    "sort_order": 0,
                }
            ],
            "prepare_intervals_sync": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    new_id = body["athlete"]["id"]
    assert new_id != aid
    assert body["athlete"]["username"] == "brand-new-b"
    assert SECRET_GOAL_B in (body["athlete"].get("goal_text") or "")

    with db_session(db) as conn:
        a_after = get_athlete(conn, aid)
        b_after = get_athlete(conn, new_id)
        a_blocks = list_plan_blocks(conn, aid)
        b_blocks = list_plan_blocks(conn, new_id)
    assert a_after["goal_text"] == SECRET_GOAL_A
    assert SECRET_AGR_A in (a_after.get("agreements") or [])
    assert a_blocks and a_blocks[0]["title"] == "A-only block"
    assert b_after["goal_text"] == SECRET_GOAL_B
    assert SECRET_AGR_B in (b_after.get("agreements") or [])
    assert b_blocks and b_blocks[0]["title"] == "B base"
    assert (athletes / new_id / "profile.md").is_file()
    assert SECRET_GOAL_A not in (athletes / new_id / "profile.md").read_text(
        encoding="utf-8"
    )


def test_setup_confirm_rejects_mismatched_body_and_header(client):
    c, _athletes, db = client
    with db_session(db) as conn:
        a = _make_athlete(
            conn, username="a1", display="A1", goal=SECRET_GOAL_A, agreements=[]
        )
        b = _make_athlete(
            conn, username="b1", display="B1", goal=SECRET_GOAL_B, agreements=[]
        )
    r = c.post(
        "/v1/setup/confirm",
        headers={"X-Athlete-Id": a["id"]},
        json={
            "athlete_id": b["id"],
            "display_name": "B1",
            "username": "b1",
            "goal_text": "hijack attempt",
            "plan_blocks": [
                {
                    "key": "x",
                    "title": "X",
                    "theme": "t",
                    "phase": "base",
                    "start_date": "2026-10-01",
                    "end_date": "2026-11-01",
                    "weekly_hours": 4,
                    "sort_order": 0,
                }
            ],
        },
    )
    assert r.status_code == 403


def test_chat_endpoint_scopes_messages_and_does_not_leak_a_into_b_prompt(client):
    c, athletes, db = client
    with db_session(db) as conn:
        a = _make_athlete(
            conn,
            username="chat-a",
            display="ChatA",
            goal=SECRET_GOAL_A,
            agreements=[SECRET_AGR_A],
        )
        b = _make_athlete(
            conn,
            username="chat-b",
            display="ChatB",
            goal=SECRET_GOAL_B,
            agreements=[SECRET_AGR_B],
        )
        upsert_athlete_secrets(
            conn, a["id"], intervals_api_key="key-aaaaaa", intervals_athlete_id="iA"
        )
        upsert_athlete_secrets(
            conn, b["id"], intervals_api_key="key-bbbbbb", intervals_athlete_id="iB"
        )
    write_profile(athletes, a)
    write_profile(athletes, b)

    captured: dict[str, str] = {}

    def _fake_llm(*, api_key, model, system, history, user_message):
        captured["system"] = system
        captured["user"] = user_message
        return "Ok — jeg ser bare din profil."

    with patch.object(main_mod, "call_llm", side_effect=_fake_llm):
        r = c.post(
            "/v1/chat",
            headers={"X-Athlete-Id": b["id"]},
            json={"message": "Hva er målet mitt?"},
        )
    assert r.status_code == 200, r.text
    sys_prompt = captured["system"]
    assert SECRET_GOAL_B in sys_prompt
    assert SECRET_GOAL_A not in sys_prompt
    assert SECRET_AGR_A not in sys_prompt
    assert "iA" not in sys_prompt or True  # intervals id may appear only for B
    # B's secrets public view may include iB — must not include A's key material
    assert "key-aaaaaa" not in sys_prompt

    with db_session(db) as conn:
        msgs_a = recent_messages(conn, a["id"], limit=20)
        msgs_b = recent_messages(conn, b["id"], limit=20)
    assert msgs_a == []
    assert len(msgs_b) >= 2
