"""FastAPI entrypoint for Lofoten coach web MVP."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
from chat_service import build_system_prompt, call_llm
from db import (
    add_message,
    db_session,
    delete_plan_block,
    get_athlete,
    get_athlete_secrets,
    init_db,
    insert_athlete,
    insert_plan_block,
    list_plan_blocks,
    recent_messages,
    secrets_public_view,
    update_athlete,
    update_plan_block,
    upsert_athlete_secrets,
)
from form_estimates import compute_form_estimates
from intervals_smoke import smoke_test_intervals
from profile import write_profile
from progress_compliance import (
    days_to_goal,
    pick_current_and_next,
    public_block,
    resolve_progress,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db(config.DATABASE_PATH)
    config.ATHLETES_DATA_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Lofoten coach-api", version="0.1.0", lifespan=lifespan)
# Starlette rejects allow_origins=["*"] together with allow_credentials=True
_cors_origins = config.CORS_ORIGINS or ["*"]
_cors_credentials = _cors_origins != ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials,
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
    season_swim_hours_target: float | None = None
    season_bike_hours_target: float | None = None
    season_run_hours_target: float | None = None
    season_strength_hours_target: float | None = None
    season_start_date: str | None = None
    goal_race_date: str | None = None


class ChatIn(BaseModel):
    message: str = Field(min_length=1)


class IntervalsCredentialsIn(BaseModel):
    intervals_athlete_id: str = Field(min_length=1)
    # Empty string keeps existing key when already connected (phone UX).
    intervals_api_key: str = ""
    verify: bool = True


class PlanBlockIn(BaseModel):
    title: str = ""
    theme: str = ""
    start_date: str | None = None
    end_date: str | None = None
    weekly_hours: float | None = None
    sort_order: int = 0


class PlanBlockPatch(BaseModel):
    title: str | None = None
    theme: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    weekly_hours: float | None = None
    sort_order: int | None = None


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
    """Store Intervals credentials first, then soft-verify (never blocks forever)."""
    aid = _require_athlete(x_athlete_id)
    icu_id = body.intervals_athlete_id.strip()
    api_key_in = body.intervals_api_key.strip()
    if not icu_id:
        raise HTTPException(400, "Intervals athlete ID kreves")

    with db_session(config.DATABASE_PATH) as conn:
        if not get_athlete(conn, aid):
            raise HTTPException(404, "Utøver ikke funnet")
        existing = get_athlete_secrets(conn, aid)
        existing_key = ((existing or {}).get("intervals_api_key") or "").strip()
        # Prefer new key; empty keeps stored key so phone users can re-save ID only.
        api_key = api_key_in or existing_key
        if not api_key:
            raise HTTPException(400, "API-nøkkel kreves (eller lagre en nøkkel først)")
        row = upsert_athlete_secrets(
            conn,
            aid,
            intervals_api_key=api_key,
            intervals_athlete_id=icu_id,
        )

    verified: bool | None = None
    verify_error: str | None = None
    if body.verify:
        ok, err = smoke_test_intervals(api_key, icu_id)
        verified = ok
        verify_error = err

    out = secrets_public_view(row)
    out["verified"] = verified
    out["verify_error"] = verify_error
    return out


@app.post("/v1/athlete/me/intervals/verify")
def verify_intervals(x_athlete_id: str | None = Header(default=None)) -> dict[str, Any]:
    """Soft-test stored Intervals credentials (5s cap). Does not change secrets."""
    aid = _require_athlete(x_athlete_id)
    with db_session(config.DATABASE_PATH) as conn:
        if not get_athlete(conn, aid):
            raise HTTPException(404, "Utøver ikke funnet")
        secrets = get_athlete_secrets(conn, aid)
    view = secrets_public_view(secrets)
    if not view.get("connected"):
        raise HTTPException(400, "Ingen Intervals-opplysninger lagret ennå")
    key = ((secrets or {}).get("intervals_api_key") or "").strip()
    icu_id = ((secrets or {}).get("intervals_athlete_id") or "").strip()
    ok, err = smoke_test_intervals(key, icu_id)
    out = dict(view)
    out["verified"] = ok
    out["verify_error"] = err
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
            athlete,
            config.KNOWLEDGE_DIR,
            overview_stub=overview,
            athletes_dir=config.ATHLETES_DATA_DIR,
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
        blocks = list_plan_blocks(conn, aid)
    return _overview_payload(athlete, secrets, blocks)


@app.get("/v1/athlete/me/plan-blocks")
def get_plan_blocks(x_athlete_id: str | None = Header(default=None)) -> dict[str, Any]:
    aid = _require_athlete(x_athlete_id)
    with db_session(config.DATABASE_PATH) as conn:
        if not get_athlete(conn, aid):
            raise HTTPException(404, "Utøver ikke funnet")
        blocks = list_plan_blocks(conn, aid)
    return {"blocks": [public_block(b) for b in blocks]}


@app.post("/v1/athlete/me/plan-blocks")
def create_plan_block(
    body: PlanBlockIn,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    aid = _require_athlete(x_athlete_id)
    with db_session(config.DATABASE_PATH) as conn:
        if not get_athlete(conn, aid):
            raise HTTPException(404, "Utøver ikke funnet")
        block = insert_plan_block(conn, aid, body.model_dump())
    return {"block": public_block(block)}


@app.patch("/v1/athlete/me/plan-blocks/{block_id}")
def patch_plan_block(
    block_id: str,
    body: PlanBlockPatch,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    aid = _require_athlete(x_athlete_id)
    patch = body.model_dump(exclude_unset=True)
    with db_session(config.DATABASE_PATH) as conn:
        if not get_athlete(conn, aid):
            raise HTTPException(404, "Utøver ikke funnet")
        block = update_plan_block(conn, aid, block_id, patch)
    if not block:
        raise HTTPException(404, "Blokk ikke funnet")
    return {"block": public_block(block)}


@app.delete("/v1/athlete/me/plan-blocks/{block_id}")
def remove_plan_block(
    block_id: str,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    aid = _require_athlete(x_athlete_id)
    with db_session(config.DATABASE_PATH) as conn:
        if not get_athlete(conn, aid):
            raise HTTPException(404, "Utøver ikke funnet")
        ok = delete_plan_block(conn, aid, block_id)
    if not ok:
        raise HTTPException(404, "Blokk ikke funnet")
    return {"ok": True}


class SeedFromRepoIn(BaseModel):
    dry_run: bool = False
    display_name: str = "William"
    coach_name: str = "Ole"
    seed_id: str = "william-lofoten"


@app.post("/v1/admin/seed-from-repo")
def admin_seed_from_repo(
    body: SeedFromRepoIn,
    x_admin_seed_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Optional: seed William from docs/athlete. Requires ADMIN_SEED_TOKEN."""
    expected = config.ADMIN_SEED_TOKEN
    if not expected:
        raise HTTPException(
            503,
            "ADMIN_SEED_TOKEN er ikke satt — bruk CLI scripts/seed_william_from_repo.py",
        )
    if not x_admin_seed_token or x_admin_seed_token != expected:
        raise HTTPException(401, "Ugyldig eller manglende X-Admin-Seed-Token")
    from seed_from_repo import seed_athlete

    return seed_athlete(
        display_name=body.display_name,
        coach_name=body.coach_name,
        seed_id=body.seed_id,
        dry_run=body.dry_run,
    )


