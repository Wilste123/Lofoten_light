"""Pass 2: dashboard TB strip, session prescriptions, ICU vs app compare, coach-report."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chat_service import user_requests_intervals_review
from coach_report import format_tb_report_markdown, recomputable_from_rows
from sessions_service import session_detail_payload
from week_analysis import compare_icu_vs_app_nb, session_plan_b_and_risk


pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import config
import main as main_mod
from db import init_db


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
        yield c


def _onboard(c) -> str:
    r = c.post(
        "/v1/onboarding",
        json={
            "display_name": "William",
            "username": "william-pass2",
            "coach_display_name": "Rocky",
            "goal_text": "Lofoten",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["athlete"]["id"]


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


def test_compare_intent_regex():
    assert user_requests_intervals_review("sammenlign app vs Intervals-kalender")
    assert user_requests_intervals_review("app mot ICU denne uka")
    assert user_requests_intervals_review("kalender-sannhet")
    assert user_requests_intervals_review("avvik mellom plan og intervals")
    assert not user_requests_intervals_review("sync planen til intervals")


def test_compare_icu_vs_app_buckets():
    merged = [
        {
            "session_date": "2026-10-20",
            "name": "Z2",
            "sport": "bike",
            "sync_status": "synced",
            "source_kind_nb": "Coach",
            "description": "Warmup:\n- 10 min\nMain:\n- 60 min Z2\nCooldown:\n- 5 min\n",
        },
        {
            "session_date": "2026-10-21",
            "name": "App-only terskel",
            "sport": "run",
            "sync_status": "planned_not_synced",
            "source_kind_nb": "App",
            "description": "Main:\n- 5x3\nPlan B: kutt til 3x3\n",
        },
        {
            "session_date": "2026-10-21",
            "name": "ICU utkast SS",
            "sport": "bike",
            "sync_status": "intervals_only",
            "source_kind_nb": "Manuell",
        },
    ]
    cmp = compare_icu_vs_app_nb(
        merged,
        week_start="2026-10-20",
        week_end="2026-10-26",
        intervals_linked=True,
    )
    assert cmp["counts"]["synced"] == 1
    assert cmp["counts"]["app_only"] == 1
    assert cmp["counts"]["icu_only"] == 1
    assert cmp["drift_lines"]
    assert any("Matched" in ln or "matched" in ln.lower() for ln in cmp["reply_lines"])
    assert cmp["prescriptions"]
    assert cmp["plan_b"]


def test_session_plan_b_and_prescription_in_detail():
    session = {
        "id": "ps:1",
        "external_id": "ll-coach-w-20261010-bike-0",
        "name": "6x5",
        "date": "2026-10-10",
        "discipline": "bike",
        "discipline_label": "Sykkel",
        "kind": "event",
        "bucket": "upcoming",
        "description": (
            "Warmup:\n- 15 min Z2\n"
            "Main:\n- 6x5 min terskel\n"
            "Cooldown:\n- 10 min\n"
            "Plan B: 4x5 hvis sliten\n"
            "Ukerisiko: for mye terskel\n"
        ),
        "editable": True,
        "completion": None,
    }
    bundle = {
        "upcoming": [session],
        "planned": [session],
        "recent": [],
        "completed": [],
        "library": [],
    }
    detail = session_detail_payload(bundle, session, today=date(2026, 10, 9))
    assert detail.get("prescription_nb")
    assert "6x5" in detail["prescription_nb"] or "Oppvarming" in detail["prescription_nb"]
    assert detail.get("plan_b")
    assert detail.get("risk")
    meta = session_plan_b_and_risk(session)
    assert meta["plan_b"]
    assert meta["risk"]


def test_coach_report_markdown_from_rows():
    report = recomputable_from_rows(
        _wellness_days(),
        [
            {
                "kind": "activity",
                "start_date_local": "2026-10-15T17:00:00",
                "training_load": 100,
                "duration_hours": 1.0,
                "type": "Run",
            }
        ],
    )
    assert report["available"] is True
    assert "TB-Score" in report["markdown"]
    md = format_tb_report_markdown(report["tb"])
    assert "Komponenter" in md or "TB-Score" in md


def test_readiness_endpoint_soft_without_icu(client):
    c = client
    aid = _onboard(c)
    r = c.get("/v1/readiness", headers={"X-Athlete-Id": aid})
    assert r.status_code == 200
    data = r.json()
    assert data["available"] is False
    assert data["written_to_intervals"] is False
    assert "markdown" in data


def test_dashboard_includes_readiness_strip(client):
    c = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}

    fake_strip = {
        "tb": {
            "available": True,
            "tb_score": 70,
            "band": "gul",
            "plan_b_nb": "Plan B: Z2",
            "recommendation": "Lett",
            "tsb": -10,
            "note": None,
        },
        "week": {
            "week_start": "2026-10-20",
            "week_end": "2026-10-26",
            "sessions_planned": 5,
            "sessions_done": 2,
            "compliance_pct": 40.0,
        },
        "cta_nb": "Spør Coach",
        "written_to_intervals": False,
    }

    with patch("main.resolve_period_training") as pt, patch(
        "main.resolve_wellness_bundle"
    ) as wl, patch("main.list_sessions") as ls, patch(
        "coach_report.readiness_dashboard_strip", return_value=fake_strip
    ):
        pt.return_value = {
            "disciplines": [],
            "total_hours": 0,
            "activity_count": 0,
            "source": "none",
            "days": 14,
            "window": {},
            "note": "",
            "charts": {},
        }
        wl.return_value = {
            "sleep": {"available": False},
            "body": {"available": False},
            "load_wellness": {},
            "load_series": {},
            "fetch_error": False,
            "source": "none",
        }
        ls.return_value = {
            "planned": [],
            "completed": [],
            "recent": [],
            "planned_not_done": [],
            "rolling_compliance_4w": None,
        }
        r = c.get("/v1/dashboard?period=14d", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("readiness")
    assert data["readiness"]["tb"]["tb_score"] == 70
    assert data["readiness"]["week"]["sessions_planned"] == 5
