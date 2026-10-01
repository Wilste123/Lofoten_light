"""Commercial athletes must not inherit William / Lofoten Half Extreme defaults.

Regression for: generic «komme i form» + 2×/uke without discipline asked →
must NOT get triathlete CORE_PLAN, ole-grenser, periodisering-mot-2027,
or a 7-session swim+bike+run week.
"""

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
from athlete_constraints import resolve_constraints
from athlete_type import infer_athlete_type
from db import init_db
from knowledge_ctx import (
    detect_athlete_signals,
    is_william_seed_or_lofoten_goal,
    select_knowledge_paths,
)
from plan_workouts import build_plan_week_icu_events, build_plan_sync_bundle
from setup_plan import build_setup_chat_system, build_setup_preview


REPO = Path(__file__).resolve().parents[3]
KDIR = REPO / "knowledge"

GENERIC_BLOB = "Jeg vil komme i form, 2 økter i uka"
GENERIC_DRAFT = {
    "display_name": "Ada",
    "username": "ada-comercial",
    "goal_text": "komme i form",
    "sessions_per_week": 2,
    "schedule_notes": "2 økter i uka",
    "background_notes": "nybegynner",
}


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
        yield c, athletes


def test_generic_signals_not_multisport_or_william():
    signals = detect_athlete_signals(GENERIC_BLOB, GENERIC_DRAFT)
    assert signals["multisport"] is False
    assert signals["william_seed"] is False
    assert signals["time_constrained"] is True
    assert signals["beginner"] is True
    assert is_william_seed_or_lofoten_goal(GENERIC_DRAFT, blob=GENERIC_BLOB) is False


def test_generic_infer_type_is_general_not_triathlete():
    signals = detect_athlete_signals(GENERIC_BLOB, GENERIC_DRAFT)
    info = infer_athlete_type(GENERIC_BLOB, GENERIC_DRAFT, signals=signals)
    assert info["athlete_type"] == "general_endurance"
    assert info["is_multisport"] is False


def test_generic_knowledge_excludes_william_lofoten_core():
    paths = select_knowledge_paths(
        mode="plan",
        query_text=GENERIC_BLOB,
        draft={**GENERIC_DRAFT, "athlete_type": "general_endurance"},
    )
    forbidden = (
        "triathlon/periodisering-mot-2027.md",
        "coach/ukemaler.md",
        "coach/ole-grenser.md",
        "coach/coach-filosofi.md",
        "coach/treneridentitet.md",
        "triathlon/lofoten-half-extreme.md",
    )
    for p in forbidden:
        assert p not in paths, f"commercial plan must not inject {p}"
    assert "coach/maalrealisme.md" in paths
    assert (
        "coach/ukeplaner-generell-utholdenhet.md" in paths
        or "lop/ukeplaner-lav-frekvens.md" in paths
    )
    # No Half Extreme / Lofoten race name in selected path list
    joined = " ".join(paths).lower()
    assert "half extreme" not in joined
    assert "lofoten-half" not in joined
    assert "periodisering-mot-2027" not in joined


def test_setup_chat_system_asks_discipline_not_lofoten():
    system, meta = build_setup_chat_system(
        GENERIC_DRAFT,
        knowledge_dir=KDIR,
        history_blob=GENERIC_BLOB,
    )
    low = system.lower()
    assert "hovedidrett" in low or "disiplin" in low
    assert "ikke anta lofoten" in low or "half extreme" in low
    assert "sessions_per_week" in system
    paths = meta.get("paths") or []
    assert "coach/ole-grenser.md" not in paths
    assert "triathlon/periodisering-mot-2027.md" not in paths
    assert "coach/maalrealisme.md" in paths


