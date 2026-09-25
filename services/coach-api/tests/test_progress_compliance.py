"""Unit tests for season volume / compliance math."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from progress_compliance import (
    build_progress_payload,
    compliance_pct,
    days_to_goal,
    map_activity_type,
    parse_duration_hours,
    pick_current_and_next,
    progress_pct,
    sum_hours_by_discipline,
)


def test_compliance_pct_basic():
    assert compliance_pct(175, 500) == 35.0
    assert compliance_pct(375, 500) == 75.0
    assert compliance_pct(500, 500) == 100.0
    assert compliance_pct(600, 500) == 100.0  # capped
    assert compliance_pct(0, 500) == 0.0
    assert compliance_pct(100, None) is None
    assert compliance_pct(100, 0) is None


def test_progress_pct_matches_compliance():
    assert progress_pct(175, 500) == compliance_pct(175, 500)


def test_parse_duration_hours():
    assert parse_duration_hours(3600, "moving_time") == 1.0
    assert parse_duration_hours(7200, "elapsed_time") == 2.0
    assert parse_duration_hours(1.5, "duration") == 1.5  # already hours
    assert parse_duration_hours(90, "duration") == 0.025  # seconds (>= 15)
    assert abs(parse_duration_hours(90, "moving_time") - 0.025) < 1e-9
    assert parse_duration_hours(None) is None
    assert parse_duration_hours("x") is None


def test_map_activity_type():
    assert map_activity_type("Ride") == "bike"
    assert map_activity_type("VirtualRide") == "bike"
    assert map_activity_type("Swim") == "swim"
    assert map_activity_type("TrailRun") == "run"
    assert map_activity_type("WeightTraining") == "strength"
    assert map_activity_type("Yoga") is None


def test_sum_hours_by_discipline():
    acts = [
        {"type": "Ride", "moving_time": 3600},
        {"type": "Ride", "elapsed_time": 1800},
        {"type": "Swim", "moving_time": 2400},
        {"type": "Run", "moving_time": 3600},
        {"type": "WeightTraining", "duration": 0.5},
    ]
    totals = sum_hours_by_discipline(acts)
    assert totals["bike"] == 1.5
    assert abs(totals["swim"] - 2400 / 3600) < 0.01
    assert totals["run"] == 1.0
    assert totals["strength"] == 0.5


def test_build_progress_payload_demo_style():
    athlete = {
        "season_bike_hours_target": 500,
        "season_swim_hours_target": 100,
        "season_run_hours_target": 150,
        "season_strength_hours_target": 50,
        "season_start_date": "2026-01-01",
    }
    payload = build_progress_payload(
        athlete,
        completed={"bike": 175, "swim": 28, "run": 62, "strength": 18},
        source="demo",
        today=date(2026, 9, 25),
    )
    assert payload["source"] == "demo"
    bike = next(d for d in payload["disciplines"] if d["id"] == "bike")
    assert bike["completed_hours"] == 175.0
    assert bike["target_hours"] == 500.0
    assert bike["compliance_pct"] == 35.0
    assert bike["progress_pct"] == 35.0
    assert payload["window"]["start"] == "2026-01-01"
    assert payload["window"]["end"] == "2026-09-25"


def test_pick_current_and_next():
    blocks = [
        {
            "id": "a",
            "title": "Base 1",
            "start_date": "2026-09-01",
            "end_date": "2026-09-28",
            "sort_order": 0,
        },
        {
            "id": "b",
            "title": "Base 2",
            "start_date": "2026-09-29",
            "end_date": "2026-10-26",
            "sort_order": 1,
        },
    ]
    picked = pick_current_and_next(blocks, today=date(2026, 9, 25))
    assert picked["current"]["id"] == "a"
    assert picked["next"]["id"] == "b"


def test_days_to_goal():
    assert days_to_goal({"goal_race_date": "2026-09-30"}, today=date(2026, 9, 25)) == 5
    assert days_to_goal({}, today=date(2026, 9, 25)) is None
