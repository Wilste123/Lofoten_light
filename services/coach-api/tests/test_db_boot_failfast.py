"""Health + degraded boot when Postgres init fails (no infinite hang)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client_sqlite(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    monkeypatch.setenv("DATABASE_PATH", str(db))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("SUPABASE_DATABASE_URL", raising=False)
    import config

    monkeypatch.setattr(config, "DATABASE_PATH", db)
    monkeypatch.setattr(config, "DATABASE_URL", "")
    import main as main_mod
    from db import init_db

    init_db(db)
    main_mod._DB_BOOT_ERROR = None
    with TestClient(main_mod.app) as c:
        yield c, main_mod


def test_health_ok_sqlite(client_sqlite):
    c, _ = client_sqlite
    r = c.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db_ok"] is True
    assert body["db_backend"] == "sqlite"


def test_health_degraded_and_v1_503(client_sqlite):
    c, main_mod = client_sqlite
    main_mod._DB_BOOT_ERROR = "simulated postgres timeout"
    try:
        h = c.get("/health")
        assert h.status_code == 200
        assert h.json()["status"] == "degraded"
        assert h.json()["db_ok"] is False
        assert "simulated" in h.json()["db_error"]

        login = c.post("/v1/session/login", json={"username": "x"})
        assert login.status_code == 503
        assert login.json()["db_ok"] is False
        assert "sslmode" in login.json()["detail"].lower() or "Database" in login.json()["detail"]
    finally:
        main_mod._DB_BOOT_ERROR = None


def test_connect_unreachable_fails_fast(monkeypatch):
    """Bad host must not hang — connect_timeout bounds the wait."""
    monkeypatch.setenv("PGCONNECT_TIMEOUT", "2")
    from db_backend import connect

    # TEST-NET-1 — blackhole; connect should raise within a few seconds
    with pytest.raises(RuntimeError, match="Postgres-tilkobling feilet"):
        connect(
            "postgresql://u:p@203.0.113.1:5432/postgres?sslmode=disable"
        )