def _overview_payload(
    athlete: dict[str, Any],
    secrets: dict[str, Any] | None = None,
    blocks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Form estimates + progress/compliance + plan strip."""
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
        intervals_hint = f"Koblet (athlete {icu}). Detaljer og kalender lever i Intervals."
        uplift = "Intervals er koblet — sesongvolum hentes fra aktiviteter."
    else:
        intervals_hint = "Ikke koblet ennå. Legg inn ID + API-nøkkel under Du → Intervals."
        uplift = "Koble Intervals under Du for ekte volum — demo-tall vises inntil da."
    if athlete.get("weekly_focus"):
        uplift = f"Ukens fokus: {athlete['weekly_focus']}"
    elif athlete.get("goal_text"):
        uplift = f"Retning: {athlete['goal_text'][:120]}"

    progress = resolve_progress(athlete, secrets)
    if progress.get("fetch_error"):
        uplift = "Intervals-henting feilet — fremskritt viser 0 t til neste forsøk."
    elif (
        not athlete.get("weekly_focus")
        and not athlete.get("goal_text")
        and progress.get("source") == "intervals"
        and intervals_linked
    ):
        n = progress.get("activity_count")
        if n is not None:
            uplift = f"Volum fra Intervals ({n} aktiviteter i sesongvinduet)."
    block_list = blocks or []
    picked = pick_current_and_next(block_list)
    days = days_to_goal(athlete)

    return {
        "plan_headline": (picked["current"] or {}).get("title") if picked.get("current") else None,
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
        "progress": progress,
        "periodization": {
            "current_block": public_block(picked.get("current")),
            "next_block": public_block(picked.get("next")),
            "days_to_goal": days,
            "goal_race_date": athlete.get("goal_race_date"),
            "season_start_date": athlete.get("season_start_date"),
            "blocks_count": len(block_list),
        },
        "season_targets": {
            "swim": athlete.get("season_swim_hours_target"),
            "bike": athlete.get("season_bike_hours_target"),
            "run": athlete.get("season_run_hours_target"),
            "strength": athlete.get("season_strength_hours_target"),
            "season_start_date": athlete.get("season_start_date"),
            "goal_race_date": athlete.get("goal_race_date"),
        },
    }


def _mount_static_ui() -> None:
    """Serve Vite build from STATIC_DIR (Fly: same origin as /v1)."""
    static = config.STATIC_DIR
    if not static:
        return
    root = Path(static)
    if not root.is_dir() or not (root / "index.html").is_file():
        return
    app.mount(
        "/",
        StaticFiles(directory=str(root), html=True),
        name="ui",
    )


_mount_static_ui()

