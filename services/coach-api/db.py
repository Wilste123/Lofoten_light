"""Coach-api schema and helpers — SQLite (local/tests) or Postgres/Supabase.

Schema is 1:1 across backends. Prefer ``DATABASE_URL`` / ``SUPABASE_DB_URL``;
otherwise ``DATABASE_PATH`` (SQLite volume). See ``docs/product/supabase.md``.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from db_backend import (
    Connection,
    DbTarget,
    PgConnection,
    connect as backend_connect,
    is_postgres_url,
    table_columns,
)

# Lowercase slug: letters/digits, optional hyphens, 2–32 chars.
USERNAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$")

# Serialize concurrent Postgres init_db (uvicorn lifespan + SEED_ON_BOOT).
# Transaction-scoped so Session/transaction poolers both release on commit.
_PG_INIT_ADVISORY_LOCK_KEY = 87421031
_INIT_DB_DEADLOCK_RETRIES = 3

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
  show_body_metrics INTEGER DEFAULT 0,
  setup_completed INTEGER DEFAULT 0,
  athlete_type TEXT DEFAULT '',
  athlete_type_notes TEXT DEFAULT '',
  allowed_disciplines TEXT DEFAULT '',
  sessions_per_week INTEGER,
  fitness_notes TEXT DEFAULT '',
  auth_user_id TEXT,
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
  hours_min REAL,
  hours_max REAL,
  session_types_json TEXT DEFAULT '{}',
  layer TEXT DEFAULT 'grov',
  sort_order INTEGER DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plan_windows (
  id TEXT PRIMARY KEY,
  athlete_id TEXT NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
  kind TEXT NOT NULL DEFAULT 'detalj',
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  source TEXT NOT NULL DEFAULT 'setup',
  readiness_json TEXT DEFAULT '{}',
  block_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS planned_sessions (
  id TEXT PRIMARY KEY,
  athlete_id TEXT NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
  session_date TEXT NOT NULL,
  sport TEXT NOT NULL DEFAULT 'other',
  name TEXT NOT NULL DEFAULT '',
  description TEXT DEFAULT '',
  duration_minutes INTEGER,
  start_time TEXT DEFAULT '07:00',
  planned_path TEXT DEFAULT '',
  phase TEXT DEFAULT '',
  block_id TEXT,
  window_id TEXT,
  external_id TEXT,
  source TEXT NOT NULL DEFAULT 'plan',
  status TEXT NOT NULL DEFAULT 'planned',
  plan_tier TEXT NOT NULL DEFAULT 'detalj',
  session_type TEXT DEFAULT '',
  steps_json TEXT DEFAULT '[]',
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

-- Ticker stub (coach-ticker.md) — unread strip next slice; never auto-apply plans.
CREATE TABLE IF NOT EXISTS athlete_events (
  id TEXT PRIMARY KEY,
  athlete_id TEXT NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}',
  read_at TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_athlete ON messages(athlete_id, created_at);
CREATE INDEX IF NOT EXISTS idx_plan_blocks_athlete ON plan_blocks(athlete_id, start_date);
CREATE INDEX IF NOT EXISTS idx_plan_windows_athlete ON plan_windows(athlete_id, start_date);
CREATE INDEX IF NOT EXISTS idx_planned_sessions_athlete
  ON planned_sessions(athlete_id, session_date);
CREATE INDEX IF NOT EXISTS idx_pending_actions_athlete ON pending_actions(athlete_id, created_at);
CREATE INDEX IF NOT EXISTS idx_session_completions_athlete
  ON session_completions(athlete_id, session_date);
CREATE INDEX IF NOT EXISTS idx_athlete_events_athlete
  ON athlete_events(athlete_id, created_at);
CREATE INDEX IF NOT EXISTS idx_athlete_events_unread
  ON athlete_events(athlete_id, read_at, created_at);
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


def connect(db_path: DbTarget) -> Connection:
    return backend_connect(db_path)


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
    # Privacy-first: body metrics off for new athletes. Existing DBs that
    # already have this column keep their stored values (no flip-on-migrate).
    ("show_body_metrics", "INTEGER DEFAULT 0"),
    ("setup_completed", "INTEGER DEFAULT 0"),
    ("athlete_type", "TEXT DEFAULT ''"),
    ("athlete_type_notes", "TEXT DEFAULT ''"),
    ("allowed_disciplines", "TEXT DEFAULT ''"),
    ("sessions_per_week", "INTEGER"),
    ("fitness_notes", "TEXT DEFAULT ''"),
    ("auth_user_id", "TEXT"),
    ("detalj_roll_offered_at", "TEXT"),
    ("detalj_roll_confirmed_at", "TEXT"),
    # Ticker email opt-in (coach-ticker.md) — never invent secrets
    ("email", "TEXT DEFAULT ''"),
    ("notify_email", "INTEGER DEFAULT 0"),
]

_PLAN_BLOCK_EXTRA_COLUMNS = [
    ("hours_min", "REAL"),
    ("hours_max", "REAL"),
    ("session_types_json", "TEXT DEFAULT '{}'"),
    ("layer", "TEXT DEFAULT 'grov'"),
]

_PLANNED_SESSION_EXTRA_COLUMNS = [
    ("window_id", "TEXT"),
    ("plan_tier", "TEXT DEFAULT 'detalj'"),
    ("session_type", "TEXT DEFAULT ''"),
    ("steps_json", "TEXT DEFAULT '[]'"),
]

_SECRETS_EXTRA_COLUMNS = [
    ("tp_auth_cookie", "TEXT"),
    ("tp_user_id", "TEXT"),
    ("tp_sync_enabled", "INTEGER DEFAULT 0"),
]

# Seeded returning athletes — always treated as setup-done; re-seed must not wipe them.
SEED_PROTECTED_IDS = frozenset({"william-lofoten"})
SEED_PROTECTED_USERNAMES = frozenset({"william"})


def _username_taken(
    conn: Connection, username: str, *, exclude_id: str | None = None
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
    conn: Connection,
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


def _backfill_usernames(conn: Connection) -> None:
    # ORDER BY keeps lock order stable if two migrators ever overlap without advisory lock.
    rows = conn.execute(
        "SELECT id, display_name, username FROM athletes ORDER BY id"
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


def _backfill_setup_completed(conn: Connection, *, column_just_added: bool) -> None:
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


def _is_deadlock_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "deadlock" in msg or "40p01" in msg


def init_db(db_path: DbTarget) -> None:
    """Create/migrate schema. Safe under concurrent boot (seed + lifespan)."""
    last: BaseException | None = None
    for attempt in range(_INIT_DB_DEADLOCK_RETRIES):
        try:
            _init_db_once(db_path)
            return
        except Exception as exc:
            last = exc
            if attempt + 1 < _INIT_DB_DEADLOCK_RETRIES and _is_deadlock_error(exc):
                time.sleep(0.05 * (2**attempt))
                continue
            raise
    if last is not None:  # pragma: no cover — loop always returns or raises
        raise last


def _init_db_once(db_path: DbTarget) -> None:
    with connect(db_path) as conn:
        # Postgres: enable extensions used by optional RLS helpers (safe if missing).
        if isinstance(conn, PgConnection):
            try:
                conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
            except Exception:
                conn.rollback()
                # reconnect path: extension may require superuser; schema still works
                pass
            # Must run after any rollback above. Blocks the other boot path
            # (docker_entrypoint SEED_ON_BOOT → seed_from_repo.init_db) so both
            # cannot race UPDATE athletes SET setup_completed / username backfill.
            conn.execute(
                "SELECT pg_advisory_xact_lock(?)",
                (_PG_INIT_ADVISORY_LOCK_KEY,),
            )
        conn.executescript(SCHEMA)
        existing = table_columns(conn, "athletes")
        setup_col_added = False
        for name, decl in _EXTRA_COLUMNS:
            if name not in existing:
                conn.execute(f"ALTER TABLE athletes ADD COLUMN {name} {decl}")
                if name == "setup_completed":
                    setup_col_added = True
        block_cols = table_columns(conn, "plan_blocks")
        for name, decl in _PLAN_BLOCK_EXTRA_COLUMNS:
            if name not in block_cols:
                conn.execute(f"ALTER TABLE plan_blocks ADD COLUMN {name} {decl}")
        sess_cols = table_columns(conn, "planned_sessions")
        for name, decl in _PLANNED_SESSION_EXTRA_COLUMNS:
            if name not in sess_cols:
                conn.execute(f"ALTER TABLE planned_sessions ADD COLUMN {name} {decl}")
        secret_cols = table_columns(conn, "athlete_secrets")
        for name, decl in _SECRETS_EXTRA_COLUMNS:
            if name not in secret_cols:
                conn.execute(f"ALTER TABLE athlete_secrets ADD COLUMN {name} {decl}")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_athletes_username ON athletes(username)"
        )
        try:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_athletes_auth_user_id "
                "ON athletes(auth_user_id)"
            )
        except Exception:
            pass
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_plan_windows_athlete "
            "ON plan_windows(athlete_id, start_date)"
        )
        _backfill_usernames(conn)
        _backfill_setup_completed(conn, column_just_added=setup_col_added)
        conn.commit()


@contextmanager
def db_session(db_path: DbTarget) -> Iterator[Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_to_athlete(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    d = dict(row)
    raw = d.pop("agreements_json", "[]") or "[]"
    try:
        d["agreements"] = json.loads(raw)
    except json.JSONDecodeError:
        d["agreements"] = []
    d["nutrition_lactose"] = bool(d.get("nutrition_lactose"))
    # Privacy-first: default false when column missing / NULL
    sbm = d.get("show_body_metrics")
    d["show_body_metrics"] = False if sbm is None else bool(sbm)
    sc = d.get("setup_completed")
    d["setup_completed"] = bool(sc) if sc is not None else False
    # Training agreements
    discs_raw = d.get("allowed_disciplines")
    if isinstance(discs_raw, str) and discs_raw.strip().startswith("["):
        try:
            d["allowed_disciplines"] = json.loads(discs_raw)
        except json.JSONDecodeError:
            d["allowed_disciplines"] = []
    elif not discs_raw:
        d["allowed_disciplines"] = []
    spw = d.get("sessions_per_week")
    if spw is not None and spw != "":
        try:
            d["sessions_per_week"] = int(spw)
        except (TypeError, ValueError):
            d["sessions_per_week"] = None
    else:
        d["sessions_per_week"] = None
    ne = d.get("notify_email")
    d["notify_email"] = bool(ne) if ne is not None else False
    d["email"] = (d.get("email") or "").strip().lower()
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


def get_athlete(conn: Connection, athlete_id: str) -> dict[str, Any] | None:
    cur = conn.execute("SELECT * FROM athletes WHERE id = ?", (athlete_id,))
    return row_to_athlete(cur.fetchone())


def get_athlete_by_username(
    conn: Connection, username: str
) -> dict[str, Any] | None:
    uname = normalize_username(username)
    if not uname:
        return None
    cur = conn.execute("SELECT * FROM athletes WHERE username = ?", (uname,))
    return row_to_athlete(cur.fetchone())


def username_available(
    conn: Connection, username: str, *, exclude_id: str | None = None
) -> bool:
    return not _username_taken(conn, normalize_username(username), exclude_id=exclude_id)


def insert_athlete(conn: Connection, data: dict[str, Any]) -> dict[str, Any]:
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
    # Explicit show_body_metrics: do not rely on SQLite column DEFAULT alone —
    # older DBs may still have DEFAULT 1 from when the column was first added.
    show_body = 1 if data.get("show_body_metrics") else 0
    conn.execute(
        """
        INSERT INTO athletes (
          id, username, display_name, timezone, coach_display_name, coach_personality,
          coach_style_note, accent_color, goal_text, injury_notes, agreements_json,
          weekly_focus, ftp_tested, ftp_tested_at, weight_kg, age_years,
          sport, schedule_notes,
          nutrition_ibs, nutrition_gluten, nutrition_lactose,
          nutrition_other_restrictions, nutrition_notes, notes,
          show_body_metrics, setup_completed,
          created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            show_body,
            1 if data.get("setup_completed") else 0,
            now,
            now,
        ),
    )
    return get_athlete(conn, athlete_id)  # type: ignore[return-value]


