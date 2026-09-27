"""Tests for seed_from_repo — fixture athlete docs → SQLite + profile.md."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chat_service import build_system_prompt
from db import db_session, get_athlete, init_db, list_plan_blocks
from profile import load_profile_md
from seed_from_repo import SEED_ATHLETE_ID, seed_athlete

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ATHLETE_DOCS = FIXTURES / "athlete_docs"
PLANS = FIXTURES / "plans"
REPO_ROOT = Path(__file__).resolve().parents[3]  # lofoten_light


def test_dry_run_parses_fixture_without_writing(tmp_path: Path):
    result = seed_athlete(
        repo_root=REPO_ROOT,
        athlete_docs=ATHLETE_DOCS,
        plans_dir=PLANS,
        db_path=tmp_path / "unused.db",
        athletes_dir=tmp_path / "athletes",
        dry_run=True,
    )
    assert result["dry_run"] is True
    assert result["ftp_tested"] == 210.0
    assert result["agreements_count"] >= 1
    assert result["plan_blocks"] == 11
    assert result["goal_race_date"] == "2027-08-20"
    assert not (tmp_path / "athletes").exists() or not any(
        (tmp_path / "athletes").rglob("profile.md")
    )


def test_seed_populates_sqlite_and_profile(tmp_path: Path):
    db = tmp_path / "coach.db"
    athletes = tmp_path / "athletes"
    result = seed_athlete(
        repo_root=REPO_ROOT,
        athlete_docs=ATHLETE_DOCS,
        plans_dir=PLANS,
        db_path=db,
        athletes_dir=athletes,
        display_name="William",
        coach_name="Ole",
        seed_id=SEED_ATHLETE_ID,
    )
    assert result["athlete_id"] == SEED_ATHLETE_ID
    assert result["created"] is True

    with db_session(db) as conn:
        athlete = get_athlete(conn, SEED_ATHLETE_ID)
        blocks = list_plan_blocks(conn, SEED_ATHLETE_ID)

    assert athlete is not None
    assert athlete["display_name"] == "William"
    assert athlete["username"] == "william"
    assert athlete["coach_display_name"] == "Ole"
    assert athlete["setup_completed"] is True
    assert athlete["ftp_tested"] == 210.0
    assert athlete["goal_race_date"] == "2027-08-20"
    assert athlete["season_bike_hours_target"] and athlete["season_bike_hours_target"] > 300
    assert any("410" in a or "FTP" in a for a in athlete["agreements"])
    assert "isjas" in (athlete["injury_notes"] or "").lower() or "Rygg" in (
        athlete["injury_notes"] or ""
    )
    assert "Lofoten" in (athlete["goal_text"] or "")
    assert len(blocks) == 11
    assert blocks[0]["start_date"] == "2026-09-28"

    profile_path = athletes / SEED_ATHLETE_ID / "profile.md"
    assert profile_path.is_file()
    text = profile_path.read_text(encoding="utf-8")
    assert "Avtaler" in text
    assert "210" in text
    assert "isjas" in text.lower() or "Rygg" in text

    # Idempotent re-run updates same id
    result2 = seed_athlete(
        repo_root=REPO_ROOT,
        athlete_docs=ATHLETE_DOCS,
        plans_dir=PLANS,
        db_path=db,
        athletes_dir=athletes,
    )
    assert result2["athlete_id"] == SEED_ATHLETE_ID
    assert result2["created"] is False
    assert result2.get("preserved") is True
    with db_session(db) as conn:
        assert len(list_plan_blocks(conn, SEED_ATHLETE_ID)) == 11


def test_reseed_preserves_custom_goals_blocks_and_secrets(tmp_path: Path):
    """Boot re-seed must not wipe a completed William profile or Intervals secrets."""
    from db import get_athlete_secrets, upsert_athlete_secrets, update_athlete

    db = tmp_path / "coach.db"
    athletes = tmp_path / "athletes"
    seed_athlete(
        repo_root=REPO_ROOT,
        athlete_docs=ATHLETE_DOCS,
        plans_dir=PLANS,
        db_path=db,
        athletes_dir=athletes,
    )
    custom_goal = "CUSTOM: ikke overskriv ved re-seed"
    custom_profile = "# Custom runtime profile\n\nBehold meg.\n"
    (athletes / SEED_ATHLETE_ID / "profile.md").write_text(
        custom_profile, encoding="utf-8"
    )

    with db_session(db) as conn:
        update_athlete(
            conn,
            SEED_ATHLETE_ID,
            {"goal_text": custom_goal, "setup_completed": True},
        )
        upsert_athlete_secrets(
            conn,
            SEED_ATHLETE_ID,
            intervals_api_key="icu-secret-key",
            intervals_athlete_id="i12345",
        )
        # Drop one plan block to prove re-seed does not restore B0–B10
        blocks_before = list_plan_blocks(conn, SEED_ATHLETE_ID)
        assert len(blocks_before) == 11
        conn.execute(
            "DELETE FROM plan_blocks WHERE id = ?",
            (f"{SEED_ATHLETE_ID}-b10",),
        )

    result = seed_athlete(
        repo_root=REPO_ROOT,
        athlete_docs=ATHLETE_DOCS,
        plans_dir=PLANS,
        db_path=db,
        athletes_dir=athletes,
    )
    assert result["preserved"] is True
    assert result["created"] is False
    assert result["setup_completed"] is True

    with db_session(db) as conn:
        athlete = get_athlete(conn, SEED_ATHLETE_ID)
        blocks = list_plan_blocks(conn, SEED_ATHLETE_ID)
        secrets = get_athlete_secrets(conn, SEED_ATHLETE_ID)

    assert athlete["goal_text"] == custom_goal
    assert athlete["setup_completed"] is True
    assert len(blocks) == 10  # b10 still missing — not re-upserted
    assert secrets is not None
    assert secrets["intervals_api_key"] == "icu-secret-key"
    assert secrets["intervals_athlete_id"] == "i12345"
    assert (athletes / SEED_ATHLETE_ID / "profile.md").read_text(
        encoding="utf-8"
    ) == custom_profile


def test_chat_system_prompt_loads_seeded_profile(tmp_path: Path):
    db = tmp_path / "coach.db"
    athletes = tmp_path / "athletes"
    seed_athlete(
        repo_root=REPO_ROOT,
        athlete_docs=ATHLETE_DOCS,
        plans_dir=PLANS,
        db_path=db,
        athletes_dir=athletes,
    )
    init_db(db)
    with db_session(db) as conn:
        athlete = get_athlete(conn, SEED_ATHLETE_ID)
    assert athlete
    loaded = load_profile_md(athletes, athlete)
    assert "Svøm 3×/uke" in loaded or "Avtaler" in loaded
    prompt = build_system_prompt(
        athlete,
        REPO_ROOT / "knowledge",
        overview_stub={"weekly_focus": athlete.get("weekly_focus")},
        athletes_dir=athletes,
    )
    assert "Avtaler" in prompt
    assert athlete["display_name"] in prompt
