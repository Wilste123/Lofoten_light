"""Pass 3: Sunday ritual coach-rapport, TP zip export, week compliance, chat intents."""

from __future__ import annotations

import io
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chat_service import (
    compliance_gap_reply_nb,
    user_requests_coach_report,
    user_requests_compliance_gap,
    user_requests_tp_export,
    user_requests_week_check,
)
from coach_report import sunday_ritual_payload
from tp_export import build_tp_export_zip, default_export_range, event_files
from week_analysis import build_week_compliance

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import config
import main as main_mod
from db import init_db, upsert_athlete_secrets


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
            "username": "william-pass3",
            "coach_display_name": "Rocky",
            "goal_text": "Lofoten",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["athlete"]["id"]


def test_intent_coach_report_and_tp_export():
    assert user_requests_coach_report("vis coach-rapport")
    assert user_requests_coach_report("søndagsrapport")
    assert user_requests_coach_report("TB rapport")
    assert not user_requests_coach_report("sjekk uka mi")
    assert user_requests_tp_export("eksporter til TP")
    assert user_requests_tp_export("Intervals til TrainingPeaks")
    assert user_requests_tp_export("last ned tp zip")
    assert not user_requests_tp_export("sync planen til intervals")
    assert user_requests_compliance_gap("hva mangler jeg")
    assert user_requests_compliance_gap("planlagt vs gjennomført")
    assert not user_requests_compliance_gap("sjekk uka mi")
    assert user_requests_week_check("sjekk uka mi")


def test_build_week_compliance_lists():
    mon = date(2026, 10, 20)
    sun = mon + timedelta(days=6)
    bundle = {
        "planned": [
            {
                "session_date": "2026-10-20",
                "name": "Z2",
                "discipline_label": "Sykkel",
                "training_status": "planned",
            },
            {
                "session_date": "2026-10-21",
                "name": "Terskel",
                "discipline_label": "Løp",
                "training_status": "planned",
            },
        ],
        "completed": [
            {
                "session_date": "2026-10-20",
                "name": "Z2 ride",
                "discipline_label": "Sykkel",
                "kind": "activity",
                "training_status": "completed",
            }
        ],
        "planned_not_done": [
            {
                "session_date": "2026-10-21",
                "name": "Terskel",
                "discipline_label": "Løp",
                "training_status": "planned_not_done",
            }
        ],
    }
    wc = build_week_compliance(bundle, week_start=mon, week_end=sun)
    assert wc["sessions_planned"] == 2
    assert wc["sessions_missed"] == 1
    assert wc["sessions_done"] == 1
    assert wc["compliance_pct"] == 50.0
    assert any("Terskel" in ln for ln in wc["missed_lines"])
    assert any("Z2" in ln for ln in wc["done_lines"])


def test_tp_export_zip_from_events():
    events = [
        {
            "id": 1,
            "type": "Ride",
            "category": "WORKOUT",
            "name": "Z2 75",
            "start_date_local": "2026-10-22T07:00:00",
            "moving_time": 4500,
            "icu_training_load": 60,
            "workout_doc": {
                "steps": [
                    {"duration": 600, "text": "WU", "power": {"units": "%ftp", "value": 55}},
                    {"duration": 3600, "text": "Z2", "power": {"units": "%ftp", "value": 70}},
                    {"duration": 300, "text": "CD", "power": {"units": "%ftp", "value": 50}},
                ]
            },
        },
        {
            "id": 2,
            "type": "WeightTraining",
            "category": "WORKOUT",
            "name": "ST04",
            "start_date_local": "2026-10-23T18:00:00",
            "moving_time": 2100,
            "description": "3x8 squats",
        },
        {
            "id": 3,
            "type": "Run",
            "category": "WORKOUT",
            "name": "Easy",
            "start_date_local": "2026-10-24T07:00:00",
            "moving_time": 2400,
            "workout_doc": {
                "steps": [{"duration": 2400, "text": "Easy", "pace": {"start": 78, "end": 82}}]
            },
        },
    ]
    blob, meta = build_tp_export_zip(events, start="2026-10-22", end="2026-10-31")
    assert meta["workouts"] == 3
    assert meta["zwo"] == 2
    assert meta["strength"] == 1
    assert meta["written_to_trainingpeaks"] is False
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = zf.namelist()
        assert "index.csv" in names
        assert "trainingdojo-import.csv" in names
        assert "README-TP-import.md" in names
        assert any(n.startswith("bike/") and n.endswith(".zwo") for n in names)
        assert any(n.startswith("run/") and n.endswith(".zwo") for n in names)


