"""Unit tests for season volume / compliance math + Intervals resolve."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from progress_compliance import (
    build_progress_payload,
    clear_progress_cache,
    compliance_pct,
    days_to_goal,
    fetch_intervals_activities,
    map_activity_type,
    parse_duration_hours,
    pick_current_and_next,
    progress_pct,
    resolve_progress,
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
    assert "completed_hours / season_target_hours" in payload["formula"]


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


def test_resolve_progress_demo_without_credentials():
    clear_progress_cache()
    athlete = {"season_start_date": "2026-01-01", "season_bike_hours_target": 500}
    payload = resolve_progress(athlete, None, today=date(2026, 9, 25))
    assert payload["source"] == "demo"
    bike = next(d for d in payload["disciplines"] if d["id"] == "bike")
    assert bike["completed_hours"] == 175.0


def test_resolve_progress_intervals_mocked():
    clear_progress_cache()
    athlete = {
        "season_start_date": "2026-01-01",
        "season_bike_hours_target": 500,
        "season_swim_hours_target": 100,
        "season_run_hours_target": 150,
        "season_strength_hours_target": 50,
    }
    secrets = {"intervals_api_key": "test-key-xyz", "intervals_athlete_id": "i1"}
    acts = [
        {"id": "1", "type": "Ride", "moving_time": 7200, "start_date_local": "2026-09-01T08:00:00"},
        {"id": "2", "type": "Swim", "moving_time": 3600, "start_date_local": "2026-09-02T07:00:00"},
        {"id": "3", "type": "Run", "moving_time": 3600, "start_date_local": "2026-09-03T07:00:00"},
        {"id": "4", "type": "WeightTraining", "moving_time": 1800, "start_date_local": "2026-09-04T18:00:00"},
    ]
    with patch(
        "progress_compliance.fetch_intervals_activities", return_value=acts
    ) as mocked:
        payload = resolve_progress(
            athlete, secrets, today=date(2026, 9, 25), use_cache=False
        )
        mocked.assert_called_once()
    assert payload["source"] == "intervals"
    assert payload["activity_count"] == 4
    assert payload.get("fetch_error") is None
    bike = next(d for d in payload["disciplines"] if d["id"] == "bike")
    assert bike["completed_hours"] == 2.0
    assert bike["compliance_pct"] == 0.4  # 2/500*100
    swim = next(d for d in payload["disciplines"] if d["id"] == "swim")
    assert swim["completed_hours"] == 1.0


def test_resolve_progress_fetch_error_zeros_not_demo_hours():
    clear_progress_cache()
    athlete = {
        "season_start_date": "2026-01-01",
        "season_bike_hours_target": 500,
    }
    secrets = {"intervals_api_key": "bad", "intervals_athlete_id": "i1"}
    with patch(
        "progress_compliance.fetch_intervals_activities",
        side_effect=TimeoutError("timed out"),
    ):
        payload = resolve_progress(
            athlete, secrets, today=date(2026, 9, 25), use_cache=False
        )
    assert payload["fetch_error"] is True
    assert payload["source"] == "intervals"
    assert payload.get("retryable") is True
    bike = next(d for d in payload["disciplines"] if d["id"] == "bike")
    assert bike["completed_hours"] == 0.0  # not fake 175


def test_resolve_progress_season_not_started_skips_fetch():
    clear_progress_cache()
    athlete = {"season_start_date": "2026-09-28", "season_bike_hours_target": 500}
    secrets = {"intervals_api_key": "k", "intervals_athlete_id": "i1"}
    with patch("progress_compliance.fetch_intervals_activities") as mocked:
        payload = resolve_progress(
            athlete, secrets, today=date(2026, 9, 25), use_cache=False
        )
        mocked.assert_not_called()
    assert payload["source"] == "intervals"
    assert payload["season_not_started"] is True
    bike = next(d for d in payload["disciplines"] if d["id"] == "bike")
    assert bike["completed_hours"] == 0.0


def test_fetch_intervals_activities_paginates():
    """When a page is full (limit), fetch older pages until exhausted."""
    page1 = [
        {
            "id": str(i),
            "type": "Ride",
            "moving_time": 3600,
            "start_date_local": f"2026-06-{20 - (i % 10):02d}T08:00:00",
        }
        for i in range(100)
    ]
    # Force oldest in page1 to 2026-06-10
    for i, act in enumerate(page1):
        act["start_date_local"] = f"2026-06-{10 + (i % 15):02d}T08:00:00"
    page1[-1]["start_date_local"] = "2026-06-01T08:00:00"

    page2 = [
        {
            "id": "p2-1",
            "type": "Run",
            "moving_time": 1800,
            "start_date_local": "2026-05-15T08:00:00",
        }
    ]
    calls: list[tuple[str, str]] = []

    def fake_page(api_key, athlete_id, oldest, newest, **kwargs):
        calls.append((oldest, newest))
        if len(calls) == 1:
            return page1
        return page2

    with patch(
        "progress_compliance.fetch_intervals_activities_page", side_effect=fake_page
    ):
        acts = fetch_intervals_activities(
            "k", "i1", "2026-01-01", "2026-06-30", page_limit=100
        )
    assert len(calls) >= 2
    assert len(acts) == 101
    ids = {a["id"] for a in acts}
    assert "p2-1" in ids
    assert "0" in ids


def test_fetch_intervals_activities_page_builds_url():
    captured: dict[str, str] = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            body = json.dumps(
                [{"id": "a1", "type": "Ride", "moving_time": 3600}]
            ).encode()
            return body

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["auth"] = req.get_header("Authorization")
        return _Resp()

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        from progress_compliance import fetch_intervals_activities_page

        rows = fetch_intervals_activities_page(
            "secret", "i99", "2026-01-01", "2026-01-31"
        )
    assert len(rows) == 1
    assert "athlete/i99/activities" in captured["url"]
    assert "oldest=2026-01-01" in captured["url"]
    assert "newest=2026-01-31" in captured["url"]
    assert "limit=100" in captured["url"]
    assert "fields=" in captured["url"]
    assert captured["auth"].startswith("Basic ")
