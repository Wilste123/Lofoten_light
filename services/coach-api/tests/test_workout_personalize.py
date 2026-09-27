"""Library workout personalization for non-William athletes."""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plan_workouts import build_plan_sync_bundle, build_plan_week_icu_events
from workout_personalize import (
    athlete_injury_flags,
    injury_strength_session,
    personalize_coach_text,
    text_has_william_addressee,
)

_BLOCKS = [
    {
        "id": "b1",
        "title": "Re-etablering",
        "theme": "Kontakt alle ben",
        "start_date": "2026-09-28",
        "end_date": "2026-10-25",
        "weekly_hours": 8.5,
    }
]

_R01_COACH = """### Fra treneren

William, rolig løp i dag. Puls er boss — ikke pace på klokka.

Rygg og isjas: hvis nerven bråker, gå 1 min og fortsett rolig. Plan B: 30 min + tøying hjemme.

---

- Warmup 10m 81-89% LTHR
"""


def test_replace_william_and_strip_isjas_for_other_athlete():
    out = personalize_coach_text(
        _R01_COACH,
        {"display_name": "Ada", "injury_notes": ""},
    )
    assert "Ada," in out or "Ada " in out
    assert not text_has_william_addressee(out)
    assert "isjas" not in out.lower()
    assert "Plan B" in out
    assert "Warmup" in out


def test_william_with_isjas_keeps_injury_copy():
    out = personalize_coach_text(
        _R01_COACH,
        {
            "display_name": "William",
            "injury_notes": "Rygg/isjasnerven — stopp ved prikking",
        },
    )
    assert "William," in out
    assert "isjas" in out.lower()


def test_injury_strength_depends_on_profile():
    title, path = injury_strength_session(
        {"display_name": "Ada", "injury_notes": "kneplager"}
    )
    assert "ST03" in title or "ST03" in path
    assert "isjas" not in title.lower()

    title_w, path_w = injury_strength_session(
        {"display_name": "William", "injury_notes": "isjas og rygg"}
    )
    assert "ST04" in path_w
    assert "isjas" in title_w.lower()


def test_icu_events_non_william_no_william_addressee():
    events = build_plan_week_icu_events(
        _BLOCKS,
        signals={"returning": True, "beginner": False, "injury": False},
        weeks=1,
        today=date(2026, 9, 28),
        athlete={
            "display_name": "Ada",
            "injury_notes": "",
            "notes": "comeback etter pause",
            "goal_text": "triatlon",
        },
    )
    assert events
    for ev in events:
        blob = f"{ev.get('name') or ''}\n{ev.get('description') or ''}"
        assert not text_has_william_addressee(blob), blob[:400]
        assert "isjas" not in blob.lower(), blob[:400]


def test_icu_events_injury_without_isjas_avoids_st04():
    events = build_plan_week_icu_events(
        _BLOCKS,
        signals={"injury": True, "beginner": False},
        weeks=1,
        today=date(2026, 9, 28),
        athlete={
            "display_name": "Bo",
            "injury_notes": "kne — forsiktig med løp",
            "notes": "",
        },
    )
    names = {e["name"] for e in events}
    assert not any("isjas" in n.lower() for n in names)
    assert any("ST03" in n or "prehab" in n.lower() or "recovery" in n.lower() for n in names)
    for ev in events:
        blob = f"{ev.get('name') or ''}\n{ev.get('description') or ''}"
        assert not text_has_william_addressee(blob)
        # Seed ST04 body must not appear; profile cue ok
        assert "isjasnerven" not in blob.lower()
        assert "glidning isjas" not in blob.lower()


def test_william_seed_may_keep_personalization():
    events = build_plan_week_icu_events(
        _BLOCKS,
        signals={"injury": True, "beginner": False},
        weeks=1,
        today=date(2026, 9, 28),
        athlete={
            "display_name": "William",
            "injury_notes": "Rygg/isjasnerven: stopp ved prikking",
            "notes": "comeback",
        },
    )
    joined = "\n".join(
        f"{e.get('name')}\n{e.get('description')}" for e in events
    )
    assert "William" in joined
    assert any("ST04" in (e.get("name") or "") or "isjas" in (e.get("name") or "").lower() for e in events)


def test_bundle_preview_personalizes_descriptions():
    bundle = build_plan_sync_bundle(
        _BLOCKS,
        athlete={
            "display_name": "Ada",
            "injury_notes": "",
            "notes": "nybegynner",
            "goal_text": "halvmaraton",
        },
        weeks=1,
        today=date(2026, 9, 28),
    )
    assert bundle["workouts_count"] >= 1
    for ev in bundle["workout_events"]:
        desc = ev.get("description") or ""
        assert not re.search(r"\bWilliam\b", desc, re.I)


def test_athlete_injury_flags_from_notes():
    flags = athlete_injury_flags({"injury_notes": "akilles plager"})
    assert flags["rygg_isjas"] is False
    assert flags["any_injury"] is True
    flags2 = athlete_injury_flags({"injury_notes": "isjas i høyre bein"})
    assert flags2["rygg_isjas"] is True
