"""Coach API — FastAPI + SQLite for Lofoten coach web MVP."""

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
# Built web UI (Fly / Docker). Empty → API only.
STATIC_DIR = Path(os.environ["STATIC_DIR"]) if os.environ.get("STATIC_DIR") else None
if STATIC_DIR is None:
    _candidate = Path(__file__).resolve().parents[2] / "apps" / "coach-web" / "dist"
    STATIC_DIR = _candidate if _candidate.is_dir() else None
