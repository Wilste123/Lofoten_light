"""Tests: form_estimates from Intervals + calendar sync preview/confirm."""

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
from db import get_athlete, init_db, db_session
from form_from_intervals import (
    activities_to_power_list,
    activity_to_power,
    parse_power_curve_mmp,
    resolve_form_estimates,
)
from intervals_calendar import build_block_note_events, external_id_for_block_day
from progress_compliance import on_pace_metrics


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
            "coach_personality": "direkte",
            "accent_color": "#1a6b4a",
            "ftp_tested": 250,
            "weight_kg": 78,
            "age_years": 35,
        },
    )
    assert r.status_code == 200
    return r.json()["athlete"]["id"]


def _link_intervals(c, headers, monkeypatch):
    monkeypatch.setattr(
        main_mod,
        "smoke_test_intervals",
        lambda key, icu: (True, None),
    )
    put = c.put(
        "/v1/athlete/me/intervals",
        headers=headers,
        json={
            "intervals_athlete_id": "i42",
            "intervals_api_key": "live-key-form",
            "verify": False,
        },
    )
    assert put.status_code == 200


def test_activity_to_power_and_curve_parse():
    act = {
        "type": "Ride",
        "moving_time": 3600,
        "average_watts": 200,
    }
    p = activity_to_power(act)
    assert p is not None
    assert p.duration_min == 60
    assert p.mmp[20] == 200
    assert p.mmp[5] == 200

    mmp = parse_power_curve_mmp(
        {"90d": {"secs": [300, 480, 720, 1200], "watts": [400, 350, 320, 280]}}
    )
    assert mmp[5] == 400
    assert mmp[20] == 280


def test_resolve_form_estimates_from_icu_mocked():
    athlete = {"ftp_tested": 250, "weight_kg": 78, "age_years": 35}
    secrets = {"intervals_api_key": "k", "intervals_athlete_id": "i1"}
    rides = [
        {
            "id": str(i),
            "type": "Ride",
            "moving_time": 3600,
            "average_watts": 200 + i,
            "start_date_local": f"2026-08-{10 + i:02d}T08:00:00",
        }
        for i in range(5)
    ]
    with (
        patch(
            "form_from_intervals.fetch_bike_power_activities",
            return_value=rides,
        ),
        patch(
            "form_from_intervals.fetch_power_curve_mmp",
            return_value={20: 280, 12: 300, 8: 320},
        ),
    ):
        result = resolve_form_estimates(athlete, secrets, today=date(2026, 9, 25))
    assert result["fetch_source"] == "intervals"
    assert result["gate_open"] is True
    assert result["ftp_estimated"] is not None
    assert result["qualifying_sessions"] >= 5


def test_overview_wires_form_estimates_and_persists(client, monkeypatch):
    c, _ = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}
    _link_intervals(c, headers, monkeypatch)

    rides = [
        {
            "id": f"r{i}",
            "type": "VirtualRide",
            "moving_time": 45 * 60,
            "icu_weighted_avg_watts": 220,
            "start_date_local": f"2026-07-{i + 1:02d}T09:00:00",
        }
        for i in range(6)
    ]

    monkeypatch.setattr(
        "form_from_intervals.fetch_bike_power_activities",
        lambda *a, **k: rides,
    )
    monkeypatch.setattr(
        "form_from_intervals.fetch_power_curve_mmp",
        lambda *a, **k: {20: 260, 12: 275},
    )
    monkeypatch.setattr(
        "progress_compliance.fetch_intervals_activities",
        lambda *a, **k: [],
    )

    ov = c.get("/v1/overview", headers=headers)
    assert ov.status_code == 200
    body = ov.json()
    assert body["gate_open"] is True
    assert body["ftp_estimated"] is not None
    assert body["qualifying_sessions"] >= 5

    with db_session(config.DATABASE_PATH) as conn:
        athlete = get_athlete(conn, aid)
    assert athlete["ftp_estimated"] == body["ftp_estimated"]


def test_form_recompute_endpoint(client, monkeypatch):
    c, _ = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}
    _link_intervals(c, headers, monkeypatch)

    rides = [
        {
            "id": f"x{i}",
            "type": "Ride",
            "moving_time": 50 * 60,
            "average_watts": 210,
        }
        for i in range(5)
    ]
    monkeypatch.setattr(
        "form_from_intervals.fetch_bike_power_activities",
        lambda *a, **k: rides,
    )
    monkeypatch.setattr(
        "form_from_intervals.fetch_power_curve_mmp",
        lambda *a, **k: {20: 250},
    )

    r = c.post("/v1/form/recompute", headers=headers)
    assert r.status_code == 200
    assert r.json()["estimates"]["gate_open"] is True
    assert r.json()["athlete"]["ftp_estimated"] is not None


