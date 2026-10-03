"""init_db must survive concurrent boot (lifespan + SEED_ON_BOOT) without sticky deadlock."""

from __future__ import annotations

from pathlib import Path

import pytest

from db import (
    _PG_INIT_ADVISORY_LOCK_KEY,
    _is_deadlock_error,
    init_db,
)


def test_is_deadlock_error_detects_postgres_message():
    assert _is_deadlock_error(
        Exception(
            "deadlock detected\nLINE 2:         UPDATE athletes SET setup_completed = 1\n"
        )
    )
    assert _is_deadlock_error(Exception("ERROR: 40P01 deadlock detected"))
    assert not _is_deadlock_error(Exception("connection refused"))


def test_init_db_sqlite_idempotent(tmp_path: Path):
    db = tmp_path / "coach.db"
    init_db(db)
    init_db(db)
    assert db.is_file()


def test_init_db_retries_deadlock_then_succeeds(monkeypatch, tmp_path: Path):
    import db as db_mod

    calls = {"n": 0}
    real = db_mod._init_db_once

    def flaky(path: Path) -> None:
        calls["n"] += 1
        if calls["n"] < 2:
            raise Exception(
                "deadlock detected\nLINE 2:         UPDATE athletes SET setup_completed = 1"
            )
        return real(path)

    monkeypatch.setattr(db_mod, "_init_db_once", flaky)
    monkeypatch.setattr(db_mod.time, "sleep", lambda _s: None)
    db_mod.init_db(tmp_path / "retry.db")
    assert calls["n"] == 2


def test_advisory_lock_key_stable():
    # Documented in ops playbook — do not change casually (cross-process lock).
    assert _PG_INIT_ADVISORY_LOCK_KEY == 87421031
