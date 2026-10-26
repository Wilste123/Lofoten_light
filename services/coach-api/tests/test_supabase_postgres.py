"""Postgres / Supabase dual-backend smoke (skipped without DATABASE_URL)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import config
from db import (
    db_session,
    get_active_plan_window,
    init_db,
    insert_athlete,
    list_plan_blocks,
    list_planned_sessions,
    replace_detalj_window,
    replace_plan_blocks,
)
from db_backend import is_postgres_url, wipe_all_tables
from two_tier_plan import DETAIL_WEEKS, build_two_tier_plan_payload

PG_URL = (
    os.environ.get("TEST_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or ""
).strip()

pytestmark = pytest.mark.skipif(
    not is_postgres_url(PG_URL),
    reason="Set TEST_DATABASE_URL / DATABASE_URL to a Postgres URI to run",
)


@pytest.fixture()
def pg(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", PG_URL)
    init_db(PG_URL)
    with db_session(PG_URL) as conn:
        wipe_all_tables(conn)
    yield PG_URL
    with db_session(PG_URL) as conn:
        wipe_all_tables(conn)


def test_postgres_two_tier_persist(pg):
    with db_session(pg) as conn:
        ath = insert_athlete(
            conn,
            {
                "display_name": "Pg Test",
                "username": "pg-test",
                "goal_race_date": "2027-08-20",
                "sessions_per_week": 3,
                "allowed_disciplines": '["run","strength"]',
                "setup_completed": True,
            },
        )
        aid = ath["id"]
        blocks = replace_plan_blocks(
            conn,
            aid,
            [
                {
                    "id": f"{aid}-b0",
                    "title": "Base",
                    "theme": "aerob",
                    "start_date": "2026-10-01",
                    "end_date": "2027-08-20",
                    "weekly_hours": 6,
                    "layer": "grov",
                    "session_types": {"easy": 2, "quality": 1, "strength": 1},
                }
            ],
        )
        assert blocks[0]["layer"] == "grov"
        payload = build_two_tier_plan_payload(blocks, athlete=ath)
        result = replace_detalj_window(
            conn,
            aid,
            start_date=payload["detalj_start"],
            end_date=payload["detalj_end"],
            sessions=payload["sessions"],
            source="setup",
        )
        assert result["count"] == payload["count"]
        assert payload["detalj_weeks"] == DETAIL_WEEKS
        assert result["count"] <= DETAIL_WEEKS * 14  # hard cap: at most 2/day
        assert result["count"] >= 1
        window = get_active_plan_window(conn, aid)
        assert window is not None
        assert window["kind"] == "detalj"
        rows = list_planned_sessions(conn, aid)
        assert len(rows) == result["count"]
        assert all((r.get("plan_tier") or "detalj") == "detalj" for r in rows)
        assert list_plan_blocks(conn, aid)
