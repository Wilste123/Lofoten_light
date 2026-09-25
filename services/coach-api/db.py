"""SQLite schema and helpers for coach-api."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS athletes (
  id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  timezone TEXT DEFAULT 'Europe/Oslo',
  coach_display_name TEXT NOT NULL DEFAULT 'Rocky',
  coach_personality TEXT DEFAULT 'direkte',
  coach_style_note TEXT DEFAULT '',
  accent_color TEXT DEFAULT '#1a6b4a',
  goal_text TEXT DEFAULT '',
  injury_notes TEXT DEFAULT '',
  agreements_json TEXT DEFAULT '[]',
  weekly_focus TEXT DEFAULT '',
  ftp_tested REAL,
  ftp_tested_at TEXT,
  ftp_estimated REAL,
  vo2_estimate REAL,
  estimate_confidence TEXT,
  estimate_updated_at TEXT,
  estimate_source TEXT,
  weight_kg REAL,
  age_years INTEGER,
  notes TEXT DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS athlete_secrets (
  athlete_id TEXT PRIMARY KEY REFERENCES athletes(id) ON DELETE CASCADE,
  intervals_api_key TEXT,
  intervals_athlete_id TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  athlete_id TEXT NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invites (
  id TEXT PRIMARY KEY,
  token_hash TEXT NOT NULL,
  created_by TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  expires_at TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS training_pairs (
  id TEXT PRIMARY KEY,
  athlete_a_id TEXT NOT NULL REFERENCES athletes(id),
  athlete_b_id TEXT NOT NULL REFERENCES athletes(id),
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS coordinated_sessions (
  id TEXT PRIMARY KEY,
  pair_id TEXT NOT NULL REFERENCES training_pairs(id) ON DELETE CASCADE,
  starts_at TEXT NOT NULL,
  ends_at TEXT,
  venue TEXT,
  discipline TEXT,
  athlete_a_workout_note TEXT,
  athlete_b_workout_note TEXT,
  athlete_a_confirmed INTEGER DEFAULT 0,
  athlete_b_confirmed INTEGER DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_athlete ON messages(athlete_id, created_at);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def db_session(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_to_athlete(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    d = dict(row)
    raw = d.pop("agreements_json", "[]") or "[]"
    try:
        d["agreements"] = json.loads(raw)
    except json.JSONDecodeError:
        d["agreements"] = []
    return d


def get_athlete(conn: sqlite3.Connection, athlete_id: str) -> dict[str, Any] | None:
    cur = conn.execute("SELECT * FROM athletes WHERE id = ?", (athlete_id,))
    return row_to_athlete(cur.fetchone())


def insert_athlete(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    athlete_id = data.get("id") or new_id()
    agreements = data.get("agreements") or []
    conn.execute(
        """
        INSERT INTO athletes (
          id, display_name, timezone, coach_display_name, coach_personality,
          coach_style_note, accent_color, goal_text, injury_notes, agreements_json,
          weekly_focus, ftp_tested, ftp_tested_at, weight_kg, age_years, notes,
          created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            athlete_id,
            data["display_name"],
            data.get("timezone") or "Europe/Oslo",
            data.get("coach_display_name") or "Rocky",
            data.get("coach_personality") or "direkte",
            data.get("coach_style_note") or "",
            data.get("accent_color") or "#1a6b4a",
            data.get("goal_text") or "",
            data.get("injury_notes") or "",
            json.dumps(agreements, ensure_ascii=False),
            data.get("weekly_focus") or "",
            data.get("ftp_tested"),
            data.get("ftp_tested_at"),
            data.get("weight_kg"),
            data.get("age_years"),
            data.get("notes") or "",
            now,
            now,
        ),
    )
    return get_athlete(conn, athlete_id)  # type: ignore[return-value]


def update_athlete(
    conn: sqlite3.Connection, athlete_id: str, patch: dict[str, Any]
) -> dict[str, Any] | None:
    existing = get_athlete(conn, athlete_id)
    if not existing:
        return None
    allowed = {
        "display_name",
        "timezone",
        "coach_display_name",
        "coach_personality",
        "coach_style_note",
        "accent_color",
        "goal_text",
        "injury_notes",
        "weekly_focus",
        "ftp_tested",
        "ftp_tested_at",
        "ftp_estimated",
        "vo2_estimate",
        "estimate_confidence",
        "estimate_updated_at",
        "estimate_source",
        "weight_kg",
        "age_years",
        "notes",
    }
    fields: list[str] = []
    values: list[Any] = []
    for key, val in patch.items():
        if key == "agreements":
            fields.append("agreements_json = ?")
            values.append(json.dumps(val, ensure_ascii=False))
        elif key in allowed:
            fields.append(f"{key} = ?")
            values.append(val)
    if not fields:
        return existing
    fields.append("updated_at = ?")
    values.append(utc_now())
    values.append(athlete_id)
    conn.execute(
        f"UPDATE athletes SET {', '.join(fields)} WHERE id = ?",
        values,
    )
    return get_athlete(conn, athlete_id)


def add_message(
    conn: sqlite3.Connection, athlete_id: str, role: str, content: str
) -> dict[str, Any]:
    mid = new_id()
    now = utc_now()
    conn.execute(
        "INSERT INTO messages (id, athlete_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (mid, athlete_id, role, content, now),
    )
    return {"id": mid, "athlete_id": athlete_id, "role": role, "content": content, "created_at": now}


def recent_messages(
    conn: sqlite3.Connection, athlete_id: str, limit: int = 12
) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT id, athlete_id, role, content, created_at FROM messages
        WHERE athlete_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (athlete_id, limit),
    )
    rows = [dict(r) for r in cur.fetchall()]
    rows.reverse()
    return rows