def update_athlete(
    conn: Connection, athlete_id: str, patch: dict[str, Any]
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
        "sessions_per_week",
        "fitness_notes",
        "auth_user_id",
        "detalj_roll_offered_at",
        "detalj_roll_confirmed_at",
        "email",
    }
    fields: list[str] = []
    values: list[Any] = []
    for key, val in patch.items():
        if key == "agreements":
            fields.append("agreements_json = ?")
            values.append(json.dumps(val, ensure_ascii=False))
        elif key == "allowed_disciplines":
            fields.append("allowed_disciplines = ?")
            if isinstance(val, (list, tuple)):
                values.append(json.dumps(list(val), ensure_ascii=False))
            else:
                values.append(val if val is not None else "")
        elif key == "nutrition_lactose":
            fields.append("nutrition_lactose = ?")
            values.append(1 if val else 0)
        elif key == "show_body_metrics":
            fields.append("show_body_metrics = ?")
            values.append(1 if val else 0)
        elif key == "setup_completed":
            fields.append("setup_completed = ?")
            values.append(1 if val else 0)
        elif key == "notify_email":
            fields.append("notify_email = ?")
            values.append(1 if val else 0)
        elif key == "email":
            fields.append("email = ?")
            values.append((val or "").strip().lower() if val else "")
        elif key == "username":
            uname = normalize_username(val if isinstance(val, str) else str(val or ""))
            err = validate_username(uname)
            if err:
                raise ValueError(err)
            if _username_taken(conn, uname, exclude_id=athlete_id):
                raise ValueError("Brukernavnet er opptatt. Velg et annet.")
            fields.append("username = ?")
            values.append(uname)
        elif key == "sessions_per_week":
            fields.append("sessions_per_week = ?")
            if val is None or val == "":
                values.append(None)
            else:
                values.append(int(val))
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
    conn: Connection, athlete_id: str, role: str, content: str
) -> dict[str, Any]:
    mid = new_id()
    now = utc_now()
    conn.execute(
        "INSERT INTO messages (id, athlete_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (mid, athlete_id, role, content, now),
    )
    return {"id": mid, "athlete_id": athlete_id, "role": role, "content": content, "created_at": now}