def test_on_pace_formula():
    # 100d season, day 50 → expected half of target
    m = on_pace_metrics(
        40,
        100,
        season_start=date(2026, 1, 1),
        goal_race=date(2026, 4, 11),  # 100 days
        today=date(2026, 2, 19),  # day 50 (Jan1 + 49 = Feb19 → elapsed 50)
    )
    assert m["season_days"] == 100
    assert m["elapsed_days"] == 50
    assert m["expected_hours"] == 50.0
    assert m["on_pace_pct"] == 80.0
    assert m["on_pace"] is False
    assert "Bak plan" in (m["on_pace_note"] or "")


def test_calendar_preview_confirm_push_mocked(client, monkeypatch):
    c, _ = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}
    _link_intervals(c, headers, monkeypatch)

    created = c.post(
        "/v1/athlete/me/plan-blocks",
        headers=headers,
        json={
            "title": "Base 1",
            "theme": "Aerob",
            "start_date": "2026-09-28",
            "end_date": "2026-10-25",
            "weekly_hours": 8,
        },
    )
    assert created.status_code == 200

    preview = c.post(
        "/v1/athlete/me/intervals/calendar/preview",
        headers=headers,
        json={"op": "push"},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["confirm_required"] is True
    assert body["count"] >= 1
    assert body["pending_id"]
    assert all(e["external_id"].startswith("ll-coach-") for e in body["events"])

    pushed = {}

    def _fake_post(api_key, athlete_id, events, **kwargs):
        pushed["n"] = len(events)
        pushed["key"] = api_key
        return {"count": len(events), "dry": False}

    monkeypatch.setattr(main_mod, "post_events_bulk", _fake_post)

    confirm = c.post(
        "/v1/athlete/me/intervals/calendar/confirm",
        headers=headers,
        json={"pending_id": body["pending_id"]},
    )
    assert confirm.status_code == 200
    assert confirm.json()["ok"] is True
    assert confirm.json()["pushed"] == body["count"]
    assert pushed["n"] == body["count"]
    assert pushed["key"] == "live-key-form"

    # Second confirm rejected
    again = c.post(
        "/v1/athlete/me/intervals/calendar/confirm",
        headers=headers,
        json={"pending_id": body["pending_id"]},
    )
    assert again.status_code == 400


def test_calendar_delete_preview_confirm(client, monkeypatch):
    c, _ = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}
    _link_intervals(c, headers, monkeypatch)

    c.post(
        "/v1/athlete/me/plan-blocks",
        headers=headers,
        json={
            "title": "B0",
            "start_date": "2026-09-01",
            "end_date": "2026-09-28",
            "weekly_hours": 7,
        },
    )

    monkeypatch.setattr(
        main_mod,
        "fetch_events",
        lambda *a, **k: [],
    )

    preview = c.post(
        "/v1/athlete/me/intervals/calendar/preview",
        headers=headers,
        json={"op": "delete"},
    )
    assert preview.status_code == 200
    pid = preview.json()["pending_id"]
    n = preview.json()["count"]
    assert n >= 1

    deleted = {}

    def _fake_del(api_key, athlete_id, external_ids):
        deleted["ids"] = list(external_ids)
        return {"eventsDeleted": len(external_ids)}

    monkeypatch.setattr(main_mod, "delete_events_bulk", _fake_del)

    conf = c.post(
        "/v1/athlete/me/intervals/calendar/confirm",
        headers=headers,
        json={"pending_id": pid},
    )
    assert conf.status_code == 200
    assert conf.json()["deleted"] == n
    assert len(deleted["ids"]) == n


def test_build_block_note_external_ids():
    blocks = [
        {
            "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "title": "Base",
            "theme": "Z2",
            "start_date": "2026-09-28",
            "end_date": "2026-10-11",
            "weekly_hours": 8,
        }
    ]
    events = build_block_note_events(blocks)
    assert len(events) >= 2
    assert events[0]["category"] == "NOTE"
    assert events[0]["external_id"] == external_id_for_block_day(
        blocks[0]["id"], date(2026, 9, 28)
    )


def test_calendar_preview_requires_intervals(client):
    c, _ = client
    aid = _onboard(c)
    r = c.post(
        "/v1/athlete/me/intervals/calendar/preview",
        headers={"X-Athlete-Id": aid},
        json={"op": "push"},
    )
    assert r.status_code == 400
