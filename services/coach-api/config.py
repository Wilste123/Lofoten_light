"""Coach API — FastAPI + SQLite for Lofoten coach web MVP."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Repo root = services/coach-api/../..
REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env")

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
