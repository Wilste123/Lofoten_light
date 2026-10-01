"""Beta forecasts — Banister CTL/ATL projection, ACWR bands, no auto-apply."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from beta_forecasts import (
    CITATIONS,
    K_ATL,
    K_CTL,
    activity_tss,
    build_beta_forecasts,
    daily_tss_from_planned,
    ease_scenario,
    ewma_step,
    race_form_estimate,
    risk_band_from_acwr,
    run_ewma,
)
from ticker import ACWR_HARD, ACWR_SOFT

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import config
import main as main_mod
from db import init_db


def test_ewma_step_moves_toward_load():
    assert ewma_step(0.0, 100.0, K_CTL) == pytest.approx(100.0 * K_CTL)
    assert ewma_step(50.0, 50.0, K_ATL) == pytest.approx(50.0)


def test_run_ewma_tsb_and_planned_label():
    start = date(2026, 10, 1)
    end = date(2026, 10, 7)
    loads = {start.isoformat(): 80.0}
    pts = run_ewma(loads, start=start, end=end, ctl0=40.0, atl0=55.0)
    assert len(pts) == 7
    assert pts[0]["ctl"] > 40.0
    assert "tsb" in pts[0]
    assert pts[-1]["date"] == end.isoformat()


def test_activity_tss_prefers_icu_load():
    assert activity_tss({"icu_training_load": 72, "moving_time": 3600}) == 72.0
    # 1h → proxy 50
    assert activity_tss({"moving_time": 3600, "type": "Ride"}) == 50.0


def test_planned_tss_future_only():
    today = date(2026, 10, 15)
    sessions = [
        {"session_date": "2026-10-10", "duration_minutes": 60},  # past
        {"session_date": "2026-10-16", "duration_minutes": 60, "sport": "bike"},
        {"session_date": "2026-10-17", "tss": 90},
    ]
    buckets = daily_tss_from_planned(
        sessions, today, today + timedelta(days=7), today=today
    )
    assert "2026-10-10" not in buckets or buckets.get("2026-10-10", 0) == 0.0
    assert buckets["2026-10-16"] == 50.0
    assert buckets["2026-10-17"] == 90.0
    # Past planned must not inflate future projection window
    assert all(
        (date.fromisoformat(k) >= today) for k in buckets
    )

def test_acwr_risk_bands_match_ticker():
    assert risk_band_from_acwr(1.0)["band"] == "ok"
    soft = risk_band_from_acwr(ACWR_SOFT)
    assert soft["band"] == "elevated"
    hard = risk_band_from_acwr(ACWR_HARD)
    assert hard["band"] == "high"
    assert "diagnose" not in hard["note_nb"].lower() or "ikke" in hard["note_nb"].lower()


def test_race_form_honest_confidence():
    r = race_form_estimate(
        ctl=55,
        atl=60,
        tsb=-5,
        goal_race_date="2027-08-20",
        projected_ctl_at_goal=70,
        data_quality="wellness+planned",
        today=date(2026, 10, 1),
    )
    assert r["days_to_goal"] and r["days_to_goal"] > 200
    assert r["confidence"] in ("lav", "medium", "høy")
    assert r["auto_apply"] is False
    assert "fasit" in r["summary_nb"].lower() or "Banister" in r["summary_nb"]


def test_ease_scenario_never_auto_applies():
    today = date(2026, 10, 1)
    loads = {
        (today + timedelta(days=i)).isoformat(): 60.0 for i in range(14)
    }
    sc = ease_scenario(
        planned_loads=loads,
        today=today,
        horizon_days=14,
        ctl0=50.0,
        atl0=55.0,
        fraction=0.8,
    )
    assert sc["auto_apply"] is False
    assert sc["proposal_only"] is True
    assert sc["human_coach_confirm"] is True
    assert sc["eased_end"]["ctl"] <= sc["baseline_end"]["ctl"] + 0.5


def test_build_beta_forecasts_offline_no_invented_ctl():
    athlete = {
        "goal_race_date": "2027-08-20",
        "display_name": "Test",
    }
    planned = [
        {
            "session_date": (date.today() + timedelta(days=1)).isoformat(),
            "duration_minutes": 90,
            "sport": "bike",
        }
    ]
    payload = build_beta_forecasts(
        athlete=athlete,
        secrets=None,
        planned_sessions=planned,
        today=date.today(),
        lookback_days=30,
        horizon_days=14,
    )
    assert payload["experimental"] is True
    assert payload["auto_apply"] is False
    assert payload["human_coach_confirm_required"] is True
    assert payload["truth"]["planned"] == "planned_sessions"
    assert isinstance(payload["citations"], list) and len(payload["citations"]) >= 4
    assert any(c["id"] == "ioc2016" for c in CITATIONS)
    # Without wellness/activities, no invented high CTL
    charts = payload["charts"]["ctl_atl_tsb"]
    assert charts["label_future_nb"].lower().find("planlagt") >= 0


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "beta.db"
    athletes = tmp_path / "athletes"
    athletes.mkdir()
    monkeypatch.setattr(config, "DATABASE_PATH", db)
    monkeypatch.setattr(config, "ATHLETES_DATA_DIR", athletes)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config, "DATABASE_URL", "")
    monkeypatch.setenv("DATABASE_PATH", str(db))
    init_db(db)
    with TestClient(main_mod.app) as c:
        yield c, db


def test_beta_api_endpoint(client):
    c, _db = client
    r = c.post(
        "/v1/onboarding",
        json={
            "display_name": "Beta",
            "username": "beta-user",
            "coach_display_name": "Ole",
            "coach_personality": "direkte",
            "accent_color": "#1a6b4a",
            "goal_text": "Lofoten",
            "goal_race_date": "2027-08-20",
        },
    )
    assert r.status_code == 200, r.text
    aid = r.json()["athlete"]["id"]
    fr = c.get("/v1/beta/forecasts", headers={"X-Athlete-Id": aid})
    assert fr.status_code == 200, fr.text
    data = fr.json()
    assert data["experimental"] is True
    assert data["auto_apply"] is False
    assert "overload_risk" in data
    assert "race_form" in data
    assert data["charts"]["ctl_atl_tsb"]["label_future_nb"]
    assert len(data["citations"]) >= 3
