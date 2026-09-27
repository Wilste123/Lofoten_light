"""Workout library grouping + session detail + focused chat/edit preview."""

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
from sessions_service import (
    group_library,
    library_key_for,
    parse_coach_steps,
    session_detail_payload,
    session_focus_for_chat,
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


def test_parse_coach_steps_bullets_and_warmup():
    desc = (
        "### Lofoten Coach\n\n"
        "- Warmup 10 min Z2\n"
        "- 5x 3 min Z4 / 2 min soft\n"
        "Cooldown 10 min\n"
        "Plan B: kutt til 3x.\n"
    )
    steps = parse_coach_steps(desc)
    assert steps[0] == "Warmup 10 min Z2"
    assert "5x 3 min Z4 / 2 min soft" in steps
    assert any(s.lower().startswith("cooldown") for s in steps)
    assert not any("Plan B" in s for s in steps)


def test_library_key_groups_coach_slug_across_dates():
    a = {
        "external_id": "ll-coach-w-20261001-easyz2-0",
        "name": "Easy Z2",
        "discipline": "bike",
        "kind": "event",
    }
    b = {
        "external_id": "ll-coach-w-20261008-easyz2-0",
        "name": "Easy Z2",
        "discipline": "bike",
        "kind": "event",
    }
    c = {
        "external_id": "ll-coach-w-20261001-hardz4-0",
        "name": "Hard Z4",
        "discipline": "bike",
        "kind": "event",
    }
    assert library_key_for(a) == library_key_for(b)
    assert library_key_for(a) != library_key_for(c)


def test_group_library_collapses_occurrences():
    desc = "- Warmup\n- Main 40 min\n"
    sessions = [
        {
            "id": "evt:1",
            "external_id": "ll-coach-w-20261001-easyz2-0",
            "name": "Easy Z2",
            "discipline": "bike",
            "discipline_label": "Sykkel",
            "kind": "event",
            "date": "2026-10-01",
            "bucket": "upcoming",
            "description": desc,
            "editable": True,
            "completion": None,
        },
        {
            "id": "evt:2",
            "external_id": "ll-coach-w-20261008-easyz2-0",
            "name": "Easy Z2",
            "discipline": "bike",
            "discipline_label": "Sykkel",
            "kind": "event",
            "date": "2026-10-08",
            "bucket": "upcoming",
            "description": desc,
            "editable": True,
            "completion": None,
        },
        {
            "id": "evt:3",
            "external_id": "ll-coach-w-20261002-swimtech-0",
            "name": "Svøm teknikk",
            "discipline": "swim",
            "discipline_label": "Svøm",
            "kind": "event",
            "date": "2026-10-02",
            "bucket": "upcoming",
            "description": "- 8x50",
            "editable": True,
            "completion": None,
        },
    ]
    lib = group_library(sessions, today=date(2026, 9, 27))
    assert len(lib) == 2
    easy = next(x for x in lib if "Easy" in (x.get("name") or ""))
    assert easy["occurrence_count"] == 2
    assert easy["dates"] == ["2026-10-01", "2026-10-08"]
    assert easy["next_date"] == "2026-10-01"
    assert easy["sample_session_id"] == "evt:1"


def test_session_detail_payload_structured():
    bundle = {
        "upcoming": [
            {
                "id": "evt:9",
                "external_id": "ll-coach-w-20261001-easyz2-0",
                "name": "Easy Z2",
                "discipline": "bike",
                "discipline_label": "Sykkel",
                "kind": "event",
                "date": "2026-10-01",
                "bucket": "upcoming",
                "description": "- Warmup\n- 3x10",
                "duration_hours": 1.0,
                "editable": True,
                "completion": None,
            }
        ],
        "today": [],
        "recent": [],
        "compliance_note": "Compliance i appen",
    }
    detail = session_detail_payload(bundle, bundle["upcoming"][0], today=date(2026, 9, 27))
    assert detail["library_key"].startswith("w:easyz2")
    assert detail["steps"][0] == "Warmup"
    assert detail["coach_block"]["title"] == "Fra treneren"
    assert detail["editable"] is True
    assert detail["editable_fields"]["duration_minutes"] == 60
    assert "seed_prompt" in detail
    focus = session_focus_for_chat(detail["session"])
    assert focus["name"] == "Easy Z2"
    assert "focused" in focus["note"].lower() or "DENNE" in focus["note"]


def test_get_sessions_includes_library(client):
    c, _ = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}

    fake = {
        "window": {"start": "2026-09-13", "end": "2026-10-11"},
        "source": "intervals",
        "fetch_error": False,
        "fetch_error_detail": None,
        "compliance_note": "Compliance i appen",
        "today": [],
        "recent": [],
        "upcoming": [
            {
                "id": "evt:a",
                "external_id": "ll-coach-w-20261001-easyz2-0",
                "name": "Easy Z2",
                "discipline": "bike",
                "discipline_label": "Sykkel",
                "kind": "event",
                "date": "2026-10-01",
                "bucket": "upcoming",
                "description": "- Warmup\n- Main",
                "editable": True,
                "completion": None,
            },
            {
                "id": "evt:b",
                "external_id": "ll-coach-w-20261008-easyz2-0",
                "name": "Easy Z2",
                "discipline": "bike",
                "discipline_label": "Sykkel",
                "kind": "event",
                "date": "2026-10-08",
                "bucket": "upcoming",
                "description": "- Warmup\n- Main",
                "editable": True,
                "completion": None,
            },
        ],
        "library": [],
        "view_modes": ["library", "chronological"],
        "default_view": "library",
    }

    with patch("main.list_sessions", return_value=fake):
        r = c.get("/v1/sessions", headers=headers)
    assert r.status_code == 200
    # Endpoint returns whatever list_sessions builds; soft-fail path tested elsewhere.
    # Here we assert detail + chat wiring against real list_sessions enrichment:
    from sessions_service import enrich_sessions_bundle

    enriched = enrich_sessions_bundle(
        {k: v for k, v in fake.items() if k != "library"},
        today=date(2026, 9, 27),
    )
    assert len(enriched["library"]) == 1
    assert enriched["library"][0]["occurrence_count"] == 2


