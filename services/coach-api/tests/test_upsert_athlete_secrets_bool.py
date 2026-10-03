"""Regression: tp_sync_enabled must bind as bool on Postgres BOOLEAN column.

Live Fly (migration 003) defines athlete_secrets.tp_sync_enabled as BOOLEAN.
Writing bare ints 0/1 made PUT /v1/athlete/me/intervals return HTTP 500.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db import (  # noqa: E402
    _db_flag,
    db_session,
    get_athlete_secrets,
    init_db,
    insert_athlete,
    upsert_athlete_secrets,
)
from db_backend import PgConnection  # noqa: E402


def test_db_flag_sqlite_uses_int(tmp_path):
    db = tmp_path / "flag.db"
    init_db(db)
    with db_session(db) as conn:
        assert _db_flag(conn, False) == 0
        assert _db_flag(conn, True) == 1
        assert isinstance(_db_flag(conn, False), int)


def test_db_flag_postgres_uses_bool():
    pg = object.__new__(PgConnection)
    assert _db_flag(pg, False) is False
    assert _db_flag(pg, True) is True
    assert _db_flag(pg, 0) is False
    assert _db_flag(pg, 1) is True
    assert isinstance(_db_flag(pg, 0), bool)
    assert isinstance(_db_flag(pg, False), bool)


def test_upsert_intervals_insert_sqlite_still_works(tmp_path):
    db = tmp_path / "secrets.db"
    init_db(db)
    with db_session(db) as conn:
        ath = insert_athlete(
            conn,
            {"display_name": "Bool QA", "username": "bool-qa", "setup_completed": True},
        )
        aid = ath["id"]
        row = upsert_athlete_secrets(
            conn,
            aid,
            intervals_api_key="fake-key-not-real-eraa",
            intervals_athlete_id="i729340",
        )
        assert row["intervals_athlete_id"] == "i729340"
        assert row["intervals_api_key"] == "fake-key-not-real-eraa"
        # SQLite stores INTEGER; truthy check must still work for readers
        assert not bool(row["tp_sync_enabled"])

        row2 = upsert_athlete_secrets(
            conn,
            aid,
            intervals_api_key="fake-key-not-real-eraa",
            intervals_athlete_id="i729340",
            tp_sync_enabled=True,
        )
        assert bool(row2["tp_sync_enabled"])


class _CapturePg(PgConnection):
    """Minimal PgConnection stand-in that records bound params (no network)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...] | list[Any]]] = []
        self._existing: dict[str, Any] | None = None

    def execute(self, sql: str, params=None):  # type: ignore[override]
        params = tuple(params or ())
        self.calls.append((sql, params))

        class _Cur:
            def fetchone(self_inner):
                if "FROM athlete_secrets" in sql and "SELECT" in sql.upper():
                    return self._existing
                return None

        return _Cur()


def test_upsert_binds_python_bool_on_postgres_insert():
    """Reproduce the Fly failure mode: INSERT must not bind int for BOOLEAN."""
    conn = _CapturePg()
    upsert_athlete_secrets(
        conn,
        "athlete-1",
        intervals_api_key="k",
        intervals_athlete_id="i1",
    )
    insert_calls = [c for c in conn.calls if "INSERT INTO athlete_secrets" in c[0]]
    assert len(insert_calls) == 1
    params = insert_calls[0][1]
    # (athlete_id, key, aid, tp_cookie, tp_uid, tp_on, now)
    tp_on = params[5]
    assert tp_on is False
    assert type(tp_on) is bool


def test_upsert_binds_python_bool_on_postgres_update_preserve():
    conn = _CapturePg()
    conn._existing = {
        "athlete_id": "athlete-1",
        "intervals_api_key": "old",
        "intervals_athlete_id": "i0",
        "tp_auth_cookie": None,
        "tp_user_id": None,
        "tp_sync_enabled": False,
        "updated_at": "t0",
    }
    upsert_athlete_secrets(
        conn,
        "athlete-1",
        intervals_api_key="new-key",
        intervals_athlete_id="i1",
    )
    update_calls = [c for c in conn.calls if "UPDATE athlete_secrets" in c[0]]
    assert len(update_calls) == 1
    # (key, aid, tp_cookie, tp_uid, tp_on, now, athlete_id)
    tp_on = update_calls[0][1][4]
    assert tp_on is False
    assert type(tp_on) is bool


def test_legacy_int_binding_would_be_rejected_by_pg_boolean_semantics():
    """Document why ints are wrong: Postgres BOOLEAN ≠ integer parameter."""
    # psycopg/Postgres: column boolean + int param → datatype mismatch.
    # We only assert the fixed binder never emits int for PgConnection.
    pg = object.__new__(PgConnection)
    assert type(_db_flag(pg, False)) is bool
    assert type(_db_flag(pg, 0)) is bool
    # Contrast: the old code path produced ints
    legacy = 1 if False else 0
    assert type(legacy) is int
