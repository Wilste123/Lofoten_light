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
    get_athlete_secrets,
    init_db,
    insert_athlete,
    recent_messages,
    secrets_public_view,
    update_athlete,
    upsert_athlete_secrets,
)
from form_estimates import compute_form_estimates
from intervals_smoke import smoke_test_intervals
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
    sport: str = "triathlon"
    schedule_notes: str = ""
    nutrition_ibs: str = "no"
    nutrition_gluten: str = "none"
    nutrition_lactose: bool = False
    nutrition_other_restrictions: str = ""
    nutrition_notes: str = ""
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
    sport: str | None = None
    schedule_notes: str | None = None
    nutrition_ibs: str | None = None
    nutrition_gluten: str | None = None
    nutrition_lactose: bool | None = None
    nutrition_other_restrictions: str | None = None
    nutrition_notes: str | None = None
    notes: str | None = None
    agreements: list[str] | None = None


class ChatIn(BaseModel):
    message: str = Field(min_length=1)


class IntervalsCredentialsIn(BaseModel):
    intervals_athlete_id: str = Field(min_length=1)
    intervals_api_key: str = Field(min_length=1)
    verify: bool = True


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
    patch = body.model_dump(exclude_unset=True)
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


@app.get("/v1/athlete/me/intervals")
def get_intervals(x_athlete_id: str | None = Header(default=None)) -> dict[str, Any]:
    """Return connection status — never the full API key."""
    aid = _require_athlete(x_athlete_id)
    with db_session(config.DATABASE_PATH) as conn:
        if not get_athlete(conn, aid):
            raise HTTPException(404, "Utøver ikke funnet")
        secrets = get_athlete_secrets(conn, aid)
    return secrets_public_view(secrets)


@app.put("/v1/athlete/me/intervals")
def put_intervals(
    body: IntervalsCredentialsIn,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Store Intervals athlete ID + API key in athlete_secrets (server only)."""
    aid = _require_athlete(x_athlete_id)
    icu_id = body.intervals_athlete_id.strip()
    api_key = body.intervals_api_key.strip()
    if not icu_id or not api_key:
        raise HTTPException(400, "Intervals athlete ID og API-nøkkel kreves")

    verified: bool | None = None
    verify_error: str | None = None
    if body.verify:
        ok, err = smoke_test_intervals(api_key, icu_id)
        verified = ok
        verify_error = err

    with db_session(config.DATABASE_PATH) as conn:
        if not get_athlete(conn, aid):
            raise HTTPException(404, "Utøver ikke funnet")
        row = upsert_athlete_secrets(
            conn,
            aid,
            intervals_api_key=api_key,
            intervals_athlete_id=icu_id,
        )
    out = secrets_public_view(row)
    out["verified"] = verified
    out["verify_error"] = verify_error
    return out


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
        secrets = get_athlete_secrets(conn, aid)
        overview = _overview_payload(athlete, secrets)
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
        secrets = get_athlete_secrets(conn, aid)
    return _overview_payload(athlete, secrets)


def _overview_payload(
    athlete: dict[str, Any],
    secrets: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Phase 1: form_estimates with empty activities → gate closed. Intervals status from secrets."""
    estimates = compute_form_estimates(
        [],
        ftp_tested=athlete.get("ftp_tested"),
        weight_kg=athlete.get("weight_kg"),
        age_years=athlete.get("age_years"),
    )
    linked = secrets_public_view(secrets)
    intervals_linked = bool(linked.get("connected"))
    if intervals_linked:
        icu = linked.get("intervals_athlete_id") or ""
        intervals_hint = f"Koblet (athlete {icu}). Kalenderdetaljer hentes i fase 2."
        uplift = "Intervals er koblet — kontekst klar for belastning når sync kommer."
    else:
        intervals_hint = "Ikke koblet ennå. Legg inn ID + API-nøkkel under Du → Intervals."
        uplift = "Koble Intervals under Du for belastning og fremgang — konteksten din er klar."
    if athlete.get("weekly_focus"):
        uplift = f"Ukens fokus: {athlete['weekly_focus']}"
    elif athlete.get("goal_text"):
        uplift = f"Retning: {athlete['goal_text'][:120]}"

    return {
        "plan_headline": None,
        "last_session": None,
        "load": None,
        "intervals_linked": intervals_linked,
        "intervals_hint": intervals_hint,
        "intervals_athlete_id": linked.get("intervals_athlete_id"),
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