def test_sunday_ritual_includes_compliance():
    ritual = sunday_ritual_payload(
        None,
        week_compliance={
            "sessions_planned": 5,
            "sessions_done": 3,
            "compliance_pct": 60.0,
            "missed_lines": ["2026-10-21 · Terskel (Løp)"],
            "done_lines": ["2026-10-20 · Z2"],
            "note_nb": "NOTE teller ikke.",
        },
    )
    assert ritual["ritual"] is True
    assert "Planlagt vs gjennomført" in ritual["markdown"]
    assert "ukesopp" in ritual["markdown"].lower() or "ukesopp" in str(ritual.get("cta"))
    assert ritual["written_to_intervals"] is False


def test_compliance_gap_reply():
    text = compliance_gap_reply_nb(
        name="William",
        week_start="2026-10-20",
        week_end="2026-10-26",
        compliance={
            "sessions_planned": 4,
            "sessions_done": 2,
            "compliance_pct": 50.0,
            "missed_lines": ["2026-10-21 · Terskel"],
            "done_lines": ["2026-10-20 · Z2"],
            "note_nb": "NOTE ≠ trening.",
            "rolling_compliance_4w": {
                "sessions_planned": 16,
                "sessions_done": 12,
                "compliance_pct": 75.0,
            },
        },
        intervals_linked=True,
    )
    assert "2 / 4" in text
    assert "Terskel" in text
    assert "4 uker" in text


def test_readiness_ritual_endpoint(client):
    aid = _onboard(client)
    r = client.get("/v1/readiness", headers={"X-Athlete-Id": aid})
    assert r.status_code == 200
    body = r.json()
    assert "markdown" in body
    assert body.get("ritual") is True
    assert "cta" in body
    assert body.get("written_to_intervals") is False


def test_compliance_week_endpoint(client):
    aid = _onboard(client)
    fake = {
        "planned": [],
        "completed": [],
        "planned_not_done": [],
        "recent": [],
        "rolling_compliance_4w": {
            "sessions_planned": 0,
            "sessions_done": 0,
            "compliance_pct": None,
        },
    }
    with patch("main.list_sessions", return_value=fake):
        r = client.get("/v1/compliance/week", headers={"X-Athlete-Id": aid})
    assert r.status_code == 200
    body = r.json()
    assert body.get("available") is True
    assert "week_start" in body
    assert body.get("written_to_intervals") is False


def test_tp_export_zip_endpoint_requires_icu(client):
    aid = _onboard(client)
    r = client.get(
        "/v1/exports/tp-from-intervals.zip",
        headers={"X-Athlete-Id": aid},
    )
    assert r.status_code == 400


def test_tp_export_zip_endpoint_download(client):
    aid = _onboard(client)
    from db import db_session

    with db_session(config.get_db()) as conn:
        upsert_athlete_secrets(
            conn, aid, intervals_api_key="k", intervals_athlete_id="i1"
        )
    events = [
        {
            "id": 9,
            "type": "Ride",
            "category": "WORKOUT",
            "name": "Spin",
            "start_date_local": "2026-10-22T08:00:00",
            "moving_time": 3600,
            "workout_doc": {
                "steps": [{"duration": 3600, "text": "Z2", "power": {"units": "%ftp", "value": 70}}]
            },
        }
    ]
    with patch("intervals_calendar.fetch_events", return_value=events):
        r = client.get(
            "/v1/exports/tp-from-intervals.zip?start=2026-10-22&end=2026-10-28",
            headers={"X-Athlete-Id": aid},
        )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/zip")
    assert r.headers.get("X-Written-To-TrainingPeaks") == "false"
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert "index.csv" in zf.namelist()


