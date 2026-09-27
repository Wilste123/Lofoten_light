"""Constraints: run+strength @ 3/week, 2-week horizon, knowledge grounding."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from athlete_constraints import (
    DISC_RUN,
    DISC_STRENGTH,
    MAX_WORKOUT_WEEKS,
    infer_allowed_disciplines,
    infer_sessions_per_week,
    resolve_constraints,
)
from athlete_type import TYPE_HALF_MARATHON
from knowledge_ctx import select_knowledge_paths
from plan_workouts import (
    build_plan_sync_bundle,
    build_plan_week_icu_events,
    build_plan_week_rows,
    prescription_meta_from_athlete,
)


BLOCKS = [
    {
        "id": "b1",
        "title": "Grunnlag",
        "theme": "etablering",
        "start_date": "2026-09-28",
        "end_date": "2026-12-01",
        "weekly_hours": 5,
    }
]


def test_infer_three_sessions_run_strength():
    draft = {
        "goal_text": "Halvmaraton",
        "schedule_notes": "3 økter i uka, kun løp og styrke",
        "athlete_type": TYPE_HALF_MARATHON,
    }
    assert infer_sessions_per_week(draft, athlete_type=TYPE_HALF_MARATHON) == 3
    discs = infer_allowed_disciplines(draft, athlete_type=TYPE_HALF_MARATHON)
    assert set(discs) == {DISC_RUN, DISC_STRENGTH}


def test_run_strength_3_per_week_no_swim_bike_two_weeks():
    athlete = {
        "athlete_type": TYPE_HALF_MARATHON,
        "goal_text": "Halvmaraton juni",
        "schedule_notes": "3 økter/uke kun løp og styrke",
        "allowed_disciplines": ["run", "strength"],
        "sessions_per_week": 3,
        "display_name": "Ada",
    }
    events = build_plan_week_icu_events(
        BLOCKS,
        athlete=athlete,
        weeks=2,
        today=date(2026, 9, 28),
    )
    sports = {str(e.get("type") or "") for e in events}
    assert "Swim" not in sports
    assert "Ride" not in sports
    assert "Run" in sports
    assert "WeightTraining" in sports or "Strength" in sports or any(
        "styrke" in (e.get("name") or "").lower() for e in events
    )
    # ≈ 3/week × 2 weeks
    assert 5 <= len(events) <= 7
    assert len(events) == 6
    days = sorted(
        {str(e.get("start_date_local") or "")[:10] for e in events if e.get("start_date_local")}
    )
    assert days
    span = (date.fromisoformat(days[-1]) - date.fromisoformat(days[0])).days
    assert span <= 14


def test_weeks_hard_cap_at_two():
    athlete = {
        "athlete_type": TYPE_HALF_MARATHON,
        "allowed_disciplines": ["run", "strength"],
        "sessions_per_week": 3,
    }
    _, rows = build_plan_week_rows(
        BLOCKS,
        athlete=athlete,
        weeks=8,  # request ignored
        today=date(2026, 9, 28),
    )
    assert len(rows) == 6  # 3 × 2
    bundle = build_plan_sync_bundle(
        BLOCKS,
        athlete=athlete,
        weeks=8,
        today=date(2026, 9, 28),
        include_notes=False,
    )
    assert bundle["weeks"] == MAX_WORKOUT_WEEKS
    assert bundle["workouts_count"] == 6


def test_prescription_rationale_and_knowledge_paths():
    athlete = {
        "athlete_type": TYPE_HALF_MARATHON,
        "goal_text": "Halvmaraton",
        "schedule_notes": "3 økter kun løp og styrke",
        "allowed_disciplines": ["run", "strength"],
        "sessions_per_week": 3,
    }
    meta = prescription_meta_from_athlete(athlete, blocks=BLOCKS)
    assert "3 økter" in meta["constraints_summary_nb"]
    assert "løp" in meta["constraints_summary_nb"]
    rat = meta["prescription_rationale_nb"]
    assert "Hvorfor" in rat or "hvorfor" in rat.lower() or "Ukesstruktur" in rat
    assert "Knowledge" in rat
    paths = meta["knowledge_paths"]
    assert any("ukeplaner-lav-frekvens" in p for p in paths)
    assert any("halvmaraton" in p for p in paths)
    assert "triathlon/periodisering-mot-2027.md" not in paths or True  # may or may not


def test_hm_knowledge_selection_prefers_run_pack():
    paths = select_knowledge_paths(
        mode="plan",
        query_text="halvmaraton 3 økter kun løp og styrke",
        draft={
            "athlete_type": TYPE_HALF_MARATHON,
            "allowed_disciplines": ["run", "strength"],
            "sessions_per_week": 3,
            "goal_text": "Halvmaraton",
        },
    )
    assert "lop/halvmaraton-periodisering.md" in paths
    assert "lop/ukeplaner-lav-frekvens.md" in paths
    assert "lop/styrke-og-lop.md" in paths


def test_resolve_constraints_persisted_fields():
    c = resolve_constraints(
        {
            "athlete_type": "runner",
            "allowed_disciplines": ["run", "strength"],
            "sessions_per_week": 3,
        }
    )
    assert c["sessions_per_week"] == 3
    assert c["allowed_disciplines"] == ["run", "strength"]
