"""Tests for profile.md write on onboarding / update."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from profile import render_profile_md, write_profile


def test_render_contains_name_and_coach():
    athlete = {
        "id": "test-id",
        "display_name": "Ada",
        "coach_display_name": "Rocky",
        "coach_personality": "direkte",
        "accent_color": "#c45c26",
        "goal_text": "Half Extreme Lofoten 2027",
        "injury_notes": "Ankel — gradvis",
        "ftp_tested": 210,
        "ftp_tested_at": "2026-09-24",
        "weight_kg": 70,
        "age_years": 28,
        "timezone": "Europe/Oslo",
        "agreements": ["Ingen langløp denne uka"],
        "weekly_focus": "Z2 base",
        "notes": "IBS — lav FODMAP før intervall",
    }
    md = render_profile_md(athlete)
    assert "Ada" in md
    assert "Rocky" in md
    assert "210" in md
    assert "Half Extreme" in md
    assert "Ingen langløp" in md
    assert "ikke anta Williams historikk" in md.lower() or "Williams historikk" in md


def test_write_profile_creates_file(tmp_path: Path):
    athlete = {
        "id": "abc-123",
        "display_name": "Kai",
        "coach_display_name": "Pondus",
        "coach_personality": "støttende",
        "goal_text": "Bygge base",
        "injury_notes": "",
        "agreements": [],
    }
    path = write_profile(tmp_path, athlete)
    assert path == tmp_path / "abc-123" / "profile.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Athlete profile — Kai")
    assert "Pondus" in text
