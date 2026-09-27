"""Plan sync workouts via CLI builder + knowledge templates."""

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
from db import db_session, init_db, upsert_athlete_secrets
from plan_workouts import (
    build_plan_sync_bundle,
    build_plan_week_icu_events,
    knowledge_paths_for_workouts,
    signals_from_athlete,
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
        yield c, athletes, db


def _onboard(c) -> str:
    r = c.post(
        "/v1/onboarding",
        json={
            "display_name": "Testa",
            "username": "testa-planw",
            "coach_display_name": "Rocky",
            "goal_text": "Triathlon comeback",
            "injury_notes": "",
            "notes": "tidligere syklist comeback etter pause",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["athlete"]["id"]


def test_knowledge_paths_include_ukemaler_and_conditional():
    paths = knowledge_paths_for_workouts(
        {
            "goal_text": "Lofoten half",
            "notes": "nybegynner aldri trent",
            "injury_notes": "",
        }
    )
    assert "coach/ukemaler.md" in paths
    assert "triathlon/periodisering-mot-2027.md" in paths
    assert "svom/nybegynner-til-triatlet.md" in paths


def test_builder_emits_zwo_and_planned_shape():
    blocks = [
        {
            "id": "b1",
            "title": "Re-etablering",
            "theme": "Kontakt alle ben",
            "start_date": "2026-09-28",
            "end_date": "2026-10-25",
            "weekly_hours": 8.5,
        }
    ]
    events = build_plan_week_icu_events(
        blocks,
        signals={"returning": True, "beginner": False, "injury": False},
        weeks=1,
        today=date(2026, 9, 28),
    )
    assert len(events) >= 5
    assert all(e["category"] == "WORKOUT" for e in events)
    assert all(str(e["external_id"]).startswith("ll-coach-w-") for e in events)
    # At least one bike ZWO attached via CLI builder
    with_zwo = [e for e in events if e.get("file_contents") and e.get("filename")]
    assert len(with_zwo) >= 1
    assert any("Ride" == e.get("type") for e in events)
    # Run/swim get planned Intervals syntax (description enriched)
    runish = [e for e in events if e.get("type") == "Run"]
    assert runish
    assert "###" in (runish[0].get("description") or "") or "Warmup" in (
        runish[0].get("description") or ""
    )


def test_beginner_differs_from_injury_templates():
    blocks = [
        {
            "id": "b1",
            "title": "Grunnlag",
            "theme": "etablering",
            "start_date": "2026-09-28",
            "end_date": "2026-11-01",
            "weekly_hours": 4,
        }
    ]
    beg = build_plan_week_icu_events(
        blocks,
        signals={"beginner": True},
        weeks=1,
        today=date(2026, 9, 28),
        athlete={"display_name": "Ada", "injury_notes": ""},
    )
    inj = build_plan_week_icu_events(
        blocks,
        signals={"injury": True, "beginner": False},
        weeks=1,
        today=date(2026, 9, 28),
        athlete={
            "display_name": "William",
            "injury_notes": "isjas og ryggplager",
        },
    )
    beg_names = {e["name"] for e in beg}
    inj_names = {e["name"] for e in inj}
    assert beg_names != inj_names
    assert any("prehab" in n.lower() or "ST04" in n or "isjas" in n.lower() for n in inj_names)


def test_bundle_includes_notes_and_workouts():
    blocks = [
        {
            "id": "b1",
            "title": "Base",
            "theme": "base",
            "start_date": "2026-09-28",
            "end_date": "2026-10-25",
            "weekly_hours": 8,
        }
    ]
    bundle = build_plan_sync_bundle(
        blocks,
        athlete={"notes": "comeback etter pause", "goal_text": "triatlon"},
        weeks=2,
        today=date(2026, 9, 28),
    )
    assert bundle["workouts_count"] >= 8
    assert bundle["notes_count"] >= 1
    assert bundle["zwo_count"] >= 1
    assert bundle["builder"].endswith("build_workout_event")
    assert "coach/ukemaler.md" in bundle["knowledge_paths"]


def test_calendar_preview_push_uses_builder(client, monkeypatch):
    c, _athletes, db = client
    aid = _onboard(c)
    headers = {"X-Athlete-Id": aid}
    with db_session(db) as conn:
        upsert_athlete_secrets(
            conn, aid, intervals_api_key="k", intervals_athlete_id="i1"
        )

    created = c.post(
        "/v1/athlete/me/plan-blocks",
        headers=headers,
        json={
            "title": "Base 1",
            "theme": "Re-etablering kontakt",
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
    assert body["workouts_count"] >= 5
    assert body["notes_count"] >= 1
    assert body["zwo_count"] >= 1
    assert any(e.get("category") == "WORKOUT" for e in body["events"])
    assert any(
        str(e.get("external_id") or "").startswith("ll-coach-w-") for e in body["events"]
    )

    captured = {}

    def _fake_post(api_key, athlete_id, events, **kwargs):
        captured["events"] = events
        return {"count": len(events)}

    monkeypatch.setattr(main_mod, "post_events_bulk", _fake_post)
    conf = c.post(
        "/v1/athlete/me/intervals/calendar/confirm",
        headers=headers,
        json={"pending_id": body["pending_id"]},
    )
    assert conf.status_code == 200, conf.text
    assert conf.json()["pushed"] == body["count"]
    assert any(e.get("category") == "WORKOUT" for e in captured["events"])
    assert any(e.get("file_contents") for e in captured["events"])


def test_setup_preview_survives_missing_workout_builder(client, monkeypatch):
    """Both fresh + restart hit this: builder ImportError must not 500 preview."""
    c, *_ = client

    def _boom(*, module_file=None):
        raise ImportError(
            "Kunne ikke importere scripts/intervals_push_calendar.build_workout_event "
            "(sjekk at workouts/ + scripts er med i image). Sist feil: None"
        )

    monkeypatch.setattr(
        "plan_workouts._import_build_workout_event",
        _boom,
    )
    # Fresh-user shaped payload (minimal draft, like after short chat)
    preview = c.post(
        "/v1/setup/plan/preview",
        json={
            "display_name": "Ada",
            "username": "ada-degraded",
            "goal_text": "5k",
            "background_notes": "nybegynner",
            "weekly_hours_target": 4,
            "enrich_with_llm": False,
        },
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert len(body["plan_blocks"]) >= 2
    assert body["overview_md"]
    sync = body["intervals_sync"]
    assert sync["kind"] == "calendar_notes_only_degraded"
    assert sync.get("error")
    assert "import" in sync["error"].lower() or "workouts" in sync["error"].lower()
    assert sync["workouts_count"] == 0
    assert sync["notes_count"] >= 1


def test_setup_preview_after_reset_and_fresh_empty_draft(client):
    """Nullstill + empty restart draft, and brand-new empty draft, both preview OK."""
    c, *_ = client
    # Fresh empty-ish draft (user clicks Forhåndsvis with little chat)
    fresh = c.post(
        "/v1/setup/plan/preview",
        json={
            "display_name": "Ny",
            "username": "ny-preview",
            "coach_display_name": "Rocky",
            "enrich_with_llm": False,
        },
    )
    assert fresh.status_code == 200, fresh.text
    assert len(fresh.json()["plan_blocks"]) >= 2

    # Confirm → reset → preview with account-only draft (restart UI)
    filled = c.post(
        "/v1/setup/plan/preview",
        json={
            "display_name": "Bo",
            "username": "bo-restart",
            "goal_text": "comeback halv",
            "background_notes": "tidligere syklist",
            "weekly_hours_target": 8,
            "enrich_with_llm": False,
        },
    )
    assert filled.status_code == 200
    conf = c.post(
        "/v1/setup/confirm",
        json={
            "display_name": "Bo",
            "username": "bo-restart",
            "coach_display_name": "Rocky",
            "goal_text": "comeback halv",
            "weekly_hours_target": 8,
            "plan_blocks": filled.json()["plan_blocks"],
            "athlete_patch": filled.json()["athlete_patch"],
            "prepare_intervals_sync": False,
        },
    )
    assert conf.status_code == 200, conf.text
    aid = conf.json()["athlete"]["id"]
    reset = c.post(
        "/v1/athlete/me/setup/reset",
        headers={"X-Athlete-Id": aid},
        json={"acknowledge_wipe": True, "confirm_phrase": "SLETT"},
    )
    assert reset.status_code == 200
    assert reset.json()["athlete"]["setup_completed"] is False

    restart_preview = c.post(
        "/v1/setup/plan/preview",
        json={
            "display_name": "Bo",
            "username": "bo-restart",
            "coach_display_name": "Rocky",
            "coach_personality": "direkte",
            "enrich_with_llm": False,
        },
    )
    assert restart_preview.status_code == 200, restart_preview.text
    assert len(restart_preview.json()["plan_blocks"]) >= 2
    assert restart_preview.json()["intervals_sync"]["kind"] in (
        "calendar_notes_and_library_workouts",
        "calendar_notes_only_degraded",
    )


def test_setup_preview_shows_workouts_not_notes_only(client):
    c, *_ = client
    preview = c.post(
        "/v1/setup/plan/preview",
        json={
            "display_name": "Ada",
            "username": "ada-w",
            "goal_text": "5k",
            "background_notes": "nybegynner",
            "weekly_hours_target": 4,
            "enrich_with_llm": False,
        },
    )
    assert preview.status_code == 200, preview.text
    sync = preview.json()["intervals_sync"]
    assert sync["kind"] == "calendar_notes_and_library_workouts"
    assert sync["workouts_count"] >= 3
    assert sync.get("builder")
    assert not sync.get("error")
    assert any(
        (e.get("category") == "WORKOUT") or e.get("preview_no")
        for e in (sync.get("workouts_preview") or sync.get("events_preview") or [])
    )


def test_signals_from_athlete_injury():
    s = signals_from_athlete({"injury_notes": "isjas og ryggplager"})
    assert s["injury"] is True


def test_ancestor_paths_no_indexerror_on_docker_app():
    """Fly copies API to /app/*.py — Path.parents[2] raises IndexError(2)."""
    from plan_workouts import _ancestor_paths, format_exc_nb

    shallow = Path("/app/plan_workouts.py")
    # Direct parents[2] is the Fly bug
    with pytest.raises(IndexError) as ei:
        _ = shallow.parents[2]
    assert ei.value.args == (2,)
    assert "IndexError" in format_exc_nb(IndexError(2))
    assert "2" in format_exc_nb(IndexError(2))

    ancs = _ancestor_paths(shallow, max_up=4)
    assert ancs[0] == Path("/app")
    assert ancs[1] == Path("/")
    assert len(ancs) == 2  # stopped at filesystem root


def test_workouts_root_survives_shallow_docker_module(monkeypatch, tmp_path):
    """Simulate Docker: REPO_ROOT=/app-like with workouts + repo_scripts only."""
    from plan_workouts import _workouts_root, build_plan_week_icu_events

    app = tmp_path / "app"
    app.mkdir()
    # Minimal library + builder (same layout as Dockerfile)
    planned = app / "workouts" / "planned" / "run"
    planned.mkdir(parents=True)
    # Copy one real session so builder can resolve
    src = Path(config.REPO_ROOT) / "workouts" / "planned" / "run" / "R01-easy-40.txt"
    if not src.is_file():
        # REPO_ROOT may be services/coach-api in some envs
        src = Path(__file__).resolve().parents[3] / "workouts" / "planned" / "run" / "R01-easy-40.txt"
    (planned / "R01-easy-40.txt").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    strength = app / "workouts" / "planned" / "strength"
    strength.mkdir(parents=True)
    st = Path(__file__).resolve().parents[3] / "workouts" / "planned" / "strength" / "ST01-base.txt"
    if st.is_file():
        (strength / "ST01-base.txt").write_text(st.read_text(encoding="utf-8"), encoding="utf-8")
    # More run files referenced by HM template
    repo_run = Path(__file__).resolve().parents[3] / "workouts" / "planned" / "run"
    for name in (
        "R01-recovery-30.txt",
        "R02-easy-55-strides.txt",
        "R03-easy-trail-70.txt",
        "R04-long-easy-75.txt",
    ):
        p = repo_run / name
        if p.is_file():
            (planned / name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")

    rs = app / "repo_scripts"
    rs.mkdir()
    scripts_src = Path(__file__).resolve().parents[3] / "scripts"
    for name in (
        "intervals_push_calendar.py",
        "intervals_lib.py",
        "run_intervals_syntax.py",
    ):
        (rs / name).write_text(
            (scripts_src / name).read_text(encoding="utf-8"), encoding="utf-8"
        )

    monkeypatch.setattr(config, "REPO_ROOT", app)
    # Shallow module path like Fly /app/plan_workouts.py — only /app and /
    # Use a path under tmp that still has enough depth for pathlib resolve,
    # but exercise the same code via module_file under app/.
    module_file = app / "plan_workouts.py"
    module_file.write_text("# stub\n", encoding="utf-8")

    root = _workouts_root(module_file=module_file)
    assert root == app
    assert (root / "workouts" / "planned").is_dir()

    # Critical: Path('/app/x').parents[2] raises — our helper must not
    dockerish = Path("/app/plan_workouts.py")
    root2 = _workouts_root(module_file=dockerish)
    assert root2 == app  # falls back to config.REPO_ROOT

    blocks = [
        {
            "id": "b1",
            "title": "Grunnlag",
            "theme": "etablering",
            "start_date": "2026-09-28",
            "end_date": "2026-11-01",
            "weekly_hours": 6,
        }
    ]
    events = build_plan_week_icu_events(
        blocks,
        athlete={
            "goal_text": "halvmaraton",
            "athlete_type": "half_marathon_runner",
        },
        weeks=2,
        today=date(2026, 9, 28),
        repo_root=app,
        module_file=dockerish,
    )
    assert len(events) >= 6
    assert all(e["category"] == "WORKOUT" for e in events)
    # Run-primary: no swim in first weeks
    assert not any(e.get("type") == "Swim" for e in events)
    assert any(e.get("type") == "Run" for e in events)


def test_half_marathon_setup_preview_workouts_count(client):
    """HM / run-dominant Forhåndsvis must list library WORKOUTs, not notes-only."""
    c, *_ = client
    preview = c.post(
        "/v1/setup/plan/preview",
        json={
            "display_name": "Løper",
            "username": "hm-preview-w",
            "goal_text": "Halvmaraton våren 2027",
            "background_notes": "løper, ikke triatlon",
            "schedule_notes": "5-6t/uke",
            "weekly_hours_target": 6,
            "enrich_with_llm": False,
        },
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert (body.get("athlete_patch") or {}).get("athlete_type") == (
        "half_marathon_runner"
    )
    sync = body["intervals_sync"]
    assert sync["kind"] == "calendar_notes_and_library_workouts"
    assert sync["workouts_count"] > 0
    assert sync["notes_count"] >= 1
    assert not sync.get("error")
    assert any(
        (e.get("category") == "WORKOUT") or e.get("preview_no")
        for e in (sync.get("workouts_preview") or [])
    )


def test_bundle_degraded_indexerror_message_is_readable():
    """Regression: IndexError(2) must not surface as bare «2»."""
    from plan_workouts import format_exc_nb

    msg = format_exc_nb(IndexError(2))
    assert msg != "2"
    assert "IndexError" in msg
    assert "2" in msg


def test_old_parents_index_would_break_docker_but_helper_does_not():
    """Document the exact Fly failure mode and that we no longer hit it."""
    from plan_workouts import _ancestor_paths, _workouts_root
    import plan_workouts as pw

    fake = Path("/app/plan_workouts.py")
    # Pre-fix pattern (must raise):
    with pytest.raises(IndexError) as ei:
        _ = [
            Path("/app"),
            fake.parents[1],
            fake.parents[2],
            fake.parents[3],
        ]
    assert ei.value.args[0] == 2

    # Post-fix: building candidate list via helper never raises
    ancs = _ancestor_paths(fake, max_up=4)
    candidates = [Path("/app"), *ancs]
    assert Path("/app") in candidates
    # _workouts_root with dockerish module + normal REPO_ROOT must not raise
    root = _workouts_root(module_file=fake)
    assert isinstance(root, Path)
    assert pw._import_build_workout_event(module_file=fake)