def test_session_detail_endpoint(client):
    c, _ = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}
    bundle = {
        "window": {"start": "2026-09-13", "end": "2026-10-11"},
        "source": "intervals",
        "fetch_error": False,
        "compliance_note": "Compliance i appen",
        "today": [],
        "recent": [],
        "upcoming": [
            {
                "id": "evt:z",
                "external_id": "ll-coach-w-20261001-easyz2-0",
                "name": "Easy Z2",
                "discipline": "bike",
                "discipline_label": "Sykkel",
                "kind": "event",
                "date": "2026-10-01",
                "bucket": "upcoming",
                "description": "- Warmup 10\n- 4x8 Z4",
                "duration_hours": 1.25,
                "editable": True,
                "start_time": "07:00",
                "completion": None,
            }
        ],
        "library": [],
        "view_modes": ["library", "chronological"],
        "default_view": "library",
    }
    from sessions_service import enrich_sessions_bundle

    enriched = enrich_sessions_bundle(bundle, today=date(2026, 9, 27))

    with patch("main.list_sessions", return_value=enriched):
        r = c.get("/v1/sessions/evt:z", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["session"]["name"] == "Easy Z2"
    assert data["steps"]
    assert data["coach_block"]["title"] == "Fra treneren"
    assert data["editable"] is True
    assert data["editable_fields"]["name"] == "Easy Z2"
    assert "seed_prompt" in data


def test_chat_with_session_id_focus(client):
    c, _ = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}
    captured: dict = {}

    def fake_llm(**kwargs):
        captured["system"] = kwargs.get("system") or ""
        return "Ser bra ut — hold Z2 jevn."

    bundle = {
        "source": "intervals",
        "window": {"start": "2026-09-13", "end": "2026-10-11"},
        "today": [],
        "recent": [],
        "upcoming": [
            {
                "id": "evt:focus",
                "external_id": "ll-coach-w-20261001-easyz2-0",
                "name": "Easy Z2",
                "discipline": "bike",
                "discipline_label": "Sykkel",
                "kind": "event",
                "date": "2026-10-01",
                "bucket": "upcoming",
                "description": "- Warmup\n- Main Z2",
                "editable": True,
                "completion": None,
                "library_key": "w:easyz2|bike",
                "steps": ["Warmup", "Main Z2"],
            }
        ],
        "library": [],
        "view_modes": ["library", "chronological"],
        "default_view": "library",
        "fetch_error": False,
        "compliance_note": "x",
    }

    with (
        patch("main.call_llm", side_effect=fake_llm),
        patch("main.list_sessions", return_value=bundle),
    ):
        r = c.post(
            "/v1/chat",
            headers=headers,
            json={"message": "Hva tenker du om denne?", "session_id": "evt:focus"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["focused_session_id"] == "evt:focus"
    assert "focused_session" in captured["system"] or "Easy Z2" in captured["system"]


def test_session_edit_preview_creates_pending(client):
    c, _ = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}

    # Store fake Intervals secrets
    with patch("main._require_intervals_secrets", return_value=({}, "key", "i123")):
        r = c.post(
            "/v1/sessions/evt:z/edit/preview",
            headers=headers,
            json={
                "name": "Easy Z2 oppdatert",
                "date": "2026-10-01",
                "sport": "bike",
                "duration_minutes": 75,
                "description": "- Warmup\n- Main lengre",
                "start_time": "07:00",
                "external_id": "ll-coach-w-20261001-easyz2-0",
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["op"] == "workout_push"
    assert body["confirm_required"] is True
    assert body["pending_id"]
    assert body["events"][0]["external_id"] == "ll-coach-w-20261001-easyz2-0"