def recent_messages(
    conn: Connection, athlete_id: str, limit: int = 12
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
    conn: Connection, athlete_id: str
) -> dict[str, Any] | None:
    cur = conn.execute(
        """
        SELECT athlete_id, intervals_api_key, intervals_athlete_id,
               tp_auth_cookie, tp_user_id, tp_sync_enabled, updated_at
        FROM athlete_secrets WHERE athlete_id = ?
        """,
        (athlete_id,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def upsert_athlete_secrets(
    conn: Connection,
    athlete_id: str,
    *,
    intervals_api_key: str | None = None,
    intervals_athlete_id: str | None = None,
    tp_auth_cookie: str | None = None,
    tp_user_id: str | None = None,
    tp_sync_enabled: bool | None = None,
) -> dict[str, Any]:
    """Insert or update integration secrets. None keeps existing value."""
    existing = get_athlete_secrets(conn, athlete_id)
    now = utc_now()
    if existing is None:
        key = intervals_api_key or None
        aid = intervals_athlete_id or None
        tp_cookie = tp_auth_cookie or None
        tp_uid = tp_user_id or None
        tp_on = 1 if tp_sync_enabled else 0 if tp_sync_enabled is not None else 0
        conn.execute(
            """
            INSERT INTO athlete_secrets (
              athlete_id, intervals_api_key, intervals_athlete_id,
              tp_auth_cookie, tp_user_id, tp_sync_enabled, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (athlete_id, key, aid, tp_cookie, tp_uid, tp_on, now),
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
        tp_cookie = (
            tp_auth_cookie
            if tp_auth_cookie is not None
            else existing.get("tp_auth_cookie")
        )
        tp_uid = (
            tp_user_id if tp_user_id is not None else existing.get("tp_user_id")
        )
        if tp_sync_enabled is not None:
            tp_on = 1 if tp_sync_enabled else 0
        else:
            tp_on = existing.get("tp_sync_enabled") or 0
        conn.execute(
            """
            UPDATE athlete_secrets
            SET intervals_api_key = ?, intervals_athlete_id = ?,
                tp_auth_cookie = ?, tp_user_id = ?, tp_sync_enabled = ?,
                updated_at = ?
            WHERE athlete_id = ?
            """,
            (key, aid, tp_cookie, tp_uid, tp_on, now, athlete_id),
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


def _row_to_block(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    d = dict(row)
    raw = d.get("session_types_json") or "{}"
    if isinstance(raw, str):
        try:
            d["session_types"] = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            d["session_types"] = {}
    elif isinstance(raw, dict):
        d["session_types"] = raw
    else:
        d["session_types"] = {}
    d.setdefault("layer", d.get("layer") or "grov")
    return d


def list_plan_blocks(
    conn: Connection, athlete_id: str
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
    return [_row_to_block(r) for r in cur.fetchall()]  # type: ignore[misc]


def get_plan_block(
    conn: Connection, athlete_id: str, block_id: str
) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT * FROM plan_blocks WHERE id = ? AND athlete_id = ?",
        (block_id, athlete_id),
    )
    return _row_to_block(cur.fetchone())


def insert_plan_block(
    conn: Connection, athlete_id: str, data: dict[str, Any]
) -> dict[str, Any]:
    now = utc_now()
    block_id = data.get("id") or new_id()
    session_types = data.get("session_types")
    if session_types is None and data.get("session_types_json"):
        session_types = data.get("session_types_json")
    if isinstance(session_types, (dict, list)):
        st_json = json.dumps(session_types, ensure_ascii=False)
    else:
        st_json = str(session_types or "{}")
    conn.execute(
        """
        INSERT INTO plan_blocks (
          id, athlete_id, title, theme, start_date, end_date,
          weekly_hours, hours_min, hours_max, session_types_json, layer,
          sort_order, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            block_id,
            athlete_id,
            data.get("title") or "",
            data.get("theme") or "",
            data.get("start_date") or None,
            data.get("end_date") or None,
            data.get("weekly_hours"),
            data.get("hours_min"),
            data.get("hours_max"),
            st_json,
            str(data.get("layer") or "grov"),
            int(data.get("sort_order") or 0),
            now,
            now,
        ),
    )
    return get_plan_block(conn, athlete_id, block_id)  # type: ignore[return-value]


def update_plan_block(
    conn: Connection,
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
        "hours_min",
        "hours_max",
        "layer",
        "sort_order",
    }
    fields: list[str] = []
    values: list[Any] = []
    for key, val in patch.items():
        if key == "session_types":
            fields.append("session_types_json = ?")
            values.append(
                json.dumps(val, ensure_ascii=False)
                if isinstance(val, (dict, list))
                else (val if val is not None else "{}")
            )
            continue
        if key == "session_types_json":
            fields.append("session_types_json = ?")
            values.append(val if val is not None else "{}")
            continue
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
    conn: Connection, athlete_id: str, block_id: str
) -> bool:
    cur = conn.execute(
        "DELETE FROM plan_blocks WHERE id = ? AND athlete_id = ?",
        (block_id, athlete_id),
    )
    return cur.rowcount > 0


def delete_all_plan_blocks(conn: Connection, athlete_id: str) -> int:
    cur = conn.execute(
        "DELETE FROM plan_blocks WHERE athlete_id = ?",
        (athlete_id,),
    )
    return cur.rowcount


def replace_plan_blocks(
    conn: Connection,
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
            "hours_min": raw.get("hours_min"),
            "hours_max": raw.get("hours_max"),
            "session_types": raw.get("session_types") or raw.get("session_types_json"),
            "layer": raw.get("layer") or "grov",
            "sort_order": int(raw.get("sort_order") if raw.get("sort_order") is not None else i),
        }
        out.append(insert_plan_block(conn, athlete_id, data))
    return out


def list_planned_sessions(
    conn: Connection,
    athlete_id: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """First-class planned workouts (app plan model — not markdown)."""
    sql = """
        SELECT * FROM planned_sessions
        WHERE athlete_id = ?
    """
    params: list[Any] = [athlete_id]
    if start_date:
        sql += " AND session_date >= ?"
        params.append(start_date[:10])
    if end_date:
        sql += " AND session_date <= ?"
        params.append(end_date[:10])
    sql += " ORDER BY session_date ASC, sort_order ASC, created_at ASC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    cur = conn.execute(sql, params)
    out = []
    for r in cur.fetchall():
        d = dict(r)
        raw_steps = d.get("steps_json") or "[]"
        try:
            d["steps"] = json.loads(raw_steps) if isinstance(raw_steps, str) else (raw_steps or [])
        except json.JSONDecodeError:
            d["steps"] = []
        out.append(d)
    return out


def count_planned_sessions(conn: Connection, athlete_id: str) -> int:
    cur = conn.execute(
        "SELECT COUNT(*) AS n FROM planned_sessions WHERE athlete_id = ?",
        (athlete_id,),
    )
    row = cur.fetchone()
    return int(row["n"] if row else 0)


def delete_all_planned_sessions(conn: Connection, athlete_id: str) -> int:
    cur = conn.execute(
        "DELETE FROM planned_sessions WHERE athlete_id = ?",
        (athlete_id,),
    )
    return cur.rowcount


def delete_planned_sessions_range(
    conn: Connection,
    athlete_id: str,
    start_date: str,
    end_date: str,
) -> int:
    """Delete planned sessions in [start_date, end_date] (inclusive)."""
    cur = conn.execute(
        """
        DELETE FROM planned_sessions
        WHERE athlete_id = ?
          AND session_date >= ?
          AND session_date <= ?
        """,
        (athlete_id, start_date[:10], end_date[:10]),
    )
    return cur.rowcount


def delete_planned_sessions_by_external_ids(
    conn: Connection,
    athlete_id: str,
    external_ids: list[str],
) -> int:
    """Remove planned rows matching external_id (chat upsert / replace)."""
    ids = [str(x).strip() for x in external_ids if str(x).strip()]
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    cur = conn.execute(
        f"""
        DELETE FROM planned_sessions
        WHERE athlete_id = ?
          AND external_id IN ({placeholders})
        """,
        [athlete_id, *ids],
    )
    return cur.rowcount


def delete_planned_sessions_by_ids(
    conn: Connection,
    athlete_id: str,
    session_ids: list[str],
) -> int:
    """Remove planned rows by primary key (cap-replace / chat swap)."""
    ids = [str(x).strip() for x in session_ids if str(x).strip()]
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    cur = conn.execute(
        f"""
        DELETE FROM planned_sessions
        WHERE athlete_id = ?
          AND id IN ({placeholders})
        """,
        [athlete_id, *ids],
    )
    return cur.rowcount


def insert_planned_session_rows(
    conn: Connection,
    athlete_id: str,
    sessions: list[dict[str, Any]],
    *,
    sort_offset: int = 0,
) -> list[dict[str, Any]]:
    """Insert planned_session rows without wiping the rest of the horizon."""
    now = utc_now()
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(sessions):
        day = str(raw.get("session_date") or raw.get("date") or "").strip()[:10]
        if not day:
            continue
        sid = raw.get("id") or new_id()
        name = str(raw.get("name") or raw.get("title") or "Økt").strip()[:200]
        sport = str(raw.get("sport") or "other").strip().lower()[:40] or "other"
        try:
            dur = raw.get("duration_minutes")
            dur_i = int(float(dur)) if dur is not None and str(dur).strip() else None
        except (TypeError, ValueError):
            dur_i = None
        start_time = str(raw.get("start_time") or "07:00").strip()[:5] or "07:00"
        external = str(raw.get("external_id") or "").strip()[:120] or None
        sort_i = int(
            raw.get("sort_order")
            if raw.get("sort_order") is not None
            else sort_offset + i
        )
        window_id = raw.get("window_id")
        plan_tier = str(raw.get("plan_tier") or "detalj").strip()[:40] or "detalj"
        session_type = str(raw.get("session_type") or "").strip()[:40]
        steps = raw.get("steps") if raw.get("steps") is not None else raw.get("steps_json")
        if isinstance(steps, (list, dict)):
            steps_json = json.dumps(steps, ensure_ascii=False)
        elif steps is None:
            steps_json = "[]"
        else:
            steps_json = str(steps) or "[]"
        conn.execute(
            """
            INSERT INTO planned_sessions (
              id, athlete_id, session_date, sport, name, description,
              duration_minutes, start_time, planned_path, phase, block_id,
              window_id, external_id, source, status, plan_tier, session_type,
              steps_json, sort_order, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sid,
                athlete_id,
                day,
                sport,
                name,
                str(raw.get("description") or "").strip()[:4000],
                dur_i,
                start_time,
                str(raw.get("planned_path") or raw.get("planned") or "").strip()[:400],
                str(raw.get("phase") or "").strip()[:40],
                raw.get("block_id"),
                window_id,
                external,
                str(raw.get("source") or "plan").strip()[:40] or "plan",
                str(raw.get("status") or "planned").strip()[:40] or "planned",
                plan_tier,
                session_type,
                steps_json,
                sort_i,
                now,
                now,
            ),
        )
        out.append(
            {
                "id": sid,
                "athlete_id": athlete_id,
                "session_date": day,
                "sport": sport,
                "name": name,
                "description": str(raw.get("description") or "").strip()[:4000],
                "duration_minutes": dur_i,
                "start_time": start_time,
                "planned_path": str(raw.get("planned_path") or raw.get("planned") or ""),
                "phase": str(raw.get("phase") or ""),
                "block_id": raw.get("block_id"),
                "window_id": window_id,
                "external_id": external,
                "source": str(raw.get("source") or "plan"),
                "status": str(raw.get("status") or "planned"),
                "plan_tier": plan_tier,
                "session_type": session_type,
                "steps_json": steps_json,
                "steps": json.loads(steps_json) if steps_json.startswith("[") else [],
                "sort_order": sort_i,
                "created_at": now,
                "updated_at": now,
            }
        )
    return out


def replace_planned_sessions_range(
    conn: Connection,
    athlete_id: str,
    start_date: str,
    end_date: str,
    sessions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Surgical week (or range) replace — leaves the rest of the horizon intact."""
    delete_planned_sessions_range(conn, athlete_id, start_date, end_date)
    return insert_planned_session_rows(conn, athlete_id, sessions)


def replace_planned_sessions(
    conn: Connection,
    athlete_id: str,
    sessions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Replace detaljplan sessions (setup / roll confirm — not silent year rewrite)."""
    delete_all_planned_sessions(conn, athlete_id)
    return insert_planned_session_rows(conn, athlete_id, sessions)


def get_active_plan_window(
    conn: Connection, athlete_id: str, *, kind: str = "detalj"
) -> dict[str, Any] | None:
    cur = conn.execute(
        """
        SELECT * FROM plan_windows
        WHERE athlete_id = ? AND kind = ? AND status = 'active'
        ORDER BY end_date DESC, created_at DESC
        LIMIT 1
        """,
        (athlete_id, kind),
    )
    row = cur.fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["readiness"] = json.loads(d.get("readiness_json") or "{}")
    except json.JSONDecodeError:
        d["readiness"] = {}
    return d


def deactivate_plan_windows(
    conn: Connection, athlete_id: str, *, kind: str = "detalj"
) -> int:
    cur = conn.execute(
        """
        UPDATE plan_windows
        SET status = 'superseded', updated_at = ?
        WHERE athlete_id = ? AND kind = ? AND status = 'active'
        """,
        (utc_now(), athlete_id, kind),
    )
    return cur.rowcount


def insert_plan_window(
    conn: Connection,
    athlete_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    now = utc_now()
    wid = data.get("id") or new_id()
    readiness = data.get("readiness") or data.get("readiness_json") or {}
    if isinstance(readiness, (dict, list)):
        r_json = json.dumps(readiness, ensure_ascii=False)
    else:
        r_json = str(readiness or "{}")
    conn.execute(
        """
        INSERT INTO plan_windows (
          id, athlete_id, kind, start_date, end_date, status, source,
          readiness_json, block_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            wid,
            athlete_id,
            str(data.get("kind") or "detalj"),
            str(data["start_date"])[:10],
            str(data["end_date"])[:10],
            str(data.get("status") or "active"),
            str(data.get("source") or "setup"),
            r_json,
            data.get("block_id"),
            now,
            now,
        ),
    )
    return get_active_plan_window(conn, athlete_id) or {
        "id": wid,
        "athlete_id": athlete_id,
        "kind": data.get("kind") or "detalj",
        "start_date": str(data["start_date"])[:10],
        "end_date": str(data["end_date"])[:10],
        "status": data.get("status") or "active",
        "source": data.get("source") or "setup",
        "readiness": readiness if isinstance(readiness, dict) else {},
        "block_id": data.get("block_id"),
        "created_at": now,
        "updated_at": now,
    }


def replace_detalj_window(
    conn: Connection,
    athlete_id: str,
    *,
    start_date: str,
    end_date: str,
    sessions: list[dict[str, Any]],
    source: str = "setup",
    readiness: dict[str, Any] | None = None,
    block_id: str | None = None,
) -> dict[str, Any]:
    """Supersede active detalj window, insert new window + sessions."""
    deactivate_plan_windows(conn, athlete_id, kind="detalj")
    window = insert_plan_window(
        conn,
        athlete_id,
        {
            "kind": "detalj",
            "start_date": start_date,
            "end_date": end_date,
            "status": "active",
            "source": source,
            "readiness": readiness or {},
            "block_id": block_id,
        },
    )
    wid = window.get("id")
    stamped = []
    for s in sessions:
        row = dict(s)
        row["window_id"] = wid
        row["plan_tier"] = row.get("plan_tier") or "detalj"
        stamped.append(row)
    delete_all_planned_sessions(conn, athlete_id)
    saved = insert_planned_session_rows(conn, athlete_id, stamped)
    return {"window": window, "sessions": saved, "count": len(saved)}


def mark_detalj_roll_offered(conn: Connection, athlete_id: str) -> None:
    conn.execute(
        "UPDATE athletes SET detalj_roll_offered_at = ?, updated_at = ? WHERE id = ?",
        (utc_now(), utc_now(), athlete_id),
    )


def mark_detalj_roll_confirmed(conn: Connection, athlete_id: str) -> None:
    now = utc_now()
    conn.execute(
        """
        UPDATE athletes
        SET detalj_roll_confirmed_at = ?, detalj_roll_offered_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (now, now, now, athlete_id),
    )


def get_planned_session(
    conn: Connection, athlete_id: str, session_id: str
) -> dict[str, Any] | None:
    """Lookup by row id or external_id (evt:… stripped)."""
    sid = (session_id or "").strip()
    if sid.startswith("evt:"):
        sid = sid[4:]
    cur = conn.execute(
        """
        SELECT * FROM planned_sessions
        WHERE athlete_id = ? AND (id = ? OR external_id = ?)
        LIMIT 1
        """,
        (athlete_id, session_id.strip(), sid),
    )
    row = cur.fetchone()
    if not row:
        return None
    d = dict(row)
    raw_steps = d.get("steps_json") or "[]"
    try:
        d["steps"] = json.loads(raw_steps) if isinstance(raw_steps, str) else (raw_steps or [])
    except json.JSONDecodeError:
        d["steps"] = []
    return d


def update_planned_session_builder(
    conn: Connection,
    athlete_id: str,
    session_id: str,
    patch: dict[str, Any],
) -> dict[str, Any] | None:
    """Persist visual builder fields onto a planned_sessions row (app SoT)."""
    existing = get_planned_session(conn, athlete_id, session_id)
    if not existing:
        return None
    fields: list[str] = []
    values: list[Any] = []
    mapping = {
        "name": "name",
        "session_date": "session_date",
        "sport": "sport",
        "description": "description",
        "duration_minutes": "duration_minutes",
        "start_time": "start_time",
        "session_type": "session_type",
    }
    for key, col in mapping.items():
        if key in patch and patch[key] is not None:
            fields.append(f"{col} = ?")
            val = patch[key]
            if key == "session_date":
                val = str(val)[:10]
            elif key == "duration_minutes":
                val = int(val)
            elif key == "start_time":
                val = str(val)[:5]
            values.append(val)
    if "steps" in patch:
        steps = patch["steps"] or []
        fields.append("steps_json = ?")
        values.append(json.dumps(steps, ensure_ascii=False))
        # Keep description in sync for Intervals/text consumers unless explicit override
        if "description" not in patch:
            from sessions_service import builder_steps_to_description

            fields.append("description = ?")
            values.append(builder_steps_to_description(steps)[:4000])
    if not fields:
        return existing
    fields.append("updated_at = ?")
    values.append(utc_now())
    values.extend([existing["id"], athlete_id])
    conn.execute(
        f"UPDATE planned_sessions SET {', '.join(fields)} WHERE id = ? AND athlete_id = ?",
        values,
    )
    return get_planned_session(conn, athlete_id, existing["id"])


def clear_messages(conn: Connection, athlete_id: str) -> int:
    cur = conn.execute(
        "DELETE FROM messages WHERE athlete_id = ?",
        (athlete_id,),
    )
    return cur.rowcount


def hash_invite_token(token: str) -> str:
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def insert_invite(
    conn: Connection,
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


def invite_token_valid(conn: Connection, token: str) -> bool:
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
    conn: Connection,
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
    conn: Connection, athlete_id: str, action_id: str
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
    conn: Connection,
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


def _row_to_completion(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def list_session_completions(
    conn: Connection, athlete_id: str, *, limit: int = 100
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
    conn: Connection, athlete_id: str, external_session_id: str
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
    conn: Connection, athlete_id: str, data: dict[str, Any]
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
    conn: Connection, athlete_id: str
) -> dict[str, dict[str, Any]]:
    rows = list_session_completions(conn, athlete_id, limit=500)
    return {r["external_session_id"]: r for r in rows if r.get("external_session_id")}


def _row_to_athlete_event(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    try:
        data["payload"] = json.loads(data.get("payload_json") or "{}")
    except json.JSONDecodeError:
        data["payload"] = {}
    return data


def insert_athlete_event(
    conn: Connection,
    athlete_id: str,
    *,
    kind: str,
    title: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    eid = new_id()
    now = utc_now()
    conn.execute(
        """
        INSERT INTO athlete_events (
          id, athlete_id, kind, title, payload_json, read_at, created_at
        ) VALUES (?, ?, ?, ?, ?, NULL, ?)
        """,
        (
            eid,
            athlete_id,
            kind,
            title or "",
            json.dumps(payload or {}, ensure_ascii=False),
            now,
        ),
    )
    return get_athlete_event(conn, athlete_id, eid)  # type: ignore[return-value]


def get_athlete_event(
    conn: Connection, athlete_id: str, event_id: str
) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT * FROM athlete_events WHERE id = ? AND athlete_id = ?",
        (event_id, athlete_id),
    )
    return _row_to_athlete_event(cur.fetchone())


def list_athlete_events(
    conn: Connection,
    athlete_id: str,
    *,
    unread_only: bool = False,
    limit: int = 30,
) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit or 30), 100))
    if unread_only:
        cur = conn.execute(
            """
            SELECT * FROM athlete_events
            WHERE athlete_id = ? AND read_at IS NULL
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (athlete_id, lim),
        )
    else:
        cur = conn.execute(
            """
            SELECT * FROM athlete_events
            WHERE athlete_id = ?
            ORDER BY CASE WHEN read_at IS NULL THEN 0 ELSE 1 END, created_at DESC
            LIMIT ?
            """,
            (athlete_id, lim),
        )
    return [
        r for r in (_row_to_athlete_event(row) for row in cur.fetchall()) if r
    ]


def latest_event_of_kind(
    conn: Connection, athlete_id: str, kind: str
) -> dict[str, Any] | None:
    cur = conn.execute(
        """
        SELECT * FROM athlete_events
        WHERE athlete_id = ? AND kind = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (athlete_id, kind),
    )
    return _row_to_athlete_event(cur.fetchone())


def mark_athlete_event_read(
    conn: Connection, athlete_id: str, event_id: str
) -> dict[str, Any] | None:
    now = utc_now()
    conn.execute(
        """
        UPDATE athlete_events
        SET read_at = ?
        WHERE id = ? AND athlete_id = ? AND read_at IS NULL
        """,
        (now, event_id, athlete_id),
    )
    return get_athlete_event(conn, athlete_id, event_id)


def mark_all_athlete_events_read(
    conn: Connection, athlete_id: str
) -> int:
    now = utc_now()
    cur = conn.execute(
        """
        UPDATE athlete_events
        SET read_at = ?
        WHERE athlete_id = ? AND read_at IS NULL
        """,
        (now, athlete_id),
    )
    return int(cur.rowcount or 0)


def count_unread_athlete_events(conn: Connection, athlete_id: str) -> int:
    cur = conn.execute(
        """
        SELECT COUNT(*) AS n FROM athlete_events
        WHERE athlete_id = ? AND read_at IS NULL
        """,
        (athlete_id,),
    )
    row = cur.fetchone()
    if not row:
        return 0
    d = dict(row)
    return int(d.get("n") or 0)
