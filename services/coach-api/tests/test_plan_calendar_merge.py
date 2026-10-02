"""Plan calendar merge — app SoT + Intervals sync_status."""

from __future__ import annotations

from datetime import date

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plan_calendar_merge import (
    SYNC_INTERVALS_ONLY,
    SYNC_PLANNED_NOT_SYNCED,
    SYNC_SYNCED,
    dates_for_weekday_indices,
    merge_plan_calendar_sessions,
    user_requests_weekday_plan_focus,
    weekday_indices_from_message,
)


def test_merge_synced_and_unsynced():
    planned = [
        {
            "session_date": "2026-10-09",
            "name": "Løping - intervall",
            "sport": "run",
            "external_id": "ll-coach-w-20261009-run-0",
        },
        {
            "session_date": "2026-10-02",
            "name": "Rolig",
            "sport": "run",
            "external_id": "ll-coach-w-20261002-rolig-0",
        },
    ]
    icu = [
        {
            "external_id": "ll-coach-w-20261009-run-0",
            "name": "Løping - intervall",
            "category": "WORKOUT",
            "start_date_local": "2026-10-09T07:00:00",
            "type": "Run",
        },
        {
            "external_id": "ll-coach-w-20261012-swim-0",
            "name": "Svøm ICU only",
            "category": "WORKOUT",
            "start_date_local": "2026-10-12T07:00:00",
            "type": "Swim",
        },
    ]
    merged, counts = merge_plan_calendar_sessions(
        planned,
        icu,
        range_start=date(2026, 10, 1),
        range_end=date(2026, 10, 31),
    )
    assert counts[SYNC_SYNCED] == 1
    assert counts[SYNC_PLANNED_NOT_SYNCED] == 1
    assert counts[SYNC_INTERVALS_ONLY] == 1
    assert len(merged) == 3


def test_weekday_focus_intent_and_dates():
    assert user_requests_weekday_plan_focus("Jusetr lørdag og mandag")
    assert weekday_indices_from_message("juster lørdag og mandag") == [0, 5]
    days = dates_for_weekday_indices(
        [0, 5], anchor=date(2026, 10, 2), week_start_key="this_week"
    )
    assert days == [date(2026, 9, 28), date(2026, 10, 4)]
