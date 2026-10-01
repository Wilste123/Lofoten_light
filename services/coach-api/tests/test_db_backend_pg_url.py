"""Unit tests for Postgres URL normalization (sslmode + connect_timeout)."""

from __future__ import annotations

import os

import pytest

from db_backend import is_postgres_url, normalize_pg_url


def test_is_postgres_url():
    assert is_postgres_url("postgresql://u:p@host/db")
    assert is_postgres_url("postgres://u:p@host/db")
    assert is_postgres_url("postgresql+psycopg://u:p@host/db")
    assert not is_postgres_url("/tmp/coach.db")
    assert not is_postgres_url(None)


def test_normalize_adds_sslmode_for_supabase(monkeypatch):
    monkeypatch.delenv("PGCONNECT_TIMEOUT", raising=False)
    url = normalize_pg_url(
        "postgresql://postgres.abc:secret@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"
    )
    assert url.startswith("postgresql://")
    assert "sslmode=require" in url
    assert "connect_timeout=10" in url


def test_normalize_adds_sslmode_for_direct_supabase(monkeypatch):
    monkeypatch.delenv("PGCONNECT_TIMEOUT", raising=False)
    url = normalize_pg_url(
        "postgres://postgres:secret@db.abcdefgh.supabase.co:5432/postgres"
    )
    assert url.startswith("postgresql://")
    assert "sslmode=require" in url


def test_normalize_preserves_explicit_sslmode(monkeypatch):
    monkeypatch.delenv("PGCONNECT_TIMEOUT", raising=False)
    url = normalize_pg_url(
        "postgresql://postgres:x@db.x.supabase.co:5432/postgres?sslmode=verify-full"
    )
    assert "sslmode=verify-full" in url
    assert "sslmode=require" not in url


def test_normalize_localhost_skips_sslmode(monkeypatch):
    monkeypatch.delenv("PGCONNECT_TIMEOUT", raising=False)
    url = normalize_pg_url("postgresql://coach:coach@127.0.0.1:5432/coach_test")
    assert "sslmode=" not in url
    assert "connect_timeout=10" in url


def test_normalize_respects_pgconnect_timeout_env(monkeypatch):
    monkeypatch.setenv("PGCONNECT_TIMEOUT", "3")
    url = normalize_pg_url("postgresql://u:p@db.x.supabase.co:5432/postgres")
    assert "connect_timeout=3" in url


def test_normalize_does_not_duplicate_connect_timeout(monkeypatch):
    monkeypatch.setenv("PGCONNECT_TIMEOUT", "10")
    url = normalize_pg_url(
        "postgresql://u:p@db.x.supabase.co:5432/postgres?connect_timeout=7&sslmode=require"
    )
    assert url.count("connect_timeout=") == 1
    assert "connect_timeout=7" in url
