"""Real-data charts: ICU activities (executed) + planned_sessions (future)."""

from __future__ import annotations

from datetime import date, timedelta

from period_training import (
    planned_sessions_to_daily_hours,
    bucket_volume_series,
)


def test_planned_daily_only_future():
    today = date(2026, 10, 15)
    start = today - timedelta(days=7)
    end = today + timedelta(days=7)
    sessions = [
        {"session_date": "2026-10-10", "duration_minutes": 60, "sport": "run"},  # past — ignore
        {"session_date": "2026-10-16", "duration_minutes": 45, "sport": "run"},
        {"session_date": "2026-10-17", "duration_minutes": 90, "sport": "bike"},
    ]
    daily = planned_sessions_to_daily_hours(sessions, start, end, today=today)
    by = {r["date"]: r for r in daily}
    assert by["2026-10-10"]["hours"] == 0.0
    assert abs(by["2026-10-16"]["hours"] - 0.75) < 0.01
    assert abs(by["2026-10-17"]["hours"] - 1.5) < 0.01
    vol = bucket_volume_series(daily)
    assert vol["bucket"] in ("day", "week")
    assert sum(b["hours"] for b in vol["bars"]) > 0


def test_builder_steps_roundtrip():
    from sessions_service import (
        builder_steps_to_description,
        normalize_builder_steps,
        total_builder_duration,
    )

    steps = normalize_builder_steps(
        [
            {"type": "warmup", "duration_minutes": 12, "intensity": "Z2"},
            {"type": "work", "duration_minutes": 5, "intensity": "Z4", "note": "×6"},
            {"type": "recover", "duration_minutes": 2},
            {"type": "cooldown", "duration_minutes": 10},
        ]
    )
    assert [s["type"] for s in steps] == ["warmup", "work", "recover", "cooldown"]
    assert total_builder_duration(steps) == 29
    desc = builder_steps_to_description(steps)
    assert "Oppvarming" in desc
    assert "Arbeid" in desc
