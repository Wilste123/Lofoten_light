"""TB-Score bridge + week analysis (agent-modus parity in coach-api)."""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chat_service import week_check_summary_nb
from tb_score import (
    compute_tb_snapshot,
    plan_b_recommendation_nb,
    tb_bits_nb,
)
from week_analysis import (
    calendar_source_label,
    format_session_prescription_nb,
    quality_prescriptions_nb,
    summarize_week_load,
)


def _wellness_days(n: int = 25) -> list[dict]:
    base = date(2026, 10, 1)
    rows = []
    for i in range(n):
        d = base + timedelta(days=i)
        rows.append(
            {
                "id": d.isoformat(),
                "date": d.isoformat(),
                "ctl": 20 + i * 0.5,
                "atl": 40 + i * 1.2,
                "hrv": 55 + (i % 5),
                "restingHR": 58,
                "sleepSecs": 7.2 * 3600,
            }
        )
    return rows


def _activity_rows() -> list[dict]:
    return [
        {
            "start_date_local": "2026-10-15T17:00:00",
            "icu_training_load": 120,
            "moving_time": 5400,
            "type": "Run",
            "icu_intensity": 0.82,
        }
    ]


def test_compute_tb_snapshot_available():
    tb = compute_tb_snapshot(
        _wellness_days(),
        _activity_rows(),
        as_of="2026-10-16T19:00:00",
    )
    assert tb["available"] is True
    assert tb["tb_score"] is not None
    assert 0 <= int(tb["tb_score"]) <= 100
    assert tb["band"] in ("grønn", "gul", "rød")
    assert tb["plan_b_nb"]
    bits = tb_bits_nb(tb)
    assert any("TB-Score" in b for b in bits)


def test_compute_tb_empty_wellness():
    tb = compute_tb_snapshot([], [])
    assert tb["available"] is False


def test_plan_b_bands():
    assert "Plan A" in plan_b_recommendation_nb(band="grønn")
    assert "Plan B" in plan_b_recommendation_nb(band="gul")
    assert "recovery" in plan_b_recommendation_nb(band="rød").lower() or "Recovery" in plan_b_recommendation_nb(
        band="rød"
    )


def test_summarize_week_load():
    completed = [
        {
            "kind": "activity",
            "discipline": "run",
            "discipline_label": "Løp",
            "duration_hours": 1.0,
            "training_load": 70,
            "intensity": 0.75,
        },
        {
            "kind": "activity",
            "discipline": "bike",
            "discipline_label": "Sykkel",
            "duration_hours": 1.5,
            "training_load": 90,
            "intensity": 0.7,
        },
    ]
    planned = [
        {"duration_minutes": 60, "sport": "Swim", "name": "Svøm"},
    ]
    s = summarize_week_load(completed, planned=planned)
    assert s["sessions"] == 2
    assert s["hours"] == 2.5
    assert s["load"] == 160
    assert s["avg_intensity"] is not None
    assert "Løp" in s["load_by_sport"] or "Sykkel" in s["load_by_sport"]


def test_quality_prescription_warmup_main_cooldown():
    s = {
        "date": "2026-10-10",
        "name": "6x5 terskel",
        "discipline": "bike",
        "description": (
            "Warmup:\n- 15 min Z2\n"
            "Main:\n- 6x5 min @ terskel\n- 3 min Z1 mellom\n"
            "Cooldown:\n- 10 min easy\n"
            "Plan B: kutt til 4x5 hvis bein er tunge\n"
            "Ukerisiko: for mye terskel etter dårlig søvn\n"
        ),
    }
    block = format_session_prescription_nb(s)
    assert block is not None
    assert "Oppvarming" in block or "Warmup" in block or "15 min" in block
    assert "6x5" in block or "Hoveddel" in block or "Main" in block
    assert "Plan B" in block
    blocks = quality_prescriptions_nb([s])
    assert blocks


def test_calendar_source_label():
    assert "ikke koblet" in calendar_source_label(
        intervals_linked=False, used_icu_calendar=False
    )
    assert "Intervals-kalender" in calendar_source_label(
        intervals_linked=True, used_icu_calendar=True
    )
    assert "Don't-touch" in calendar_source_label(
        intervals_linked=True, used_icu_calendar=True, dont_touch=True
    )


def test_week_check_summary_includes_tb_and_prescriptions():
    reply = week_check_summary_nb(
        name="William",
        week_start="2026-10-06",
        week_end="2026-10-12",
        planned_lines=["2026-10-07 · Rolig løp"],
        completed_lines=["2026-10-07 · Easy run"],
        missed_lines=[],
        wellness_bits=["Søvn snitt ~7.0 t"],
        intervals_linked=True,
        sessions_planned=1,
        sessions_done=1,
        compliance_pct=100.0,
        calendar_source_line="Kilde: Intervals-kalender.",
        load_bits=["Gjennomført: ~5.0 t · load ~250"],
        tb_bits=["TB-Score 72/100 · gul", "Plan B: Z2 i stedet for terskel"],
        plan_b_bits=["Plan B: kutt intervaller"],
        risk_bits=["Ukerisiko: søvn"],
        prescription_blocks=["2026-10-08 · 6x5\n  Oppvarming:\n    - 15 min"],
    )
    assert "TB-Score" in reply
    assert "Belastning" in reply
    assert "Kvalitetsøkter" in reply
    assert "Plan B" in reply
    assert "Ukerisiko" in reply
    assert "Intervals-kalender" in reply
