"""FastAPI entrypoint for Lofoten coach web MVP."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import config
from chat_service import build_system_prompt, call_llm
from db import (
    add_message,
    db_session,
    get_athlete,
    init_db,
    insert_athlete,
    recent_messages,
    update_athlete,
)
from form_estimates import compute_form_estimates
from profile import write_profile


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db(config.DATABASE_PATH)
    config.ATHLETES_DATA_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Lofoten coach-api", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_athlete(athlete_id: str | None) -> str:
    if not athlete_id:
        raise HTTPException(401, "Mangler X-Athlete-Id")
    return athlete_id


class BootstrapIn(BaseModel):
    athlete_id: str | None = None


class OnboardingIn(BaseModel):
    display_name: str = Field(min_length=1)
    coach_display_name: str = "Rocky"
    coach_personality: str = "direkte"
    coach_style_note: str = ""
    accent_color: str = "#1a6b4a"
    goal_text: str = ""
    injury_notes: str = ""
    ftp_tested: float | None = None
    ftp_tested_at: str | None = None
    weight_kg: float | None = None
    age_years: int | None = None
    timezone: str = "Europe/Oslo"
    weekly_focus: str = ""
    notes: str = ""


class AthletePatch(BaseModel):
    display_name: str | None = None
    timezone: str | None = None
    coach_display_name: str | None = None
    coach_personality: str | None = None
    coach_style_note: str | None = None
    accent_color: str | None = None
    goal_text: str | None = None
    injury_notes: str | None = None
    weekly_focus: str | None = None
    ftp_tested: float | None = None
    ftp_tested_at: str | None = None
    weight_kg: float | None = None
    age_years: int | None = None
    notes: str | None = None
    agreements: list[str] | None = None


class ChatIn(BaseModel):
    message: str = Field(min_length=1)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/session/bootstrap")
def session_bootstrap(body: BootstrapIn) -> dict[str, Any]:
    """Return athlete if id exists; else needs_onboarding."""
    if not body.athlete_id:
        return {"needs_onboarding": True, "athlete": None}
    with db_session(config.DATABASE_PATH) as conn:
        athlete = get_athlete(conn, body.athlete_id)
    if not athlete:
        return {"needs_onboarding": True, "athlete": None}
    return {"needs_onboarding": False, "athlete": athlete}


@app.post("/v1/onboarding")
def onboarding(body: OnboardingIn) -> dict[str, Any]:
    data = body.model_dump()
    with db_session(config.DATABASE_PATH) as conn:
        athlete = insert_athlete(conn, data)
    path = write_profile(config.ATHLETES_DATA_DIR, athlete)
    return {
        "athlete": athlete,
        "profile_path": str(path.relative_to(config.REPO_ROOT))
        if path.is_relative_to(config.REPO_ROOT)
        else str(path),
    }


@app.get("/v1/athlete/me")
def get_me(x_athlete_id: str | None = Header(default=None)) -> dict[str, Any]:
    aid = _require_athlete(x_athlete_id)
    with db_session(config.DATABASE_PATH) as conn:
        athlete = get_athlete(conn, aid)
    if not athlete:
        raise HTTPException(404, "Utøver ikke funnet")
    return {"athlete": athlete}


@app.patch("/v1/athlete/me")
def patch_me(
    body: AthletePatch,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    aid = _require_athlete(x_athlete_id)
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    with db_session(config.DATABASE_PATH) as conn:
        athlete = update_athlete(conn, aid, patch)
    if not athlete:
        raise HTTPException(404, "Utøver ikke funnet")
    path = write_profile(config.ATHLETES_DATA_DIR, athlete)
    return {
        "athlete": athlete,
        "profile_path": str(path.relative_to(config.REPO_ROOT))
        if path.is_relative_to(config.REPO_ROOT)
        else str(path),
    }


@app.post("/v1/chat")
def chat(
    body: ChatIn,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    aid = _require_athlete(x_athlete_id)
    with db_session(config.DATABASE_PATH) as conn:
        athlete = get_athlete(conn, aid)
        if not athlete:
            raise HTTPException(404, "Utøver ikke funnet")
        history = recent_messages(conn, aid, limit=12)
        overview = _overview_payload(athlete)
        system = build_system_prompt(
            athlete, config.KNOWLEDGE_DIR, overview_stub=overview
        )
        reply = call_llm(
            api_key=config.OPENAI_API_KEY,
            model=config.OPENAI_MODEL,
            system=system,
            history=[{"role": m["role"], "content": m["content"]} for m in history],
            user_message=body.message,
        )
        add_message(conn, aid, "user", body.message)
        asst = add_message(conn, aid, "assistant", reply)
    return {"reply": reply, "message": asst}


@app.get("/v1/overview")
def overview(x_athlete_id: str | None = Header(default=None)) -> dict[str, Any]:
    aid = _require_athlete(x_athlete_id)
    with db_session(config.DATABASE_PATH) as conn:
        athlete = get_athlete(conn, aid)
    if not athlete:
        raise HTTPException(404, "Utøver ikke funnet")
    return _overview_payload(athlete)


def _overview_payload(athlete: dict[str, Any]) -> dict[str, Any]:
    """Phase 1 stub: no ICU. form_estimates with empty activities → gate closed."""
    estimates = compute_form_estimates(
        [],
        ftp_tested=athlete.get("ftp_tested"),
        weight_kg=athlete.get("weight_kg"),
        age_years=athlete.get("age_years"),
    )
    uplift = "Koble Intervals for belastning og fremgang — konteksten din er klar."
    if athlete.get("weekly_focus"):
        uplift = f"Ukens fokus: {athlete['weekly_focus']}"
    elif athlete.get("goal_text"):
        uplift = f"Retning: {athlete['goal_text'][:120]}"

    return {
        "plan_headline": None,
        "last_session": None,
        "load": None,
        "intervals_linked": False,
        "intervals_hint": "Koble Intervals for plan-hode og siste økt (fase 2).",
        "ftp_tested": athlete.get("ftp_tested"),
        "ftp_tested_at": athlete.get("ftp_tested_at"),
        "ftp_estimated": athlete.get("ftp_estimated") or estimates.get("ftp_estimated"),
        "vo2_estimate": athlete.get("vo2_estimate") or estimates.get("vo2_estimate"),
        "estimate_confidence": estimates.get("estimate_confidence"),
        "estimate_disclaimer": estimates.get("disclaimer"),
        "gate_open": estimates.get("gate_open"),
        "qualifying_sessions": estimates.get("qualifying_sessions"),
        "weekly_focus": athlete.get("weekly_focus"),
        "goal_text": athlete.get("goal_text"),
        "injury_notes": athlete.get("injury_notes"),
        "uplift_line": uplift,
        "partner_slots": [],
    }
