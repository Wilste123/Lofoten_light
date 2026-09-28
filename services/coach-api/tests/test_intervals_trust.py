"""Intervals trust: notes ≠ completed; planned-not-done; commercial constraints."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from athlete_constraints import validate_workouts_against_constraints
from athlete_type import TYPE_GENERAL, TYPE_HALF_MARATHON
from sessions_service import (
    list_sessions,
    normalize_event,
    sessions_snapshot_for_chat,
)


TODAY = date(2026, 9, 28)


def test_note_never_in_completed_or_recent():
    """Calendar NOTES must not appear as completed training."""
    secrets = {"intervals_api_key": "k", "intervals_athlete_id": "i1"}
    activities = [
        {
            "id": "a1",
            "type": "Run",
            "name": "Easy run",
            "moving_time": 3600,
            "start_date_local": "2026-09-27T07:00:00",
        }
    ]
    events = [
        {
            "id": "n1",
            "external_id": "ll-coach-b1-20260922",
            "category": "NOTE",
            "name": "Plan: Grunnlag",
            "start_date_local": "2026-09-22T07:00:00",
        },
        {
            "id": "n2",
            "external_id": "random-note",
            "category": "NOTE",
            "name": "Coach tip",
            "start_date_local": "2026-09-26T07:00:00",
        },
    ]
    with (
        patch("sessions_service.fetch_intervals_activities", return_value=activities),
        patch("sessions_service.fetch_events", return_value=events),
    ):
        bundle = list_sessions(secrets, today=TODAY)

    assert all(s.get("kind") == "activity" for s in bundle["recent"])
    assert all(s.get("kind") == "activity" for s in bundle["completed"])
    assert all(s.get("calendar_role") != "note" for s in bundle["completed"])
    assert len(bundle["notes"]) >= 1
    assert all(s.get("training_status") == "note" for s in bundle["notes"])

    snap = sessions_snapshot_for_chat(bundle)
    assert all(s.get("calendar_role") != "note" for s in snap["gjennomfort"])
    assert all(s.get("kind") != "event" or s.get("training_status") != "note" for s in snap["recent"])
    note_names = {s.get("name") for s in snap.get("noter") or []}
    assert "Plan: Grunnlag" in note_names or any("Plan" in (n or "") for n in note_names)


def test_planned_workout_not_done_not_counted_completed():
    """Past WORKOUT without matching activity → planned_not_done, not completed."""
    secrets = {"intervals_api_key": "k", "intervals_athlete_id": "i1"}
    activities: list = []  # nothing completed
    events = [
        {
            "id": "w1",
            "external_id": "ll-coach-w-20260925-z2-0",
            "category": "WORKOUT",
            "type": "Ride",
            "name": "Z2 75",
            "start_date_local": "2026-09-25T07:00:00",
            "moving_time": 4500,
        },
        {
            "id": "w2",
            "external_id": "ll-coach-w-20260930-run-0",
            "category": "WORKOUT",
            "type": "Run",
            "name": "Easy run",
            "start_date_local": "2026-09-30T07:00:00",
        },
    ]
    with (
        patch("sessions_service.fetch_intervals_activities", return_value=activities),
        patch("sessions_service.fetch_events", return_value=events),
    ):
        bundle = list_sessions(secrets, today=TODAY)

    assert bundle["completed"] == []
    assert bundle["recent"] == []
    assert len(bundle["planned_not_done"]) == 1
    assert bundle["planned_not_done"][0]["training_status"] == "planned_not_done"
    assert bundle["planned_not_done"][0]["name"] == "Z2 75"
    assert any(s.get("name") == "Easy run" for s in bundle["planned"])

    snap = sessions_snapshot_for_chat(bundle)
    assert snap["gjennomfort"] == []
    assert any(s.get("name") == "Z2 75" for s in snap["ikke_gjennomfort"])
    assert any(s.get("name") == "Easy run" for s in snap["planlagt"])
    assert "NOTE" not in (snap.get("note") or "").upper() or "NOTE ≠" in snap["note"]


def test_matched_activity_consumes_past_workout():
    """Past WORKOUT on same day as activity is not double-counted as missed."""
    secrets = {"intervals_api_key": "k", "intervals_athlete_id": "i1"}
    activities = [
        {
            "id": "a1",
            "type": "Ride",
            "name": "Outdoor",
            "moving_time": 3600,
            "start_date_local": "2026-09-25T08:00:00",
        }
    ]
    events = [
        {
            "id": "w1",
            "external_id": "ll-coach-w-20260925-z2-0",
            "category": "WORKOUT",
            "type": "Ride",
            "name": "Z2 planned",
            "start_date_local": "2026-09-25T07:00:00",
        }
    ]
    with (
        patch("sessions_service.fetch_intervals_activities", return_value=activities),
        patch("sessions_service.fetch_events", return_value=events),
    ):
        bundle = list_sessions(secrets, today=TODAY)

    assert len(bundle["completed"]) == 1
    assert bundle["completed"][0]["training_status"] == "completed"
    assert bundle["planned_not_done"] == []


def test_normalize_event_note_role():
    ev = normalize_event(
        {
            "id": "1",
            "external_id": "ll-coach-abc-20260928",
            "category": "NOTE",
            "name": "Plan",
            "start_date_local": "2026-09-28T07:00:00",
        },
        today=TODAY,
    )
    assert ev is not None
    assert ev["calendar_role"] == "note"
    assert ev["training_status"] == "note"


def test_commercial_discipline_cap_refuses_swim():
    athlete = {
        "athlete_type": TYPE_GENERAL,
        "allowed_disciplines": ["run", "strength"],
        "sessions_per_week": 3,
        "goal_text": "Komme i form",
    }
    gate = validate_workouts_against_constraints(
        athlete,
        [
            {
                "name": "Svømteknikk",
                "date": "2026-09-30",
                "sport": "swim",
                "duration_minutes": 45,
            }
        ],
    )
    assert gate["ok"] is False
    assert gate["accepted"] == []
    assert gate["rejected"]
    assert any("discipline_not_allowed" == r.get("reject_reason") for r in gate["rejected"])


def test_commercial_sessions_per_week_cap():
    athlete = {
        "athlete_type": TYPE_HALF_MARATHON,
        "allowed_disciplines": ["run", "strength"],
        "sessions_per_week": 3,
    }
    gate = validate_workouts_against_constraints(
        athlete,
        [
            {"name": "Run A", "date": "2026-09-29", "sport": "run", "duration_minutes": 40},
            {"name": "Run B", "date": "2026-09-30", "sport": "run", "duration_minutes": 40},
        ],
        existing_planned_this_week=3,
    )
    assert gate["ok"] is False
    assert gate["accepted"] == []
    assert gate["cap_hit"] is True


def test_commercial_allows_run_within_cap():
    athlete = {
        "athlete_type": TYPE_GENERAL,
        "allowed_disciplines": ["run", "strength"],
        "sessions_per_week": 3,
    }
    gate = validate_workouts_against_constraints(
        athlete,
        [
            {"name": "Easy", "date": "2026-09-29", "sport": "run", "duration_minutes": 40},
        ],
        existing_planned_this_week=1,
    )
    assert gate["ok"] is True
    assert len(gate["accepted"]) == 1


def test_injury_blocks_discipline():
    athlete = {
        "athlete_type": TYPE_HALF_MARATHON,
        "allowed_disciplines": ["run", "strength"],
        "sessions_per_week": 3,
        "injury_notes": "Pause løping pga knær — kun styrke inntil videre",
    }
    gate = validate_workouts_against_constraints(
        athlete,
        [{"name": "Tempo", "date": "2026-09-29", "sport": "run", "duration_minutes": 40}],
    )
    assert gate["ok"] is False
    assert any(r.get("reject_reason") == "injury_block" for r in gate["rejected"])


def test_partial_fetch_flagged():
    secrets = {"intervals_api_key": "k", "intervals_athlete_id": "i1"}
    with (
        patch(
            "sessions_service.fetch_intervals_activities",
            return_value=[
                {
                    "id": "a1",
                    "type": "Run",
                    "name": "Run",
                    "moving_time": 1800,
                    "start_date_local": "2026-09-27T07:00:00",
                }
            ],
        ),
        patch(
            "sessions_service.fetch_events",
            side_effect=RuntimeError("Intervals API 503"),
        ),
    ):
        bundle = list_sessions(secrets, today=TODAY)
    assert bundle["partial_fetch"] is True
    assert bundle["fetch_error_detail"]
    assert len(bundle["completed"]) == 1
    snap = sessions_snapshot_for_chat(bundle)
    assert snap["partial_fetch"] is True
    assert "Delvis" in snap["note"] or "delvis" in snap["note"].lower()
