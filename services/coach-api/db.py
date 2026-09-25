"""SQLite schema and helpers for coach-api."""

from __future__ import annotations

import hashlib
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
  sport TEXT DEFAULT 'triathlon',
  schedule_notes TEXT DEFAULT '',
  nutrition_ibs TEXT DEFAULT 'no',
  nutrition_gluten TEXT DEFAULT 'none',
  nutrition_lactose INTEGER DEFAULT 0,
  nutrition_other_restrictions TEXT DEFAULT '',
  nutrition_notes TEXT DEFAULT '',
  notes TEXT DEFAULT '',
  season_swim_hours_target REAL,
  season_bike_hours_target REAL,
  season_run_hours_target REAL,
  season_strength_hours_target REAL,
  season_start_date TEXT,
  goal_race_date TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plan_blocks (
  id TEXT PRIMARY KEY,
  athlete_id TEXT NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
  title TEXT NOT NULL DEFAULT '',
  theme TEXT DEFAULT '',
  start_date TEXT,
  end_date TEXT,
  weekly_hours REAL,
  sort_order INTEGER DEFAULT 0,
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
CREATE INDEX IF NOT EXISTS idx_plan_blocks_athlete ON plan_blocks(athlete_id, start_date);
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


_EXTRA_COLUMNS = [
    ("sport", "TEXT DEFAULT 'triathlon'"),
    ("schedule_notes", "TEXT DEFAULT ''"),
    ("nutrition_ibs", "TEXT DEFAULT 'no'"),
    ("nutrition_gluten", "TEXT DEFAULT 'none'"),
    ("nutrition_lactose", "INTEGER DEFAULT 0"),
    ("nutrition_other_restrictions", "TEXT DEFAULT ''"),
    ("nutrition_notes", "TEXT DEFAULT ''"),
    ("season_swim_hours_target", "REAL"),
    ("season_bike_hours_target", "REAL"),
    ("season_run_hours_target", "REAL"),
    ("season_strength_hours_target", "REAL"),
    ("season_start_date", "TEXT"),
    ("goal_race_date", "TEXT"),
]


def init_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        existing = {
            r[1]
            for r in conn.execute("PRAGMA table_info(athletes)").fetchall()
        }
        for name, decl in _EXTRA_COLUMNS:
            if name not in existing:
                conn.execute(f"ALTER TABLE athletes ADD COLUMN {name} {decl}")
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
    d["nutrition_lactose"] = bool(d.get("nutrition_lactose"))
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
          weekly_focus, ftp_tested, ftp_tested_at, weight_kg, age_years,
          sport, schedule_notes,
          nutrition_ibs, nutrition_gluten, nutrition_lactose,
          nutrition_other_restrictions, nutrition_notes, notes,
          created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            data.get("sport") or "triathlon",
            data.get("schedule_notes") or "",
            data.get("nutrition_ibs") or "no",
            data.get("nutrition_gluten") or "none",
            1 if data.get("nutrition_lactose") else 0,
            data.get("nutrition_other_restrictions") or "",
            data.get("nutrition_notes") or "",
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
        "sport",
        "schedule_notes",
        "nutrition_ibs",
        "nutrition_gluten",
        "nutrition_other_restrictions",
        "nutrition_notes",
        "notes",
        "season_swim_hours_target",
        "season_bike_hours_target",
        "season_run_hours_target",
        "season_strength_hours_target",
        "season_start_date",
        "goal_race_date",
    }
    fields: list[str] = []
    values: list[Any] = []
    for key, val in patch.items():
        if key == "agreements":
            fields.append("agreements_json = ?")
            values.append(json.dumps(val, ensure_ascii=False))
        elif key == "nutrition_lactose":
            fields.append("nutrition_lactose = ?")
            values.append(1 if val else 0)
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