def test_chat_coach_report_and_compliance(client):
    aid = _onboard(client)
    fake_bundle = {
        "planned": [
            {
                "session_date": date.today().isoformat(),
                "name": "Z2",
                "discipline_label": "Sykkel",
            }
        ],
        "completed": [],
        "planned_not_done": [
            {
                "session_date": date.today().isoformat(),
                "name": "Z2",
                "discipline_label": "Sykkel",
                "training_status": "planned_not_done",
            }
        ],
        "recent": [],
        "today": [],
        "upcoming": [],
    }
    with patch("main.list_sessions", return_value=fake_bundle):
        with patch(
            "main._sessions_bundle_for_athlete",
            return_value=fake_bundle,
        ):
            r = client.post(
                "/v1/chat",
                headers={"X-Athlete-Id": aid},
                json={"message": "coach-rapport"},
            )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("coach_report")
    assert body["coach_report"].get("ritual") is True
    assert body.get("written_to_intervals") is False

    with patch("main.list_sessions", return_value=fake_bundle):
        with patch(
            "main._sessions_bundle_for_athlete",
            return_value=fake_bundle,
        ):
            r2 = client.post(
                "/v1/chat",
                headers={"X-Athlete-Id": aid},
                json={"message": "hva mangler jeg"},
            )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2.get("week_compliance")
    assert "Z2" in body2["reply"] or body2["week_compliance"].get("sessions_missed") is not None


def test_chat_tp_export(client):
    aid = _onboard(client)
    from db import db_session

    with db_session(config.get_db()) as conn:
        upsert_athlete_secrets(
            conn, aid, intervals_api_key="k", intervals_athlete_id="i1"
        )
    events = [
        {
            "id": 1,
            "type": "Ride",
            "name": "Easy",
            "start_date_local": "2026-10-22T07:00:00",
            "moving_time": 3600,
            "workout_doc": {
                "steps": [{"duration": 3600, "text": "Z2", "power": {"units": "%ftp", "value": 70}}]
            },
        }
    ]
    with patch("intervals_calendar.fetch_events", return_value=events):
        r = client.post(
            "/v1/chat",
            headers={"X-Athlete-Id": aid},
            json={"message": "eksporter til TP"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("tp_export")
    assert body["tp_export"]["available"] is True
    assert body["tp_export"]["written_to_trainingpeaks"] is False
    assert "zip" in (body["tp_export"].get("download_path") or "")


def test_dashboard_includes_week_compliance(client):
    aid = _onboard(client)
    fake = {
        "planned": [
            {
                "session_date": date.today().isoformat(),
                "name": "Miss",
                "discipline_label": "Løp",
            }
        ],
        "completed": [],
        "planned_not_done": [
            {
                "session_date": date.today().isoformat(),
                "name": "Miss",
                "discipline_label": "Løp",
                "training_status": "planned_not_done",
            }
        ],
        "recent": [],
        "rolling_compliance_4w": {
            "sessions_planned": 4,
            "sessions_done": 2,
            "compliance_pct": 50.0,
        },
    }
    with patch("main.list_sessions", return_value=fake), patch(
        "main.resolve_period_training",
        return_value={
            "disciplines": [],
            "total_hours": 0,
            "activity_count": 0,
            "source": "none",
            "days": 14,
            "window": {},
            "note": "",
            "charts": {},
        },
    ), patch(
        "main.resolve_wellness_bundle",
        return_value={
            "sleep": {"available": False},
            "body": {"available": False},
            "load_wellness": {},
            "load_series": {},
            "fetch_error": False,
            "source": "none",
        },
    ), patch(
        "coach_report.fetch_tb_for_athlete",
        return_value={"available": False, "note": "test"},
    ):
        r = client.get("/v1/dashboard?period=14d", headers={"X-Athlete-Id": aid})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("week_compliance")
    assert data["week_compliance"].get("sessions_missed") == 1
    assert any("Miss" in ln for ln in data["week_compliance"].get("missed_lines") or [])


def test_default_export_range_two_weeks():
    start, end = default_export_range(today=date(2026, 10, 22))  # Wednesday
    assert start == "2026-10-19"  # Monday
    assert end == "2026-11-01"


def test_event_files_skips_target():
    row, dojo = event_files(
        {"category": "TARGET", "type": "Ride", "name": "CTL"}, "2026-10-01"
    )
    assert row is None and dojo is None
