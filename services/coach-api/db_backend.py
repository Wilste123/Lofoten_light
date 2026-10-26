"""SQLite + Postgres connection adapter for coach-api.

Keeps the existing ``?`` placeholder style and a Row-like interface so ``db.py``
stays schema-shaped 1:1 across backends. Prefer ``DATABASE_URL`` /
``SUPABASE_DB_URL`` (Postgres) when set; otherwise ``DATABASE_PATH`` (SQLite).
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

DbTarget = Path | str

_PG_URL_PREFIXES = ("postgres://", "postgresql://", "postgresql+psycopg://")

# Fail-fast defaults — never hang forever on bad DATABASE_URL / pooler / SSL.
DEFAULT_PG_CONNECT_TIMEOUT_S = 10
_SUPABASE_HOST_MARKERS = ("supabase.co", "supabase.com", "pooler.supabase")


def is_postgres_url(target: DbTarget | None) -> bool:
    if target is None:
        return False
    s = str(target).strip().lower()
    return s.startswith(_PG_URL_PREFIXES)


def _pg_connect_timeout_s() -> int:
    raw = (os.environ.get("PGCONNECT_TIMEOUT") or "").strip()
    if raw.isdigit():
        return max(1, int(raw))
    return DEFAULT_PG_CONNECT_TIMEOUT_S


def _host_looks_like_supabase(host: str) -> bool:
    h = (host or "").lower()
    return any(m in h for m in _SUPABASE_HOST_MARKERS)


def normalize_pg_url(url: str) -> str:
    """Normalize scheme + ensure sslmode/connect_timeout for Supabase/pooler.

    Supabase (direct + pooler) requires TLS. Without ``sslmode=require`` (or
    ``connect_timeout``), ``psycopg.connect`` can hang until the process is
    killed — which wedges Fly lifespan so even ``/health`` never answers.
    """
    u = url.strip()
    if u.startswith("postgresql+psycopg://"):
        u = "postgresql://" + u[len("postgresql+psycopg://") :]
    elif u.startswith("postgres://"):
        u = "postgresql://" + u[len("postgres://") :]

    parsed = urlparse(u)
    # Preserve blank password / unusual userinfo; only touch query params.
    q = dict(parse_qsl(parsed.query, keep_blank_values=True))
    host = parsed.hostname or ""

    sslmode = (q.get("sslmode") or "").strip().lower()
    if not sslmode:
        # Local docker/dev Postgres usually has no TLS; remote/Supabase needs it.
        if _host_looks_like_supabase(host) or host not in ("", "localhost", "127.0.0.1", "::1"):
            q["sslmode"] = "require"

    if "connect_timeout" not in q:
        q["connect_timeout"] = str(_pg_connect_timeout_s())

    return urlunparse(parsed._replace(query=urlencode(q)))


def _qmark_to_percent(sql: str) -> str:
    """Translate SQLite ``?`` placeholders to psycopg ``%s`` (no literal ? in our SQL)."""
    return sql.replace("?", "%s")


class _PgRow(dict):
    """dict subclass supporting sqlite3.Row-style integer index access."""

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)

    def keys(self):  # type: ignore[override]
        return super().keys()


class _PgCursor:
    def __init__(self, cur: Any):
        self._cur = cur
        self.rowcount = getattr(cur, "rowcount", -1)

    def fetchone(self) -> _PgRow | None:
        row = self._cur.fetchone()
        if row is None:
            return None
        if isinstance(row, dict):
            return _PgRow(row)
        # tuple fallback
        cols = [d.name for d in (self._cur.description or [])]
        return _PgRow(dict(zip(cols, row)))

    def fetchall(self) -> list[_PgRow]:
        rows = self._cur.fetchall()
        out: list[_PgRow] = []
        for row in rows:
            if isinstance(row, dict):
                out.append(_PgRow(row))
            else:
                cols = [d.name for d in (self._cur.description or [])]
                out.append(_PgRow(dict(zip(cols, row))))
        return out

    def __iter__(self) -> Iterator[_PgRow]:
        return iter(self.fetchall())


class PgConnection:
    """Thin wrapper: ``?`` placeholders, commit/rollback, executescript."""

    backend = "postgres"

    def __init__(self, raw: Any):
        self._raw = raw

    def __enter__(self) -> "PgConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()
        self.close()

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> _PgCursor:
        cur = self._raw.execute(_qmark_to_percent(sql), params or ())
        wrapped = _PgCursor(cur)
        wrapped.rowcount = cur.rowcount
        return wrapped

    def executescript(self, script: str) -> None:
        # Strip line comments; split on semicolons.
        buf: list[str] = []
        for line in script.splitlines():
            stripped = line.strip()
            if stripped.startswith("--"):
                continue
            buf.append(line)
        text = "\n".join(buf)
        for stmt in re.split(r";\s*\n", text):
            s = stmt.strip().rstrip(";").strip()
            if not s:
                continue
            self._raw.execute(s)

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        self._raw.close()

    def set_athlete_context(self, athlete_id: str | None) -> None:
        """Session GUC for RLS policies (ignored by service_role / superuser)."""
        aid = (athlete_id or "").strip()
        self._raw.execute(
            "SELECT set_config('app.current_athlete_id', %s, true)",
            (aid,),
        )


class SqliteConnection:
    """Marker wrapper so callers can branch on ``.backend`` consistently."""

    backend = "sqlite"

    def __init__(self, raw: sqlite3.Connection):
        self._raw = raw

    def __enter__(self) -> "SqliteConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()
        self.close()

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> sqlite3.Cursor:
        if params is None:
            return self._raw.execute(sql)
        return self._raw.execute(sql, params)

    def executescript(self, script: str) -> sqlite3.Cursor:
        return self._raw.executescript(script)

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        self._raw.close()

    def set_athlete_context(self, athlete_id: str | None) -> None:
        return None

    # Expose raw for rare PRAGMA / legacy
    @property
    def raw(self) -> sqlite3.Connection:
        return self._raw

Connection = SqliteConnection | PgConnection


def connect(target: DbTarget) -> Connection:
    if is_postgres_url(target):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "DATABASE_URL/Supabase Postgres krever psycopg. "
                "pip install 'psycopg[binary]>=3.1'"
            ) from exc
        timeout_s = _pg_connect_timeout_s()
        try:
            raw = psycopg.connect(
                normalize_pg_url(str(target)),
                row_factory=dict_row,
                connect_timeout=timeout_s,
            )
        except Exception as exc:
            # Re-wrap with actionable hint (sslmode / pooler / password).
            raise RuntimeError(
                "Postgres-tilkobling feilet innen "
                f"{timeout_s}s. Sjekk DATABASE_URL (sslmode=require for "
                "Supabase), Session-pooler :5432 eller direct db.*.supabase.co, "
                f"passord og nettverk. Årsak: {exc}"
            ) from exc
        raw.autocommit = False
        return PgConnection(raw)

    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(str(path), check_same_thread=False)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys = ON")
    return SqliteConnection(raw)


def table_columns(conn: Connection, table: str) -> set[str]:
    if isinstance(conn, PgConnection):
        cur = conn.execute(
            """
            SELECT column_name AS name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ?
            """,
            (table,),
        )
        return {str(r["name"]) for r in cur.fetchall()}
    cur = conn.execute(f"PRAGMA table_info({table})")
    # sqlite3.Row: index 1 is name
    return {str(r[1]) for r in cur.fetchall()}


def wipe_all_tables(conn: Connection) -> None:
    """Test helper — delete all coach rows (FK-safe order)."""
    tables = [
        "coordinated_sessions",
        "training_pairs",
        "pending_actions",
        "session_completions",
        "planned_sessions",
        "plan_windows",
        "plan_blocks",
        "messages",
        "athlete_secrets",
        "invites",
        "athletes",
    ]
    if isinstance(conn, PgConnection):
        for t in tables:
            conn.execute(f"TRUNCATE TABLE {t} CASCADE")
    else:
        for t in tables:
            conn.execute(f"DELETE FROM {t}")