def test_preview_generic_2x_no_tri_archetype_or_william_knowledge():
    prev = build_setup_preview(
        GENERIC_DRAFT,
        knowledge_dir=KDIR,
        api_key="",
        enrich=False,
        today=date(2026, 9, 28),
    )
    assert prev["athlete_type"] == "general_endurance"
    assert prev["sessions_per_week"] == 2
    discs = prev["allowed_disciplines"]
    assert "swim" not in discs
    assert "bike" not in discs
    assert "run" in discs
    paths = (prev.get("knowledge") or {}).get("paths") or []
    assert "triathlon/periodisering-mot-2027.md" not in paths
    assert "coach/ole-grenser.md" not in paths
    overview = (prev.get("overview_md") or "").lower()
    assert "half extreme" not in overview
    assert "lofoten" not in overview


def test_generic_2x_workouts_honor_sessions_not_full_tri_week():
    """2 økter/uke × 2 uker → ~4 WORKOUTs, no swim+bike+run daily pack."""
    athlete = {
        **GENERIC_DRAFT,
        "athlete_type": "general_endurance",
        "allowed_disciplines": ["run", "strength"],
    }
    c = resolve_constraints(athlete, athlete_type="general_endurance")
    assert c["sessions_per_week"] == 2
    assert c["allowed_disciplines"] == ["run", "strength"]

    blocks = [
        {
            "id": "b1",
            "title": "Base",
            "theme": "komme i form",
            "start_date": "2026-09-28",
            "end_date": "2026-11-01",
            "weekly_hours": 3,
        }
    ]
    events = build_plan_week_icu_events(
        blocks,
        athlete=athlete,
        weeks=2,
        today=date(2026, 9, 28),
        signals={"beginner": True, "time_constrained": True, "multisport": False},
    )
    workouts = [e for e in events if e.get("category") == "WORKOUT"]
    assert len(workouts) == 4, f"expected 4 WORKOUTs (2×2), got {len(workouts)}"
    sports = {str(e.get("type") or e.get("sport") or "").lower() for e in workouts}
    assert "swim" not in sports
    assert not any("svøm" in str(e.get("name") or "").lower() for e in workouts)

    bundle = build_plan_sync_bundle(
        [
            {
                "id": "b1",
                "title": "Base",
                "theme": "komme i form",
                "start_date": "2026-09-28",
                "end_date": "2026-11-01",
                "weekly_hours": 3,
            }
        ],
        athlete=athlete,
        weeks=2,
        today=date(2026, 9, 28),
    )
    assert bundle["workouts_count"] == 4
    kpaths = bundle.get("knowledge_paths") or []
    assert "triathlon/periodisering-mot-2027.md" not in kpaths
    assert "coach/ukemaler.md" not in kpaths


def test_william_seed_still_gets_lofoten_core(client):
    from seed_from_repo import SEED_ATHLETE_ID, seed_athlete

    c, athletes = client
    fixtures = Path(__file__).resolve().parent / "fixtures"
    seed = seed_athlete(
        repo_root=REPO,
        athlete_docs=fixtures / "athlete_docs",
        plans_dir=fixtures / "plans",
        db_path=config.DATABASE_PATH,
        athletes_dir=athletes,
    )
    assert seed["athlete_id"] == SEED_ATHLETE_ID

    draft = {
        "username": "william",
        "id": SEED_ATHLETE_ID,
        "goal_text": "Lofoten Half Extreme 2027",
        "athlete_type": "triathlete",
    }
    assert is_william_seed_or_lofoten_goal(draft) is True
    paths = select_knowledge_paths(
        mode="plan",
        query_text="Lofoten Half Extreme comeback",
        draft=draft,
    )
    assert "coach/ole-grenser.md" in paths
    assert "coach/coach-filosofi.md" in paths
    assert "triathlon/periodisering-mot-2027.md" in paths
    assert "coach/ukemaler.md" in paths

    login = c.post("/v1/session/login", json={"username": "william"})
    assert login.status_code == 200
    body = login.json()
    assert body["needs_setup"] is False
    assert "Lofoten" in (body["athlete"].get("goal_text") or "")
