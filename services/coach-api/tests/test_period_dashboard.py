"""Period query parsing + dashboard training aggregation."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import config
import main as main_mod
from db import init_db
from period_training import (
    PeriodValidationError,
    bucket_volume_series,
    build_period_training_payload,
    choose_volume_bucket,
    hours_by_day,
    parse_period_window,
    resolve_period_training,
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    athletes = tmp_path / "athletes"
    athletes.mkdir()
    monkeypatch.setattr(config, "DATABASE_PATH", db)
    monkeypatch.setattr(config, "ATHLETES_DATA_DIR", athletes)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    init_db(db)
    with TestClient(main_mod.app) as c:
        yield c, athletes


def _onboard(c) -> str:
    r = c.post(
        "/v1/onboarding",
        json={
            "display_name": "Testa",
            "username": "testa",
            "coach_display_name": "Rocky",
            "goal_text": "Base",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["athlete"]["id"]


def test_parse_period_presets():
    today = date(2026, 9, 27)
    p7 = parse_period_window("7d", today=today)
    assert p7 == {
        "preset": "7d",
        "start": "2026-09-21",
        "end": "2026-09-27",
        "days": 7,
    }
    p14 = parse_period_window(None, today=today)
    assert p14["preset"] == "14d"
    assert p14["days"] == 14
    assert p14["start"] == "2026-09-14"
    p90 = parse_period_window("90d", today=today)
    assert p90["days"] == 90
    assert p90["start"] == "2026-06-30"


def test_parse_period_custom_and_validation():
    today = date(2026, 9, 27)
    custom = parse_period_window(
        "custom", "2026-09-01", "2026-09-15", today=today
    )
    assert custom["preset"] == "custom"
    assert custom["days"] == 15
    assert custom["start"] == "2026-09-01"
    assert custom["end"] == "2026-09-15"

    # Caps future end to today
    capped = parse_period_window(
        "custom", "2026-09-20", "2026-10-01", today=today
    )
    assert capped["end"] == "2026-09-27"

    with pytest.raises(PeriodValidationError):
        parse_period_window("custom", today=today)
    with pytest.raises(PeriodValidationError):
        parse_period_window("custom", "2026-09-20", "2026-09-10", today=today)
    with pytest.raises(PeriodValidationError):
        parse_period_window("nope", today=today)


def test_build_period_training_payload_no_targets():
    start = date(2026, 9, 14)
    end = date(2026, 9, 27)
    payload = build_period_training_payload(
        start=start,
        end=end,
        hours={"swim": 2.0, "bike": 8.5, "run": 3.0, "strength": 1.0},
        session_counts={"swim": 2, "bike": 4, "run": 3, "strength": 1},
        source="intervals",
        activity_count=10,
    )
    assert payload["total_hours"] == 14.5
    assert payload["activity_count"] == 10
    assert payload["days"] == 14
    assert "target_hours" not in payload["disciplines"][0]
    assert payload["disciplines"][0]["hours"] == 2.0
    assert "compliance" not in payload["note"].lower() or "ikke" in payload["note"].lower()
    assert "charts" in payload
    assert payload["charts"]["volume"]["bucket"] == "day"
    assert len(payload["daily_hours"]) == 14
    assert len(payload["charts"]["by_discipline"]) == 4


def test_choose_volume_bucket_by_span():
    assert choose_volume_bucket(1) == "day"
    assert choose_volume_bucket(7) == "day"
    assert choose_volume_bucket(14) == "day"
    assert choose_volume_bucket(30) == "day"
    assert choose_volume_bucket(31) == "day"
    assert choose_volume_bucket(32) == "week"
    assert choose_volume_bucket(60) == "week"  # ~2 months
    assert choose_volume_bucket(75) == "week"
    assert choose_volume_bucket(76) == "month"
    assert choose_volume_bucket(90) == "month"
    assert choose_volume_bucket(180) == "month"
    assert choose_volume_bucket(365) == "month"
    assert choose_volume_bucket(550) == "month"
    assert choose_volume_bucket(551) == "year"
    assert choose_volume_bucket(1096) == "year"  # ~3 years


def test_hours_by_day_aggregates_and_fills_gaps():
    acts = [
        {
            "type": "Ride",
            "moving_time": 3600,
            "start_date_local": "2026-09-20T10:00:00",
        },
        {
            "type": "Ride",
            "moving_time": 1800,
            "start_date_local": "2026-09-20T18:00:00",
        },
        {
            "type": "Run",
            "moving_time": 1800,
            "start_date_local": "2026-09-22T07:00:00",
        },
    ]
    daily = hours_by_day(acts, date(2026, 9, 20), date(2026, 9, 22))
    assert len(daily) == 3
    assert daily[0]["date"] == "2026-09-20"
    assert daily[0]["hours"] == 1.5
    assert daily[0]["by_discipline"]["bike"] == 1.5
    assert daily[1]["hours"] == 0.0  # gap day
    assert daily[2]["by_discipline"]["run"] == 0.5


def test_bucket_volume_series_weeks_when_mid_span():
    start = date(2026, 8, 1)
    end = date(2026, 9, 15)
    # 46 days → week buckets
    daily = hours_by_day([], start, end)
    daily[0]["hours"] = 2.0
    daily[0]["by_discipline"]["bike"] = 2.0
    daily[10]["hours"] = 3.0
    daily[10]["by_discipline"]["run"] = 3.0
    volume = bucket_volume_series(daily)
    assert volume["bucket"] == "week"
    assert len(volume["bars"]) < len(daily)
    assert sum(b["hours"] for b in volume["bars"]) == pytest.approx(5.0)

    short = hours_by_day(
        [
            {
                "type": "Swim",
                "moving_time": 2400,
                "start_date_local": "2026-09-21T06:00:00",
            }
        ],
        date(2026, 9, 21),
        date(2026, 9, 27),
    )
    day_vol = bucket_volume_series(short)
    assert day_vol["bucket"] == "day"
    assert len(day_vol["bars"]) == 7
    assert day_vol["bars"][0]["hours"] == 0.67


def test_bucket_volume_series_month_and_year():
    # 90 d → month
    start_90 = date(2026, 6, 30)
    end_90 = date(2026, 9, 27)
    daily_90 = hours_by_day([], start_90, end_90)
    daily_90[0]["hours"] = 4.0
    daily_90[0]["by_discipline"]["bike"] = 4.0
    daily_90[-1]["hours"] = 1.0
    daily_90[-1]["by_discipline"]["run"] = 1.0
    month_vol = bucket_volume_series(daily_90)
    assert month_vol["bucket"] == "month"
    assert len(month_vol["bars"]) >= 3  # jun–sep
    assert month_vol["bars"][0]["label"].startswith("jun")
    assert sum(b["hours"] for b in month_vol["bars"]) == pytest.approx(5.0)
    # Empty month axis still present (zeros filled via hours_by_day)
    assert all("label" in b and "hours" in b for b in month_vol["bars"])

    # ~3 years → year
    start_y = date(2023, 9, 27)
    end_y = date(2026, 9, 27)
    daily_y = hours_by_day([], start_y, end_y)
    daily_y[0]["hours"] = 10.0
    daily_y[0]["by_discipline"]["bike"] = 10.0
    daily_y[400]["hours"] = 5.0
    daily_y[400]["by_discipline"]["run"] = 5.0
    year_vol = bucket_volume_series(daily_y)
    assert year_vol["bucket"] == "year"
    assert len(year_vol["bars"]) == 4  # 2023–2026
    assert year_vol["bars"][0]["label"] == "2023"
    assert year_vol["bars"][-1]["label"] == "2026"
    assert sum(b["hours"] for b in year_vol["bars"]) == pytest.approx(15.0)


def test_bucket_volume_series_legacy_max_bars():
    """max_bars keeps day/week-only behaviour for older call sites/tests."""
    start = date(2026, 7, 1)
    end = date(2026, 9, 27)
    daily = hours_by_day([], start, end)
    volume = bucket_volume_series(daily, max_bars=31)
    assert volume["bucket"] == "week"
    short = hours_by_day([], date(2026, 9, 21), date(2026, 9, 27))
    assert bucket_volume_series(short, max_bars=31)["bucket"] == "day"


def test_parse_period_custom_allows_multi_year():
    today = date(2026, 9, 27)
    long = parse_period_window(
        "custom", "2023-09-27", "2026-09-27", today=today
    )
    assert long["preset"] == "custom"
    assert long["days"] == 1097  # inclusive ~3 years
    with pytest.raises(PeriodValidationError):
        parse_period_window(
            "custom", "2020-01-01", "2026-09-27", today=today
        )

def test_resolve_period_training_aggregates_activities():
    secrets = {
        "intervals_api_key": "abc",
        "intervals_athlete_id": "i123",
    }
    acts = [
        {
            "id": "1",
            "type": "Ride",
            "moving_time": 3600,
            "start_date_local": "2026-09-20T10:00:00",
        },
        {
            "id": "2",
            "type": "Run",
            "moving_time": 1800,
            "start_date_local": "2026-09-21T07:00:00",
        },
        {
            "id": "3",
            "type": "Swim",
            "moving_time": 2400,
            "start_date_local": "2026-09-22T06:00:00",
        },
    ]
    with patch(
        "period_training.fetch_intervals_activities", return_value=acts
    ):
        out = resolve_period_training(
            secrets, date(2026, 9, 14), date(2026, 9, 27)
        )
    assert out["source"] == "intervals"
    assert out["activity_count"] == 3
    assert out["total_hours"] == 2.2  # 1 + 0.5 + 0.67 ≈ 2.2
    by_id = {d["id"]: d for d in out["disciplines"]}
    assert by_id["bike"]["hours"] == 1.0
    assert by_id["bike"]["session_count"] == 1
    assert by_id["run"]["hours"] == 0.5
    assert by_id["swim"]["session_count"] == 1
    assert len(out["daily_hours"]) == 14
    assert out["charts"]["volume"]["bucket"] == "day"
    # Three activity days non-zero
    non_zero = [d for d in out["daily_hours"] if d["hours"] > 0]
    assert len(non_zero) == 3


def test_dashboard_period_query_params(client):
    c, _athletes = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}

    fake_training = {
        "window": {"start": "2026-09-21", "end": "2026-09-27"},
        "days": 7,
        "source": "demo",
        "activity_count": 5,
        "total_hours": 9.0,
        "disciplines": [
            {"id": "swim", "label": "Svøm", "hours": 1.0, "session_count": 1},
            {"id": "bike", "label": "Sykkel", "hours": 5.0, "session_count": 2},
            {"id": "run", "label": "Løp", "hours": 2.0, "session_count": 1},
            {"id": "strength", "label": "Styrke", "hours": 1.0, "session_count": 1},
        ],
        "daily_hours": [],
        "charts": {
            "volume": {
                "bucket": "day",
                "bars": [
                    {
                        "label": "21.09",
                        "start": "2026-09-21",
                        "end": "2026-09-21",
                        "hours": 1.5,
                        "by_discipline": {},
                    }
                ],
            },
            "by_discipline": [
                {"id": "swim", "label": "Svøm", "hours": 1.0},
                {"id": "bike", "label": "Sykkel", "hours": 5.0},
                {"id": "run", "label": "Løp", "hours": 2.0},
                {"id": "strength", "label": "Styrke", "hours": 1.0},
            ],
        },
        "note": "Treningsdata for valgt periode.",
    }
    fake_wellness = {
        "window": {"start": "2026-09-21", "end": "2026-09-27"},
        "source": "intervals",
        "fetch_error": False,
        "fetch_error_detail": None,
        "sleep": {"available": True, "avg_hours": 7.0, "note": "OK", "short_nights": 0},
        "body": {"available": False},
        "load_wellness": {"available": True, "ctl": 42, "atl": 38, "readiness": 7},
        "load_series": {
            "available": True,
            "points": [
                {"date": "2026-09-21", "label": "21.09", "ctl": 40, "atl": 36},
                {"date": "2026-09-27", "label": "27.09", "ctl": 42, "atl": 38},
            ],
            "note": "CTL/ATL fra Intervals wellness for perioden.",
        },
    }

    with (
        patch("main.resolve_period_training", return_value=fake_training) as mock_tr,
        patch("main.resolve_wellness_bundle", return_value=fake_wellness) as mock_wl,
    ):
        r = c.get("/v1/dashboard?period=7d", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["period"]["preset"] == "7d"
    assert body["period"]["days"] == 7
    assert body["training"]["total_hours"] == 9.0
    assert body["hours"]["total_hours"] == 9.0
    assert body["training"]["charts"]["volume"]["bars"][0]["hours"] == 1.5
    assert body["load"]["series"]["available"] is True
    assert len(body["load"]["series"]["points"]) == 2
    assert body["compliance_app_computed"] is True
    assert "compliance" in body
    # Season compliance still present and separate
    assert body["compliance"] is not None
    assert mock_tr.called
    call_start, call_end = mock_tr.call_args[0][1], mock_tr.call_args[0][2]
    assert (call_end - call_start).days + 1 == 7
    assert mock_wl.call_args.kwargs.get("start") == call_start
    assert mock_wl.call_args.kwargs.get("end") == call_end

    with (
        patch("main.resolve_period_training", return_value=fake_training),
        patch("main.resolve_wellness_bundle", return_value=fake_wellness),
    ):
        r2 = c.get(
            "/v1/dashboard?period=custom&from=2026-09-01&to=2026-09-10",
            headers=headers,
        )
    assert r2.status_code == 200
    assert r2.json()["period"]["preset"] == "custom"
    assert r2.json()["period"]["days"] == 10

    bad = c.get("/v1/dashboard?period=custom", headers=headers)
    assert bad.status_code == 400

    bad2 = c.get("/v1/dashboard?period=banana", headers=headers)
    assert bad2.status_code == 400
