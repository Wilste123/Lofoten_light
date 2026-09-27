"""SQLite schema and helpers for coach-api."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

# Lowercase slug: letters/digits, optional hyphens, 2–32 chars.
USERNAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS athletes (
  id TEXT PRIMARY KEY,
  username TEXT UNIQUE,
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
  show_body_metrics INTEGER DEFAULT 1,
  setup_completed INTEGER DEFAULT 0,
  athlete_type TEXT DEFAULT '',
  athlete_type_notes TEXT DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_completions (
  id TEXT PRIMARY KEY,
  athlete_id TEXT NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
  external_session_id TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'intervals',
  session_name TEXT DEFAULT '',
  session_date TEXT,
  discipline TEXT DEFAULT '',
  status TEXT NOT NULL,
  reason TEXT DEFAULT '',
  note TEXT DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (athlete_id, external_session_id)
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

CREATE TABLE IF NOT EXISTS pending_actions (
  id TEXT PRIMARY KEY,
  athlete_id TEXT NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL,
  expires_at TEXT,
  confirmed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_athlete ON messages(athlete_id, created_at);
CREATE INDEX IF NOT EXISTS idx_plan_blocks_athlete ON plan_blocks(athlete_id, start_date);
CREATE INDEX IF NOT EXISTS idx_pending_actions_athlete ON pending_actions(athlete_id, created_at);
CREATE INDEX IF NOT EXISTS idx_session_completions_athlete
  ON session_completions(athlete_id, session_date);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def slugify_username(raw: str | None, *, fallback: str = "utover") -> str:
    """Build a lowercase username slug from display name or free text."""
    text = (raw or "").strip()
    if not text:
        return fallback
    norm = unicodedata.normalize("NFKD", text)
    ascii_only = "".join(c for c in norm if not unicodedata.combining(c))
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")
    if not slug:
        slug = fallback
    return slug[:32]


def normalize_username(raw: str | None) -> str:
    """Lowercase + strip; does not invent a slug from display name."""
    return (raw or "").strip().lower()


def validate_username(username: str) -> str | None:
    """Return Norwegian error message, or None if ok."""
    if not username:
        return "Brukernavn er påkrevd."
    if len(username) < 2 or len(username) > 32:
        return "Brukernavn må være 2–32 tegn."
    if not USERNAME_RE.match(username):
        return (
            "Brukernavn må være små bokstaver, tall og bindestrek "
            "(ikke starte/slutte med bindestrek)."
        )
    return None


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


_EXTRA_COLUMNS = [
    ("username", "TEXT"),
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
    ("show_body_metrics", "INTEGER DEFAULT 1"),
    ("setup_completed", "INTEGER DEFAULT 0"),
    ("athlete_type", "TEXT DEFAULT ''"),
    ("athlete_type_notes", "TEXT DEFAULT ''"),
]

# Seeded returning athletes — always treated as setup-done; re-seed must not wipe them.
SEED_PROTECTED_IDS = frozenset({"william-lofoten"})
SEED_PROTECTED_USERNAMES = frozenset({"william"})


def _username_taken(
    conn: sqlite3.Connection, username: str, *, exclude_id: str | None = None
) -> bool:
    if exclude_id:
        cur = conn.execute(
            "SELECT 1 FROM athletes WHERE username = ? AND id != ? LIMIT 1",
            (username, exclude_id),
        )
    else:
        cur = conn.execute(
            "SELECT 1 FROM athletes WHERE username = ? LIMIT 1",
            (username,),
        )
    return cur.fetchone() is not None


def allocate_username(
    conn: sqlite3.Connection,
    preferred: str,
    *,
    exclude_id: str | None = None,
) -> str:
    """Return preferred slug, or preferred-2 / preferred-3 if taken."""
    base = slugify_username(preferred)[:28] or "utover"
    candidate = base
    n = 2
    while _username_taken(conn, candidate, exclude_id=exclude_id):
        suffix = f"-{n}"
        candidate = f"{base[: 32 - len(suffix)]}{suffix}"
        n += 1
        if n > 9999:
            candidate = new_id()[:8]
            break
    return candidate


def _backfill_usernames(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT id, display_name, username FROM athletes"
    ).fetchall()
    for row in rows:
        if row["username"]:
            continue
        if row["id"] == "william-lofoten":
            preferred = "william"
        else:
            preferred = slugify_username(row["display_name"] or row["id"])
        username = allocate_username(conn, preferred, exclude_id=row["id"])
        conn.execute(
            "UPDATE athletes SET username = ? WHERE id = ?",
            (username, row["id"]),
        )


def _backfill_setup_completed(conn: sqlite3.Connection, *, column_just_added: bool) -> None:
    """Mark seeded / pre-existing athletes as setup-done.

    When the column is first added, every existing row would otherwise default to 0
    and get forced into the AI setup landing — protect them.
    Always force known seed identities to completed=1.
    """
    if column_just_added:
        conn.execute("UPDATE athletes SET setup_completed = 1")
    placeholders_id = ",".join("?" for _ in SEED_PROTECTED_IDS) or "NULL"
    placeholders_user = ",".join("?" for _ in SEED_PROTECTED_USERNAMES) or "NULL"
    conn.execute(
        f"""
        UPDATE athletes SET setup_completed = 1
        WHERE id IN ({placeholders_id}) OR username IN ({placeholders_user})
        """,
        (*SEED_PROTECTED_IDS, *SEED_PROTECTED_USERNAMES),
    )


def init_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        existing = {
            r[1]
            for r in conn.execute("PRAGMA table_info(athletes)").fetchall()
        }
        setup_col_added = False
        for name, decl in _EXTRA_COLUMNS:
            if name not in existing:
                conn.execute(f"ALTER TABLE athletes ADD COLUMN {name} {decl}")
                if name == "setup_completed":
                    setup_col_added = True
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_athletes_username ON athletes(username)"
        )
        _backfill_usernames(conn)
        _backfill_setup_completed(conn, column_just_added=setup_col_added)
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
    # Default true when column missing / NULL (migration-safe)
    sbm = d.get("show_body_metrics")
    d["show_body_metrics"] = True if sbm is None else bool(sbm)
    sc = d.get("setup_completed")
    d["setup_completed"] = bool(sc) if sc is not None else False
    return d


def is_seed_protected(athlete: dict[str, Any] | None) -> bool:
    """True for explicitly seeded returning athletes (William, …)."""
    if not athlete:
        return False
    aid = athlete.get("id") or ""
    uname = normalize_username(athlete.get("username"))
    return aid in SEED_PROTECTED_IDS or uname in SEED_PROTECTED_USERNAMES


def athlete_needs_setup(athlete: dict[str, Any] | None) -> bool:
    """AI setup landing required when setup_completed is false."""
    if not athlete:
        return True
    return not bool(athlete.get("setup_completed"))


def get_athlete(conn: sqlite3.Connection, athlete_id: str) -> dict[str, Any] | None:
    cur = conn.execute("SELECT * FROM athletes WHERE id = ?", (athlete_id,))
    return row_to_athlete(cur.fetchone())


def get_athlete_by_username(
    conn: sqlite3.Connection, username: str
) -> dict[str, Any] | None:
    uname = normalize_username(username)
    if not uname:
        return None
    cur = conn.execute("SELECT * FROM athletes WHERE username = ?", (uname,))
    return row_to_athlete(cur.fetchone())


def username_available(
    conn: sqlite3.Connection, username: str, *, exclude_id: str | None = None
) -> bool:
    return not _username_taken(conn, normalize_username(username), exclude_id=exclude_id)


def insert_athlete(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    athlete_id = data.get("id") or new_id()
    agreements = data.get("agreements") or []
    raw_username = normalize_username(data.get("username"))
    if raw_username:
        err = validate_username(raw_username)
        if err:
            raise ValueError(err)
        if _username_taken(conn, raw_username):
            raise ValueError("Brukernavnet er opptatt. Velg et annet.")
        username = raw_username
    else:
        preferred = slugify_username(data.get("display_name") or athlete_id)
        if athlete_id == "william-lofoten":
            preferred = "william"
        username = allocate_username(conn, preferred, exclude_id=athlete_id)
    conn.execute(
        """
        INSERT INTO athletes (
          id, username, display_name, timezone, coach_display_name, coach_personality,
          coach_style_note, accent_color, goal_text, injury_notes, agreements_json,
          weekly_focus, ftp_tested, ftp_tested_at, weight_kg, age_years,
          sport, schedule_notes,
          nutrition_ibs, nutrition_gluten, nutrition_lactose,
          nutrition_other_restrictions, nutrition_notes, notes,
          setup_completed,
          created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            athlete_id,
            username,
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
            1 if data.get("setup_completed") else 0,
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
        "username",
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
        "show_body_metrics",
        "setup_completed",
        "athlete_type",
        "athlete_type_notes",
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
        elif key == "show_body_metrics":
            fields.append("show_body_metrics = ?")
            values.append(1 if val else 0)
        elif key == "setup_completed":
            fields.append("setup_completed = ?")
            values.append(1 if val else 0)
        elif key == "username":
            uname = normalize_username(val if isinstance(val, str) else str(val or ""))
            err = validate_username(uname)
            if err:
                raise ValueError(err)
            if _username_taken(conn, uname, exclude_id=athlete_id):
                raise ValueError("Brukernavnet er opptatt. Velg et annet.")
            fields.append("username = ?")
            values.append(uname)
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


def delete_all_plan_blocks(conn: sqlite3.Connection, athlete_id: str) -> int:
    cur = conn.execute(
        "DELETE FROM plan_blocks WHERE athlete_id = ?",
        (athlete_id,),
    )
    return cur.rowcount


def replace_plan_blocks(
    conn: sqlite3.Connection,
    athlete_id: str,
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Wipe existing meso-blocks and insert the new set (setup confirm / restart)."""
    delete_all_plan_blocks(conn, athlete_id)
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(blocks):
        data = {
            "id": raw.get("id") or f"{athlete_id}-{raw.get('key') or i}",
            "title": raw.get("title") or "",
            "theme": raw.get("theme") or "",
            "start_date": raw.get("start_date"),
            "end_date": raw.get("end_date"),
            "weekly_hours": raw.get("weekly_hours"),
            "sort_order": int(raw.get("sort_order") if raw.get("sort_order") is not None else i),
        }
        out.append(insert_plan_block(conn, athlete_id, data))
    return out


def clear_messages(conn: sqlite3.Connection, athlete_id: str) -> int:
    cur = conn.execute(
        "DELETE FROM messages WHERE athlete_id = ?",
        (athlete_id,),
    )
    return cur.rowcount


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


def insert_pending_action(
    conn: sqlite3.Connection,
    athlete_id: str,
    kind: str,
    payload: dict[str, Any],
    *,
    expires_minutes: int = 30,
) -> dict[str, Any]:
    from datetime import timedelta

    pid = new_id()
    now = utc_now()
    expires = (
        datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    ).isoformat()
    conn.execute(
        """
        INSERT INTO pending_actions (
          id, athlete_id, kind, payload_json, status, created_at, expires_at
        ) VALUES (?, ?, ?, ?, 'pending', ?, ?)
        """,
        (pid, athlete_id, kind, json.dumps(payload, ensure_ascii=False), now, expires),
    )
    return get_pending_action(conn, athlete_id, pid)  # type: ignore[return-value]


def get_pending_action(
    conn: sqlite3.Connection, athlete_id: str, action_id: str
) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT * FROM pending_actions WHERE id = ? AND athlete_id = ?",
        (action_id, athlete_id),
    )
    row = cur.fetchone()
    if not row:
        return None
    data = dict(row)
    try:
        data["payload"] = json.loads(data.get("payload_json") or "{}")
    except json.JSONDecodeError:
        data["payload"] = {}
    return data


def mark_pending_action(
    conn: sqlite3.Connection,
    athlete_id: str,
    action_id: str,
    status: str,
) -> dict[str, Any] | None:
    now = utc_now()
    conn.execute(
        """
        UPDATE pending_actions
        SET status = ?, confirmed_at = ?
        WHERE id = ? AND athlete_id = ?
        """,
        (status, now if status == "confirmed" else None, action_id, athlete_id),
    )
    return get_pending_action(conn, athlete_id, action_id)



COMPLETION_STATUSES = frozenset(
    {"completed", "skipped", "injured", "tired", "sick", "other"}
)


def _row_to_completion(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def list_session_completions(
    conn: sqlite3.Connection, athlete_id: str, *, limit: int = 100
) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT * FROM session_completions
        WHERE athlete_id = ?
        ORDER BY COALESCE(session_date, created_at) DESC, created_at DESC
        LIMIT ?
        """,
        (athlete_id, limit),
    )
    return [dict(r) for r in cur.fetchall()]


def get_session_completion(
    conn: sqlite3.Connection, athlete_id: str, external_session_id: str
) -> dict[str, Any] | None:
    cur = conn.execute(
        """
        SELECT * FROM session_completions
        WHERE athlete_id = ? AND external_session_id = ?
        """,
        (athlete_id, external_session_id),
    )
    return _row_to_completion(cur.fetchone())


def upsert_session_completion(
    conn: sqlite3.Connection, athlete_id: str, data: dict[str, Any]
) -> dict[str, Any]:
    """Insert or update a completion log for an Intervals session id."""
    now = utc_now()
    external_id = str(data.get("external_session_id") or "").strip()
    if not external_id:
        raise ValueError("external_session_id kreves")
    status = str(data.get("status") or "").strip().lower()
    if status not in COMPLETION_STATUSES:
        raise ValueError(
            f"status må være en av: {', '.join(sorted(COMPLETION_STATUSES))}"
        )
    existing = get_session_completion(conn, athlete_id, external_id)
    if existing:
        conn.execute(
            """
            UPDATE session_completions SET
              source = ?, session_name = ?, session_date = ?, discipline = ?,
              status = ?, reason = ?, note = ?, updated_at = ?
            WHERE athlete_id = ? AND external_session_id = ?
            """,
            (
                data.get("source") or existing.get("source") or "intervals",
                data.get("session_name")
                if data.get("session_name") is not None
                else existing.get("session_name") or "",
                data.get("session_date")
                if data.get("session_date") is not None
                else existing.get("session_date"),
                data.get("discipline")
                if data.get("discipline") is not None
                else existing.get("discipline") or "",
                status,
                data.get("reason")
                if data.get("reason") is not None
                else existing.get("reason") or "",
                data.get("note")
                if data.get("note") is not None
                else existing.get("note") or "",
                now,
                athlete_id,
                external_id,
            ),
        )
        return get_session_completion(conn, athlete_id, external_id)  # type: ignore[return-value]

    cid = data.get("id") or new_id()
    conn.execute(
        """
        INSERT INTO session_completions (
          id, athlete_id, external_session_id, source, session_name,
          session_date, discipline, status, reason, note, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            cid,
            athlete_id,
            external_id,
            data.get("source") or "intervals",
            data.get("session_name") or "",
            data.get("session_date") or None,
            data.get("discipline") or "",
            status,
            data.get("reason") or "",
            data.get("note") or "",
            now,
            now,
        ),
    )
    return get_session_completion(conn, athlete_id, external_id)  # type: ignore[return-value]


def completions_by_external_id(
    conn: sqlite3.Connection, athlete_id: str
) -> dict[str, dict[str, Any]]:
    rows = list_session_completions(conn, athlete_id, limit=500)
    return {r["external_session_id"]: r for r in rows if r.get("external_session_id")}