def get_athlete_secrets(
    conn: sqlite3.Connection, athlete_id: str
) -> dict[str, Any] | None:
    cur = conn.execute(
        """
        SELECT athlete_id, intervals_api_key, intervals_athlete_id, updated_at
        FROM athlete_secrets WHERE athlete_id = ?
        """,
        (athlete_id,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def upsert_athlete_secrets(
    conn: sqlite3.Connection,
    athlete_id: str,
    *,
    intervals_api_key: str | None = None,
    intervals_athlete_id: str | None = None,
) -> dict[str, Any]:
    """Insert or update Intervals credentials. None keeps existing value."""
    existing = get_athlete_secrets(conn, athlete_id)
    now = utc_now()
    if existing is None:
        key = intervals_api_key or None
        aid = intervals_athlete_id or None
        conn.execute(
            """
            INSERT INTO athlete_secrets (
              athlete_id, intervals_api_key, intervals_athlete_id, updated_at
            ) VALUES (?, ?, ?, ?)
            """,
            (athlete_id, key, aid, now),
        )
    else:
        key = (
            intervals_api_key
            if intervals_api_key is not None
            else existing.get("intervals_api_key")
        )
        aid = (
            intervals_athlete_id
            if intervals_athlete_id is not None
            else existing.get("intervals_athlete_id")
        )
        conn.execute(
            """
            UPDATE athlete_secrets
            SET intervals_api_key = ?, intervals_athlete_id = ?, updated_at = ?
            WHERE athlete_id = ?
            """,
            (key, aid, now, athlete_id),
        )
    return get_athlete_secrets(conn, athlete_id)  # type: ignore[return-value]


def mask_api_key(key: str | None) -> str | None:
    """Never return full key — last 4 chars only when long enough."""
    if not key:
        return None
    key = key.strip()
    if len(key) <= 4:
        return "••••"
    return f"••••{key[-4:]}"


def secrets_public_view(row: dict[str, Any] | None) -> dict[str, Any]:
    """Safe payload for GET — no full API key."""
    if not row:
        return {
            "connected": False,
            "intervals_athlete_id": None,
            "api_key_hint": None,
            "updated_at": None,
        }
    key = (row.get("intervals_api_key") or "").strip()
    aid = (row.get("intervals_athlete_id") or "").strip() or None
    connected = bool(key and aid)
    return {
        "connected": connected,
        "intervals_athlete_id": aid,
        "api_key_hint": mask_api_key(key) if key else None,
        "updated_at": row.get("updated_at"),
    }


def _row_to_block(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def list_plan_blocks(
    conn: sqlite3.Connection, athlete_id: str
) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT * FROM plan_blocks
        WHERE athlete_id = ?
        ORDER BY
          CASE WHEN start_date IS NULL OR start_date = '' THEN 1 ELSE 0 END,
          start_date ASC,
          sort_order ASC,
          created_at ASC
        """,
        (athlete_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def get_plan_block(
    conn: sqlite3.Connection, athlete_id: str, block_id: str
) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT * FROM plan_blocks WHERE id = ? AND athlete_id = ?",
        (block_id, athlete_id),
    )
    return _row_to_block(cur.fetchone())


def insert_plan_block(
    conn: sqlite3.Connection, athlete_id: str, data: dict[str, Any]
) -> dict[str, Any]:
    now = utc_now()
    block_id = data.get("id") or new_id()
    conn.execute(
        """
        INSERT INTO plan_blocks (
          id, athlete_id, title, theme, start_date, end_date,
          weekly_hours, sort_order, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            block_id,
            athlete_id,
            data.get("title") or "",
            data.get("theme") or "",
            data.get("start_date") or None,
            data.get("end_date") or None,
            data.get("weekly_hours"),
            int(data.get("sort_order") or 0),
            now,
            now,
        ),
    )
    return get_plan_block(conn, athlete_id, block_id)  # type: ignore[return-value]


def update_plan_block(
    conn: sqlite3.Connection,
    athlete_id: str,
    block_id: str,
    patch: dict[str, Any],
) -> dict[str, Any] | None:
    existing = get_plan_block(conn, athlete_id, block_id)
    if not existing:
        return None
    allowed = {
        "title",
        "theme",
        "start_date",
        "end_date",
        "weekly_hours",
        "sort_order",
    }
    fields: list[str] = []
    values: list[Any] = []
    for key, val in patch.items():
        if key not in allowed:
            continue
        if key == "sort_order" and val is not None:
            val = int(val)
        fields.append(f"{key} = ?")
        values.append(val)
    if not fields:
        return existing
    fields.append("updated_at = ?")
    values.append(utc_now())
    values.extend([block_id, athlete_id])
    conn.execute(
        f"UPDATE plan_blocks SET {', '.join(fields)} WHERE id = ? AND athlete_id = ?",
        values,
    )
    return get_plan_block(conn, athlete_id, block_id)


def delete_plan_block(
    conn: sqlite3.Connection, athlete_id: str, block_id: str
) -> bool:
    cur = conn.execute(
        "DELETE FROM plan_blocks WHERE id = ? AND athlete_id = ?",
        (block_id, athlete_id),
    )
    return cur.rowcount > 0


def hash_invite_token(token: str) -> str:
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def insert_invite(
    conn: sqlite3.Connection,
    token: str,
    *,
    created_by: str | None = None,
    status: str = "pending",
    expires_at: str | None = None,
) -> dict[str, Any]:
    """Store a hashed invite token (plain token never persisted)."""
    now = utc_now()
    invite_id = new_id()
    token_hash = hash_invite_token(token)
    conn.execute(
        """
        INSERT INTO invites (id, token_hash, created_by, status, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (invite_id, token_hash, created_by, status, expires_at, now),
    )
    return {
        "id": invite_id,
        "token_hash": token_hash,
        "created_by": created_by,
        "status": status,
        "expires_at": expires_at,
        "created_at": now,
    }


def invite_token_valid(conn: sqlite3.Connection, token: str) -> bool:
    """True if a matching invite exists and is not expired."""
    raw = (token or "").strip()
    if not raw:
        return False
    cur = conn.execute(
        """
        SELECT status, expires_at FROM invites
        WHERE token_hash = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (hash_invite_token(raw),),
    )
    row = cur.fetchone()
    if not row:
        return False
    status = (row["status"] or "").lower()
    if status not in ("pending", "accepted", "active"):
        return False
    expires = row["expires_at"]
    if expires and expires < utc_now():
        return False
    return True
