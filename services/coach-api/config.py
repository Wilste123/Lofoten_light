"""Coach API — FastAPI + SQLite/Postgres for Lofoten coach web MVP."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Repo root = services/coach-api/../.. locally; /app in Docker (docs/athlete next to API)
_API_DIR = Path(__file__).resolve().parent
if (_API_DIR / "docs" / "athlete").is_dir():
    REPO_ROOT = _API_DIR
else:
    # parents[0]=services, parents[1]=repo root (lofoten_light)
    REPO_ROOT = _API_DIR.parents[1]
load_dotenv(REPO_ROOT / ".env")
load_dotenv(_API_DIR / ".env")

DATABASE_PATH = Path(
    os.environ.get("DATABASE_PATH", str(REPO_ROOT / "data" / "coach.db"))
)
# Postgres / Supabase — when set, wins over DATABASE_PATH.
# Accept DATABASE_URL, SUPABASE_DB_URL, or SUPABASE_DATABASE_URL.
DATABASE_URL = (
    os.environ.get("DATABASE_URL")
    or os.environ.get("SUPABASE_DB_URL")
    or os.environ.get("SUPABASE_DATABASE_URL")
    or ""
).strip()
# Optional Supabase project metadata (not required for API DB access).
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

# Ticker email (opt-in) — Resend. Empty = send path no-ops with clear reason.
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "").strip()
COACH_APP_URL = (
    os.environ.get("COACH_APP_URL", "").strip()
    or os.environ.get("APP_PUBLIC_URL", "").strip()
)


def get_db() -> Path | str:
    """Active DB target: Postgres URL if set, else SQLite path."""
    if DATABASE_URL:
        return DATABASE_URL
    return DATABASE_PATH


def db_backend_name() -> str:
    if DATABASE_URL:
        return "postgres"
    return "sqlite"


ATHLETES_DATA_DIR = Path(
    os.environ.get(
        "ATHLETES_DATA_DIR", str(REPO_ROOT / "data" / "athletes")
    )
)
KNOWLEDGE_DIR = Path(
    os.environ.get("KNOWLEDGE_DIR", str(REPO_ROOT / "knowledge"))
)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
]
# Optional: POST /v1/admin/seed-from-repo with header X-Admin-Seed-Token
ADMIN_SEED_TOKEN = os.environ.get("ADMIN_SEED_TOKEN", "").strip()
TRAININGPEAKS_BETA_ENABLED = os.environ.get(
    "TRAININGPEAKS_BETA_ENABLED", "1"
).strip().lower() in ("1", "true", "yes")
# Built web UI (Fly / Docker). Empty → API only.
STATIC_DIR = Path(os.environ["STATIC_DIR"]) if os.environ.get("STATIC_DIR") else None
if STATIC_DIR is None:
    # Local monorepo: services/coach-api → repo root → apps/coach-web/dist
    # Avoid Path.parents[2] — raises IndexError(2) when API lives at /app/*.py
    _api = Path(__file__).resolve().parent
    _cand = None
    cur = _api
    for _ in range(4):
        parent = cur.parent
        if parent == cur:
            break
        trial = parent / "apps" / "coach-web" / "dist"
        if trial.is_dir():
            _cand = trial
            break
        cur = parent
    STATIC_DIR = _cand
