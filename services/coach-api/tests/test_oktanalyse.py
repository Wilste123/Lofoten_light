"""Øktanalyse + TB readiness charts (pass beyond agent chat)."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chat_service import (
    user_requests_session_analysis,
    user_requests_week_check,
)
from readiness_charts import build_tb_trend_series, components_bar_payload
from session_analysis import (
    analyze_activity_payload,
    analyze_intervals,
    build_graph_series,
    downsample_series,
    intensity_distribution,
    opv_feedback_nb,
    pick_latest_activity_session,
    resolve_activity_id,
    streams_to_map,
)

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
            "username": "william-oktanalyse",
            "coach_display_name": "Rocky",
            "goal_text": "Lofoten",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["athlete"]["id"]


def test_intent_session_analysis_not_week():
    assert user_requests_session_analysis("analyser dagens økt")
    assert user_requests_session_analysis("øktanalyse")
    assert user_requests_session_analysis("analyze my workout")
    assert not user_requests_session_analysis("analyser uken")
    assert user_requests_week_check("analyser uken")
    assert not user_requests_session_analysis("sjekk uka mi")
    assert not user_requests_session_analysis("coach-rapport")


def test_resolve_activity_id():
    assert resolve_activity_id("act:i123") == "i123"
    assert resolve_activity_id({"kind": "activity", "external_id": "abc", "id": "act:abc"}) == "abc"
    assert resolve_activity_id({"kind": "event", "id": "evt:9", "external_id": "x"}) is None
    assert resolve_activity_id("plain-id") == "plain-id"


def test_downsample_and_graph():
    series = list(range(500))
    ds = downsample_series(series, max_points=50)
    assert len(ds) == 50
    assert ds[0] == 0.0
    sm = streams_to_map(
        [
            {"type": "watts", "data": [100, 200, 180, 220]},
            {"type": "heartrate", "data": [120, 140, 145, 150]},
            {"type": "time", "data": [0, 1, 2, 3]},
        ]
    )
    g = build_graph_series(sm)
    assert g["available"] is True
    assert g["has_watts"] and g["has_hr"]
    assert len(g["series"]) >= 2


def test_analyze_intervals_consistency():
    laps = [
        {"average_watts": 250, "moving_time": 180, "target_watts": 250, "name": "1"},
        {"average_watts": 255, "moving_time": 180, "target_watts": 250, "name": "2"},
        {"average_watts": 248, "moving_time": 180, "target_watts": 250, "name": "3"},
        {"type": "REST", "average_watts": 80, "moving_time": 60},
    ]
    out = analyze_intervals(laps, sport="bike")
    assert out["available"] is True
    assert out["count"] == 3
    assert out["power_cv_pct"] is not None and out["power_cv_pct"] < 5
    assert "Traff mål" in (out["verdict_nb"] or "")


def test_intensity_distribution_from_watts_ftp():
    streams = {"watts": [100] * 50 + [200] * 30 + [280] * 20}
    dist = intensity_distribution({}, streams, ftp=250)
    assert dist["available"] is True
    assert dist["source"] == "watts_vs_ftp"
    assert dist["easy_pct"] is not None
    assert dist["hard_pct"] is not None


def test_analyze_activity_payload_opv():
    activity = {
        "id": "act1",
        "name": "4x8 Z4",
        "type": "Ride",
        "start_date_local": "2026-10-26T07:00:00",
        "moving_time": 3600,
        "icu_training_load": 72,
        "icu_intensity": 0.82,
        "average_watts": 210,
        "average_heartrate": 148,
        "icu_intervals": [
            {"average_watts": 260, "moving_time": 480, "target_watts": 255},
            {"average_watts": 258, "moving_time": 480, "target_watts": 255},
            {"type": "REST", "average_watts": 90, "moving_time": 180},
        ],
        "icu_zone_times": [600, 1200, 900, 600, 300],
    }
    streams = [
        {"type": "watts", "data": [200 + (i % 20) for i in range(120)]},
        {"type": "heartrate", "data": [140 + (i % 15) for i in range(120)]},
        {"type": "time", "data": list(range(120))},
    ]
    result = analyze_activity_payload(activity=activity, streams=streams, ftp=280)
    assert result["available"] is True
    assert result["written_to_intervals"] is False
    assert result["graph"]["available"] is True
    assert result["intervals"]["available"] is True
    assert result["distribution"]["available"] is True
    fb = result["feedback_nb"]
    assert "4x8" in fb or "Z4" in fb
    assert "Signing" in fb or "signing" in fb.lower() or "Signing:" in fb
    assert "Neste:" in fb


def test_pick_latest_prefers_today():
    bundle = {
        "completed": [
            {
                "id": "act:old",
                "kind": "activity",
                "date": "2026-10-20",
                "start_date_local": "2026-10-20T08:00:00",
                "external_id": "old",
            },
            {
                "id": "act:today",
                "kind": "activity",
                "date": "2026-10-26",
                "start_date_local": "2026-10-26T09:00:00",
                "external_id": "today",
            },
        ]
    }
    picked = pick_latest_activity_session(bundle, prefer_date="2026-10-26")
    assert picked["external_id"] == "today"


def test_components_bar_payload():
    bars = components_bar_payload(
        [
            {"label": "Søvn", "score": 80, "detail": "ok"},
            {"label": "Load", "score": 55},
            {"label": "skip", "score": None},
        ]
    )
    assert bars["available"] is True
    assert len(bars["bars"]) == 2


def test_build_tb_trend_soft_empty():
    out = build_tb_trend_series([], days=7, today=date(2026, 10, 26))
    assert out["available"] is False
    assert out["written_to_intervals"] is False


def test_api_analysis_latest_without_intervals(client):
    aid = _onboard(client)
    r = client.get("/v1/analysis/latest", headers={"X-Athlete-Id": aid})
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False
    assert body["written_to_intervals"] is False
    assert "Intervals" in (body.get("note") or body.get("feedback_nb") or "")


def test_api_session_analysis_mocked(client):
    aid = _onboard(client)
    fake = {
        "available": True,
        "summary": {"name": "Test", "date": "2026-10-26"},
        "graph": {"available": False, "series": []},
        "intervals": {"available": False},
        "distribution": {"available": False},
        "feedback_nb": "[Test]\nNeste: én ting.",
        "written_to_intervals": False,
        "activity_id": "x1",
        "session_id": "act:x1",
    }
    with patch(
        "session_analysis.analyze_session_for_athlete", return_value=fake
    ):
        r = client.get(
            "/v1/sessions/act:x1/analysis",
            headers={"X-Athlete-Id": aid},
        )
    assert r.status_code == 200
    assert r.json()["feedback_nb"].startswith("[Test]")


def test_api_readiness_charts_soft(client):
    aid = _onboard(client)
    r = client.get("/v1/readiness/charts?days=7", headers={"X-Athlete-Id": aid})
    assert r.status_code == 200
    body = r.json()
    assert body["written_to_intervals"] is False
    assert "components_chart" in body


def test_chat_session_analysis_intent(client):
    aid = _onboard(client)
    fake = {
        "available": True,
        "summary": {"name": "Z2", "date": "2026-10-26"},
        "graph": {"available": False},
        "intervals": {"available": False},
        "distribution": {"available": False},
        "feedback_nb": "[Z2]\nStruktur: jevn.\nNeste: rolig.",
        "written_to_intervals": False,
    }
    with patch(
        "session_analysis.analyze_session_for_athlete", return_value=fake
    ):
        out = main_mod._chat_session_analysis(
            aid=aid,
            athlete={"display_name": "William", "ftp": 280},
            secrets={},
            sessions_bundle={"completed": [], "recent": []},
            overview={"app_plan": {}},
            intervals_ok=False,
        )
    assert "Øktanalyse" in out["reply"] or "Z2" in out["reply"]
    assert out["session_analysis"]["available"] is True
    assert out["written_to_intervals"] is False
    assert out["confirm_required"] is False


def test_opv_feedback_mentions_swim_limiter():
    fb = opv_feedback_nb(
        summary={"name": "CSS", "sport": "swim", "duration_min": 40, "load": 40},
        intervals={"available": False},
        distribution={"available": False},
        graph={"available": False},
    )
    assert "Svøm" in fb or "svøm" in fb.lower()
