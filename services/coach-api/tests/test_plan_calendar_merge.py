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
        {
            "external_id": "ll-agent-20261011-run-0",
            "name": "Agent økt",
            "category": "WORKOUT",
            "start_date_local": "2026-10-11T07:00:00",
            "type": "Run",
        },
        {
            "id": 999,
            "external_id": "",
            "name": "Manuell ICU",
            "category": "WORKOUT",
            "start_date_local": "2026-10-13T07:00:00",
            "type": "Ride",
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
    assert counts[SYNC_INTERVALS_ONLY] == 3
    assert len(merged) == 5
    by_eid = {str(s.get("external_id") or ""): s for s in merged}
    assert by_eid["ll-coach-w-20261009-run-0"]["source_kind"] == "coach"
    assert by_eid["ll-agent-20261011-run-0"]["source_kind"] == "agent"
    assert by_eid["ll-agent-20261011-run-0"]["source_kind_nb"]
    manual = [s for s in merged if s.get("name") == "Manuell ICU"][0]
    assert manual["source_kind"] == "manual"


def test_classify_and_plan_b_extract():
    from plan_calendar_merge import (
        classify_external_source,
        extract_plan_b_lines,
        extract_weekly_risk_lines,
    )

    assert classify_external_source("ll-agent-x") == "agent"
    assert classify_external_source("ll-coach-w-1") == "coach"
    assert classify_external_source("other-id") == "manual"
    assert classify_external_source("") == "app"
    lines = extract_plan_b_lines(
        [{"description": "Warmup.\nPlan B: 30 min rolig hjemme.\nCool."}]
    )
    assert lines and "Plan B" in lines[0]
    risk = extract_weekly_risk_lines(
        [{"description": "Ukerisiko: for hard intervall for tidlig."}]
    )
    assert risk and "Ukerisiko" in risk[0]


def test_weekday_focus_intent_and_dates():
    assert user_requests_weekday_plan_focus("Jusetr lørdag og mandag")
    assert weekday_indices_from_message("juster lørdag og mandag") == [0, 5]
    days = dates_for_weekday_indices(
        [0, 5], anchor=date(2026, 10, 2), week_start_key="this_week"
    )
    # 2026-10-02 is Friday → week Mon 2026-09-28 … Sat 2026-10-03
    assert days == [date(2026, 9, 28), date(2026, 10, 3)]
