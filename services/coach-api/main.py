"""FastAPI entrypoint for Lofoten coach web MVP."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from datetime import date, timedelta
import logging
import os
import re
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config

logger = logging.getLogger("coach-api")

# Set during lifespan when DATABASE_URL/init_db fails — HTTP still serves
# static + /health so the UI is not wedged behind an infinite spinner.
_DB_BOOT_ERROR: str | None = None

from athlete_type import (
    SPORT_FOR_TYPE,
    append_type_history,
    infer_athlete_type,
    label_for,
    normalize_athlete_type,
    propose_type_update,
)
from athlete_constraints import ICU_SYNC_WEEKS, validate_workouts_against_constraints
from chat_service import (
    build_system_prompt,
    call_llm,
    confirm_write_success_reply_nb,
    extract_agreements_update,
    extract_plan_update,
    extract_workout_proposal,
    extract_workout_removal,
    infer_plan_update_fallback,
    infer_workout_proposal_fallback,
    extract_type_update_proposal,
    intervals_plan_sync_reply_nb,
    knowledge_meta_for_chat,
    plan_summary_for_chat,
    reopen_pending_write_reply,
    sanitize_unconfirmed_write_claims,
    strip_workout_json_from_prose,
    user_confirms_intervals_plan_sync,
    user_confirms_pending_write,
    user_requests_confirm_and_push,
    user_requests_intervals_plan_sync,
    user_requests_plan_adjust,
    user_requests_session_change,
    workout_proposal_history_summary,
    write_intent_kind,
)
from db import (
    add_message,
    athlete_needs_setup,
    clear_messages,
    completions_by_external_id,
    count_planned_sessions,
    db_session,
    delete_all_plan_blocks,
    delete_all_planned_sessions,
    delete_plan_block,
    delete_planned_sessions_by_external_ids,
    delete_planned_sessions_by_ids,
    get_active_plan_window,
    get_athlete,
    get_athlete_by_username,
    get_athlete_secrets,
    get_pending_action,
    get_planned_session,
    init_db,
    insert_athlete,
    insert_pending_action,
    insert_plan_block,
    insert_planned_session_rows,
    invite_token_valid,
    list_plan_blocks,
    list_planned_sessions,
    list_session_completions,
    mark_all_athlete_events_read,
    mark_detalj_roll_confirmed,
    mark_detalj_roll_offered,
    mark_pending_action,
    normalize_username,
    recent_messages,
    replace_detalj_window,
    replace_plan_blocks,
    replace_planned_sessions,
    replace_planned_sessions_range,
    secrets_public_view,
    update_athlete,
    update_plan_block,
    update_planned_session_builder,
    upsert_athlete_secrets,
    upsert_session_completion,
    utc_now,
    validate_username,
    count_unread_athlete_events,
)
from two_tier_plan import (
    DETAIL_WEEKS,
    build_roll_proposal_card,
    build_two_tier_plan_payload,
    enrich_grov_blocks,
    evaluate_roll_trigger,
    readiness_from_overview,
    user_requests_explicit_roll,
)
from beta_forecasts import build_beta_forecasts
from form_from_intervals import clear_form_caches, persist_estimates_patch, resolve_form_estimates
from trainingpeaks_beta.sync import (
    preview_tp_push,
    push_tp_workouts,
    tp_public_status,
    verify_tp_credentials,
)
from intervals_calendar import (
    build_block_note_events,
    build_workout_events,
    delete_events_bulk,
    event_local_date,
    fetch_events,
    filter_coach_events,
    filter_events_in_date_range,
    parse_iso_date,
    post_events_bulk,
    public_event_preview,
    select_blocks,
    status_window_for_blocks,
)
from intervals_smoke import smoke_test_intervals
from period_training import (
    PeriodValidationError,
    parse_period_window,
    resolve_period_training,
)
from profile import write_profile
from progress_compliance import (
    clear_progress_cache,
    days_to_goal,
    pick_current_and_next,
    public_block,
    resolve_progress,
)
from plan_workouts import (
    build_plan_sync_bundle,
    build_week_adjust_sessions,
    events_preview_for_plan_sync,
    filter_planned_sessions_date_range,
    format_exc_nb,
    persistable_plan_payload,
    plan_horizon_weeks,
    readiness_adjustment_hints,
)
from setup_plan import (
    build_setup_chat_system,
    build_setup_preview,
    extract_setup_fields,
    merge_draft,
    merge_confirm_athlete_patch,
    enrich_draft_from_text,
    compose_goal_text,
)
from ticker import (
    emit_sessions_saved,
    emit_sync_fail,
    emit_sync_ok,
    emit_weekly_cap_replace,
    list_public_events,
    mark_read as ticker_mark_read,
    refresh_soft_ticker,
    resend_configured,
    validate_email,
)
from sessions_service import (
    completion_note_line,
    find_session_in_bundle,
    list_sessions,
    merge_planned_sessions,
    session_detail_payload,
    session_focus_for_chat,
    sessions_snapshot_for_chat,
)
from wellness import clear_wellness_cache, resolve_wellness_bundle


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Init DB with fail-fast timeouts; never hang forever on bad DATABASE_URL.

    On Postgres failure we still yield so ``/health`` + static UI answer and the
    browser can show an error instead of spinning until Fly edge times out.
    Set ``DB_STRICT_BOOT=1`` to exit the process instead (crash-loop / louder Fly).
    """
    global _DB_BOOT_ERROR
    _DB_BOOT_ERROR = None
    target = config.get_db()
    try:
        init_db(target)
        logger.info("db boot ok backend=%s", config.db_backend_name())
    except Exception as exc:
        msg = str(exc)
        _DB_BOOT_ERROR = msg
        logger.exception(
            "db boot FAILED backend=%s — serving degraded (static+/health). %s",
            config.db_backend_name(),
            msg,
        )
        strict = (os.environ.get("DB_STRICT_BOOT") or "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if strict:
            raise SystemExit(f"DB_STRICT_BOOT: {msg}") from exc
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


@app.middleware("http")
async def _reject_when_db_down(request: Request, call_next):
    """Fail-fast 503 on /v1/* when boot-time Postgres init failed."""
    if _DB_BOOT_ERROR and request.url.path.startswith("/v1/"):
        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    "Database utilgjengelig etter boot. Sjekk DATABASE_URL "
                    "(sslmode=require for Supabase Session/direct), kjør "
                    "migrations/001_supabase_schema.sql, deretter "
                    f"fly logs -a lofoten-coach. ({_DB_BOOT_ERROR[:240]})"
                ),
                "db_ok": False,
            },
        )
    return await call_next(request)


def _require_athlete(athlete_id: str | None) -> str:
    if not athlete_id:
        raise HTTPException(401, "Mangler X-Athlete-Id")
    return athlete_id


def _sessions_bundle_for_athlete(
    conn,
    aid: str,
    *,
    secrets: dict[str, Any] | None = None,
    comps: dict[str, dict[str, Any]] | None = None,
    past_days: int = 14,
    future_days: int = 14,
    today: date | None = None,
) -> dict[str, Any]:
    """ICU list + app ``planned_sessions`` → one Økter/Plan model (no invented compliance)."""
    if secrets is None:
        secrets = get_athlete_secrets(conn, aid)
    if comps is None:
        comps = completions_by_external_id(conn, aid)
    planned = list_planned_sessions(conn, aid)
    bundle = list_sessions(
        secrets,
        comps,
        past_days=past_days,
        future_days=future_days,
        today=today,
    )
    return merge_planned_sessions(
        bundle, planned, today=today, completions=comps
    )


class BootstrapIn(BaseModel):
    athlete_id: str | None = None


class LoginIn(BaseModel):
    """Login with username (preferred) or athlete_id. No passwords."""

    username: str | None = None
    athlete_id: str | None = None
    invite_token: str | None = None


class OnboardingIn(BaseModel):
    display_name: str = Field(min_length=1)
    username: str = Field(min_length=2, max_length=32)
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


class SetupDraftIn(BaseModel):
    """Guided setup draft — preview only until /v1/setup/confirm."""

    display_name: str = ""
    username: str = ""
    coach_display_name: str = "Rocky"
    coach_personality: str = "direkte"
    coach_style_note: str = ""
    accent_color: str = "#1a6b4a"
    goal_text: str = ""
    injury_notes: str = ""
    schedule_notes: str = ""
    background_notes: str = ""
    coach_respect_notes: str = ""
    notes: str = ""
    fitness_notes: str = ""
    weekly_focus: str = ""
    weekly_hours_target: float | None = None
    season_start_date: str | None = None
    goal_race_date: str | None = None
    ftp_tested: float | None = None
    ftp_tested_at: str | None = None
    weight_kg: float | None = None
    age_years: int | None = None
    sport: str = "triathlon"
    athlete_type: str = ""
    sessions_per_week: int | None = None
    allowed_disciplines: list[str] = Field(default_factory=list)
    nutrition_ibs: str = "no"
    nutrition_gluten: str = "none"
    nutrition_lactose: bool = False
    nutrition_other_restrictions: str = ""
    nutrition_notes: str = ""
    agreements: list[str] = Field(default_factory=list)
    # Optional Intervals — stored only on confirm; used to preview NOTE events.
    intervals_athlete_id: str = ""
    intervals_api_key: str = ""
    enrich_with_llm: bool = True


class SetupChatIn(BaseModel):
    """One adaptive coach turn during landing setup."""

    message: str = Field(min_length=1)
    draft: SetupDraftIn = Field(default_factory=SetupDraftIn)
    history: list[dict[str, str]] = Field(default_factory=list)


class SetupConfirmIn(SetupDraftIn):
    """Persist profile + plan_blocks after athlete reviewed preview."""

    plan_blocks: list[dict[str, Any]] = Field(default_factory=list)
    athlete_patch: dict[str, Any] = Field(default_factory=dict)
    # Existing athlete (restart flow) — never creates a second row.
    athlete_id: str | None = None
    # If true AND credentials present: create calendar pending (still needs confirm).
    prepare_intervals_sync: bool = False


class SetupResetIn(BaseModel):
    """Two-step wipe: both flags required before deleting plan/goals.

    Optional: delete only coach-pushed Intervals events (ll-coach-*), never wipe
    the whole calendar.
    """

    acknowledge_wipe: bool = False
    confirm_phrase: str = ""
    delete_intervals_coach_events: bool = False
    acknowledge_intervals_delete: bool = False


class AthleteTypeUpdateIn(BaseModel):
    """Explicit confirm to change mutable hovedprofil (may rewrite plan)."""

    athlete_type: str = Field(min_length=1)
    reason: str = ""
    rebuild_plan_preview: bool = True


class PlanAdjustPreviewIn(BaseModel):
    """Rebuild meso-plan from current Du-profile — preview only, no silent write."""

    enrich_with_llm: bool = True
    prepare_intervals_sync: bool = False


class PlanAdjustConfirmIn(BaseModel):
    """Replace plan_blocks + planned_sessions after athlete reviewed adjust preview."""

    plan_blocks: list[dict[str, Any]] = Field(default_factory=list)
    athlete_patch: dict[str, Any] = Field(default_factory=dict)
    prepare_intervals_sync: bool = False


class WeekAdjustPreviewIn(BaseModel):
    """Surgical one-week rebuild — preview only, rest of horizon untouched."""

    week_start: str | None = None  # YYYY-MM-DD or "this_week"
    ease_load: bool = False


class WeekAdjustConfirmIn(BaseModel):
    """Confirm surgical week replace in planned_sessions."""

    week_start: str
    week_end: str
    sessions: list[dict[str, Any]] = Field(default_factory=list)
    ease_load: bool = False
    prepare_intervals_sync: bool = False


class PlanRollConfirmIn(BaseModel):
    """Confirm next detalj window (~DETAIL_WEEKS) — never silent year rewrite."""

    detalj_start: str
    detalj_end: str
    sessions: list[dict[str, Any]] = Field(default_factory=list)
    readiness: dict[str, Any] = Field(default_factory=dict)
    prepare_intervals_sync: bool = False


def _persist_plan_horizon_sessions(
    conn: Any,
    athlete_id: str,
    blocks: list[dict[str, Any]],
    athlete: dict[str, Any],
    *,
    today: date | None = None,
    source: str = "setup",
    readiness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist grovplan blocks meta + detaljplan (~DETAIL_WEEKS) sessions.

    Never materializes a full-year of workouts. Intervals sync stays near-window.
    """
    payload = build_two_tier_plan_payload(
        blocks, athlete=athlete, today=today, readiness=readiness
    )
    # Ensure DB blocks carry grov enrichment (hours band + session types)
    enriched = payload.get("grov_blocks") or enrich_grov_blocks(blocks, athlete=athlete)
    # Caller may already have saved blocks; re-stamp enrichment when ids match
    for b in enriched:
        bid = b.get("id")
        if bid:
            update_plan_block(
                conn,
                athlete_id,
                bid,
                {
                    "hours_min": b.get("hours_min"),
                    "hours_max": b.get("hours_max"),
                    "session_types": b.get("session_types"),
                    "layer": "grov",
                },
            )
    result = replace_detalj_window(
        conn,
        athlete_id,
        start_date=payload["detalj_start"],
        end_date=payload["detalj_end"],
        sessions=payload.get("sessions") or [],
        source=source,
        readiness=readiness,
    )
    if source in ("roll", "rolling", "coach_roll"):
        mark_detalj_roll_confirmed(conn, athlete_id)
    return {
        "planned_sessions": result["sessions"],
        "planned_sessions_count": result["count"],
        "plan_horizon_weeks": payload.get("grov_horizon_weeks"),
        "detalj_weeks": payload.get("detalj_weeks"),
        "detalj_start": payload.get("detalj_start"),
        "detalj_end": payload.get("detalj_end"),
        "plan_window": result.get("window"),
        "icu_sync_weeks": payload.get("icu_sync_weeks"),
        "horizon_note_nb": payload.get("horizon_note_nb"),
        "goal_race_date": payload.get("goal_race_date") or athlete.get("goal_race_date"),
        "tier_model": "grov+detalj",
    }


def _sync_bundle_preferring_stored(
    conn: Any,
    athlete_id: str,
    blocks: list[dict[str, Any]],
    athlete: dict[str, Any],
    *,
    allow_degraded: bool = False,
    include_notes: bool = False,
) -> dict[str, Any]:
    """Near-window ICU bundle: prefer athlete's stored planned_sessions when present.

    Grovplan NOTES are off by default for chat/near-window Sync — opt in via
    ``include_notes=True``.
    """
    stored = list_planned_sessions(conn, athlete_id)
    return build_plan_sync_bundle(
        blocks,
        athlete=athlete,
        include_notes=include_notes,
        allow_degraded=allow_degraded,
        planned_sessions=stored if stored else None,
    )


class WorkoutRemovePreviewIn(BaseModel):
    """Preview delete of coach-scheduled workouts — confirm before ICU write."""

    external_ids: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    oldest: str | None = None
    newest: str | None = None


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
    athlete_type: str | None = None
    sport: str | None = None
    schedule_notes: str | None = None
    sessions_per_week: int | None = None
    allowed_disciplines: list[str] | None = None
    notes: str | None = None
    fitness_notes: str | None = None
    show_body_metrics: bool | None = None
    weight_kg: float | None = None
    age_years: int | None = None
    nutrition_ibs: str | None = None
    nutrition_gluten: str | None = None
    nutrition_lactose: bool | None = None
    nutrition_other_restrictions: str | None = None
    nutrition_notes: str | None = None
    agreements: list[str] | None = None
    season_swim_hours_target: float | None = None
    season_bike_hours_target: float | None = None
    season_run_hours_target: float | None = None
    season_strength_hours_target: float | None = None
    season_start_date: str | None = None
    goal_race_date: str | None = None
    email: str | None = None
    notify_email: bool | None = None


class ChatIn(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = Field(
        default=None,
        description="Optional: focus chat on one Økter session (detail-view chat).",
    )


class SessionEditPreviewIn(BaseModel):
    """Athlete-edited fields → Intervals workout preview (confirm required)."""

    name: str = Field(min_length=1)
    date: str = Field(min_length=10, max_length=10)
    sport: str = "other"
    duration_minutes: int | None = None
    description: str = ""
    start_time: str = "07:00"
    # When set, reuse same external_id for upsert of that day
    external_id: str | None = None
    # Visual builder steps (optional — also used by /builder/confirm)
    steps: list[dict[str, Any]] = Field(default_factory=list)


class SessionBuilderConfirmIn(BaseModel):
    """Confirm visual øktbygger → planned_sessions.steps_json (Human Coach)."""

    name: str = Field(min_length=1)
    date: str = Field(min_length=10, max_length=10)
    sport: str = "other"
    duration_minutes: int | None = None
    start_time: str = "07:00"
    steps: list[dict[str, Any]] = Field(default_factory=list)
    description: str = ""
    external_id: str | None = None
    prepare_intervals_sync: bool = False


class SessionCompletionIn(BaseModel):
    status: str = Field(
        min_length=1, description="completed|skipped|injured|tired|sick|other"
    )
    reason: str = ""
    note: str = ""
    session_name: str = ""
    session_date: str | None = None
    discipline: str = ""
    source: str = "intervals"
    append_profile_note: bool = True


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


class CalendarSyncPreviewIn(BaseModel):
    """Preview push or delete — never writes to Intervals until confirm."""

    op: str = Field(description="push | delete")
    block_ids: list[str] | None = None
    start: str | None = None
    end: str | None = None
    # Chat/near-window Sync: grov NOTES off by default (opt-in).
    include_notes: bool = False


class CalendarConfirmIn(BaseModel):
    pending_id: str = Field(min_length=1)


class TrainingPeaksBetaCredentialsIn(BaseModel):
    """Beta: Production_tpAuth cookie (tpapi) — unofficial mirror to TP calendar."""

    tp_auth_cookie: str = ""
    tp_sync_enabled: bool = False
    verify: bool = True


class TpCalendarPreviewIn(BaseModel):
    block_ids: list[str] | None = None
    start: str | None = None
    end: str | None = None
    include_notes: bool = False


class TpCalendarConfirmIn(BaseModel):
    pending_id: str = Field(min_length=1)


class WorkoutPreviewIn(BaseModel):
    """Preview chat workouts → planned_sessions (+ optional Intervals).

    Confirm persists app SoT; Intervals write only when secrets exist and
    ``prepare_intervals_sync`` is true. When weekly cap is full, pass
    ``replace_session_ids`` to swap existing planned rows (not a dead-end).
    """

    workouts: list[dict[str, Any]] = Field(min_length=1)
    prepare_intervals_sync: bool = True
    replace_session_ids: list[str] = Field(default_factory=list)


@app.get("/health")
def health() -> JSONResponse:
    """Liveness: always answers quickly (even when DB boot failed).

    Fly http_service.checks hit this path — must not block on Postgres.
    ``db_ok`` / ``db_error`` tell operators why /v1 is 503.
    """
    db_ok = _DB_BOOT_ERROR is None
    body: dict[str, Any] = {
        "status": "ok" if db_ok else "degraded",
        "db_ok": db_ok,
        "db_backend": config.db_backend_name(),
        "tier_model": "grov+detalj",
        "detail_weeks": DETAIL_WEEKS,
    }
    if _DB_BOOT_ERROR:
        body["db_error"] = _DB_BOOT_ERROR[:500]
    # 200 so Fly keeps the machine up and static UI can show the error;
    # operators still see status=degraded / db_ok=false.
    return JSONResponse(status_code=200, content=body)


@app.post("/v1/session/bootstrap")
def session_bootstrap(body: BootstrapIn) -> dict[str, Any]:
    """Return athlete if id exists; else needs_onboarding."""
    if not body.athlete_id:
        return {
            "needs_onboarding": True,
            "needs_setup": True,
            "athlete": None,
        }
    with db_session(config.get_db()) as conn:
        athlete = get_athlete(conn, body.athlete_id)
    if not athlete:
        return {
            "needs_onboarding": True,
            "needs_setup": True,
            "athlete": None,
        }
    needs_setup = athlete_needs_setup(athlete)
    return {
        "needs_onboarding": False,
        "needs_setup": needs_setup,
        "athlete": athlete,
    }


@app.post("/v1/session/login")
def session_login(body: LoginIn) -> dict[str, Any]:
    """Reconnect to an existing athlete. Never creates a new profile."""
    username = normalize_username(body.username)
    aid = (body.athlete_id or "").strip() or None
    if not username and not aid:
        raise HTTPException(422, "Oppgi brukernavn eller profil-ID.")
    token = (body.invite_token or "").strip() or None
    with db_session(config.get_db()) as conn:
        if username:
            athlete = get_athlete_by_username(conn, username)
            if not athlete:
                raise HTTPException(
                    404,
                    "Ukjent brukernavn. Sjekk stavemåte, eller opprett ny bruker.",
                )
        else:
            assert aid is not None
            athlete = get_athlete(conn, aid)
            if not athlete:
                raise HTTPException(
                    404,
                    "Ukjent profil-ID. Sjekk at ID er riktig, eller opprett ny bruker.",
                )
        if token is not None and not invite_token_valid(conn, token):
            raise HTTPException(401, "Ugyldig invite-token.")
    needs_setup = athlete_needs_setup(athlete)
    return {
        "athlete": athlete,
        "needs_onboarding": False,
        "needs_setup": needs_setup,
    }


@app.post("/v1/onboarding")
def onboarding(body: OnboardingIn) -> dict[str, Any]:
    data = body.model_dump()
    uname = normalize_username(data.get("username"))
    err = validate_username(uname)
    if err:
        raise HTTPException(422, err)
    data["username"] = uname
    # Legacy thin onboarding still marks setup done so reconnect enters the app
    # (new users use /v1/setup/* and get the AI landing instead).
    data["setup_completed"] = True
    try:
        with db_session(config.get_db()) as conn:
            if get_athlete_by_username(conn, uname):
                raise HTTPException(409, "Brukernavnet er opptatt. Velg et annet.")
            athlete = insert_athlete(conn, data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    path = write_profile(config.ATHLETES_DATA_DIR, athlete)
    return {
        "athlete": athlete,
        "profile_path": str(path.relative_to(config.REPO_ROOT))
        if path.is_relative_to(config.REPO_ROOT)
        else str(path),
    }


@app.post("/v1/setup/plan/preview")
def setup_plan_preview(body: SetupDraftIn) -> dict[str, Any]:
    """Build adaptive periodization + training outline. No SQLite / Intervals writes.

    Safe for restart (nullstill → Sett opp planen på nytt) and fresh onboarding:
    empty chat draft still yields plan_blocks. Workout-library preview degrades
    instead of 500 if Docker image mangler workouts/repo_scripts.
    """
    draft = body.model_dump()
    try:
        preview = build_setup_preview(
            draft,
            knowledge_dir=config.KNOWLEDGE_DIR,
            api_key=config.OPENAI_API_KEY or "",
            model=config.OPENAI_MODEL or "gpt-4o-mini",
            enrich=bool(body.enrich_with_llm),
        )
    except Exception as exc:
        raise HTTPException(
            500,
            f"Kunne ikke generere periodisering: {format_exc_nb(exc)}",
        ) from exc

    # NOTES + first 1–2 weeks WORKOUT (still no write). Never fail the whole
    # preview if økt-builder/workouts mangler — periodisering is the product.
    try:
        sync_prev = events_preview_for_plan_sync(
            preview["plan_blocks"],
            signals=preview.get("signals") or {},
            athlete={
                **(preview.get("athlete_patch") or {}),
                "athlete_type": preview.get("athlete_type"),
                "goal_text": draft.get("goal_text") or "",
                "sport": (preview.get("athlete_patch") or {}).get("sport")
                or draft.get("sport"),
                "allowed_disciplines": preview.get("allowed_disciplines")
                or (preview.get("athlete_patch") or {}).get("allowed_disciplines")
                or draft.get("allowed_disciplines")
                or [],
                "sessions_per_week": preview.get("sessions_per_week")
                or (preview.get("athlete_patch") or {}).get("sessions_per_week")
                or draft.get("sessions_per_week"),
            },
        )
    except Exception as exc:
        err_nb = format_exc_nb(exc)
        sync_prev = {
            "will_push": False,
            "kind": "calendar_notes_only_degraded",
            "error": err_nb,
            "warning": f"Økt-forhåndsvisning feilet: {err_nb}",
            "description": f"Periodisering OK. Økt-forhåndsvisning feilet: {err_nb}",
            "events_preview": [],
            "workouts_preview": [],
            "notes_preview": [],
            "events_count": 0,
            "notes_count": 0,
            "workouts_count": 0,
            "zwo_count": 0,
            "weeks": 2,
        }
    sync_prev["credentials_present"] = bool(
        (body.intervals_athlete_id or "").strip()
        and (body.intervals_api_key or "").strip()
    )
    if not sync_prev.get("error"):
        sync_prev["description"] = (
            "Forhåndsvisning: grovplan-noter + konkrete økter (WORKOUT) for "
            f"Intervals-nærvindu ({sync_prev.get('weeks', 2)} uker). "
            "Full app-plan til måldato lagres ved bekreft. "
            "Ingenting synces til Intervals før Sync-bekreftelse."
        )
    elif not sync_prev.get("warning"):
        sync_prev["warning"] = f"Økt-forhåndsvisning feilet: {sync_prev['error']}"
    preview["intervals_sync"] = sync_prev
    return preview


@app.post("/v1/setup/chat")
def setup_chat(body: SetupChatIn) -> dict[str, Any]:
    """Adaptive onboarding turn — knowledge-grounded, extracts fields, no persist."""
    draft = body.draft.model_dump()
    history = [
        {"role": m.get("role", ""), "content": m.get("content", "")}
        for m in (body.history or [])
        if m.get("role") in ("user", "assistant") and m.get("content")
    ][-12:]
    history_blob = " ".join(m["content"] for m in history)
    system, knowledge_meta = build_setup_chat_system(
        draft,
        knowledge_dir=config.KNOWLEDGE_DIR,
        history_blob=history_blob + " " + body.message,
    )
    raw = call_llm(
        api_key=config.OPENAI_API_KEY or "",
        model=config.OPENAI_MODEL or "gpt-4o-mini",
        system=system,
        history=history,
        user_message=body.message,
    )
    display, extracted = extract_setup_fields(raw)
    if not config.OPENAI_API_KEY:
        # Stub still teaches the flow when no key
        display = (
            display
            or (
                f"(Utviklingsmodus.) Fortell meg om mål, erfaring (nybegynner/comeback), "
                f"skader og hvor mange timer du har i uka. Jeg hørte: «{body.message[:180]}»."
            )
        )
        # Lightweight heuristic extract without LLM
        low = body.message.lower()
        if "nybegynner" in low or "aldri" in low:
            extracted.setdefault("background_notes", body.message[:400])
        if any(w in low for w in ("skade", "isjas", "rygg", "kne")):
            extracted.setdefault("injury_notes", body.message[:400])
        if any(
            w in low
            for w in ("mål", "lofoten", "triatlon", "triathlon", "halvmaraton", "2028", "2027")
        ):
            extracted.setdefault("goal_text", body.message[:400])
        if re.search(r"\d+\s*t|\d\s*økter", low):
            extracted.setdefault("schedule_notes", body.message[:400])
        if len(history) >= 2 and (
            draft.get("goal_text") or extracted.get("goal_text")
        ):
            extracted["ready_for_plan"] = True

    merged = merge_draft(draft, extracted)
    # Heuristic fill so Du-fanen later is not blank even if LLM left nulls
    merged = enrich_draft_from_text(merged, body.message)
    if not str(merged.get("goal_text") or "").strip():
        g = compose_goal_text(merged, text=body.message)
        if g:
            merged["goal_text"] = g
    ready = bool(extracted.get("ready_for_plan"))
    return {
        "reply": display,
        "extracted": extracted,
        "draft": merged,
        "ready_for_plan": ready,
        "knowledge": knowledge_meta,
    }


@app.post("/v1/setup/confirm")
def setup_confirm(
    body: SetupConfirmIn,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Persist athlete + plan_blocks + profile.md after explicit preview confirm.

    Never writes to Intervals here. If prepare_intervals_sync + credentials:
    creates a pending calendar push (same confirm gate as Plan-fanen).

    Isolation: only ``body.athlete_id`` selects an existing row (restart setup).
    ``X-Athlete-Id`` alone must NOT update another profile — leftover client
    localStorage previously caused new-user confirm to overwrite William/seed.
    """
    draft = body.model_dump()
    existing_id = (body.athlete_id or "").strip() or None
    header_id = (x_athlete_id or "").strip() or None
    if existing_id and header_id and header_id != existing_id:
        raise HTTPException(
            403,
            "X-Athlete-Id stemmer ikke med athlete_id — kan ikke bekrefte for en annen utøver.",
        )

    # Prefer client-reviewed blocks; else rebuild deterministically.
    blocks = list(body.plan_blocks or [])
    if not blocks:
        rebuilt = build_setup_preview(
            draft,
            knowledge_dir=config.KNOWLEDGE_DIR,
            api_key="",
            enrich=False,
        )
        blocks = rebuilt["plan_blocks"]
        patch = rebuilt["athlete_patch"]
    else:
        patch = dict(body.athlete_patch or {})
        if not patch:
            rebuilt = build_setup_preview(
                draft,
                knowledge_dir=config.KNOWLEDGE_DIR,
                api_key="",
                enrich=False,
            )
            patch = rebuilt["athlete_patch"]

    # Always merge conversation draft + patch so Du-fanen is not blank
    patch = merge_confirm_athlete_patch(patch, draft)
    # First-class grovplan enrichment (hours band + session-type mix)
    blocks = enrich_grov_blocks(
        blocks,
        athlete={
            **patch,
            "sessions_per_week": patch.get("sessions_per_week")
            or body.sessions_per_week,
            "allowed_disciplines": patch.get("allowed_disciplines")
            or body.allowed_disciplines,
        },
    )

    display_name = (body.display_name or "").strip()
    if not display_name and not existing_id:
        raise HTTPException(422, "Navn er påkrevd for ny bruker.")

    uname = normalize_username(body.username)
    intervals_pending: dict[str, Any] | None = None
    horizon_meta: dict[str, Any] = {}

    with db_session(config.get_db()) as conn:
        if existing_id:
            athlete = get_athlete(conn, existing_id)
            if not athlete:
                raise HTTPException(404, "Utøver ikke funnet")
            # Restart / continue setup: update fields, replace blocks
            update_fields = {
                k: v
                for k, v in {
                    "display_name": display_name or athlete.get("display_name"),
                    "coach_display_name": body.coach_display_name,
                    "coach_personality": body.coach_personality,
                    "coach_style_note": body.coach_style_note,
                    "accent_color": body.accent_color,
                    "sport": body.sport or patch.get("sport"),
                    **patch,
                }.items()
                if v is not None
            }
            athlete = update_athlete(conn, existing_id, update_fields) or athlete
            saved_blocks = replace_plan_blocks(conn, existing_id, blocks)
            aid = existing_id
        else:
            if not uname:
                raise HTTPException(422, "Brukernavn er påkrevd.")
            err = validate_username(uname)
            if err:
                raise HTTPException(422, err)
            if get_athlete_by_username(conn, uname):
                raise HTTPException(409, "Brukernavnet er opptatt. Velg et annet.")
            try:
                athlete = insert_athlete(
                    conn,
                    {
                        "display_name": display_name,
                        "username": uname,
                        "coach_display_name": body.coach_display_name,
                        "coach_personality": body.coach_personality,
                        "coach_style_note": body.coach_style_note,
                        "accent_color": body.accent_color,
                        "sport": patch.get("sport") or body.sport,
                        "goal_text": patch.get("goal_text") or body.goal_text or "",
                        "injury_notes": patch.get("injury_notes") or body.injury_notes or "",
                        "schedule_notes": patch.get("schedule_notes")
                        or body.schedule_notes
                        or "",
                        "notes": patch.get("notes") or "",
                        "weekly_focus": patch.get("weekly_focus") or "",
                        "ftp_tested": patch.get("ftp_tested"),
                        "ftp_tested_at": patch.get("ftp_tested_at"),
                        "weight_kg": patch.get("weight_kg"),
                        "age_years": patch.get("age_years"),
                        "nutrition_ibs": patch.get("nutrition_ibs") or "no",
                        "nutrition_gluten": patch.get("nutrition_gluten") or "none",
                        "nutrition_lactose": bool(patch.get("nutrition_lactose")),
                        "nutrition_other_restrictions": patch.get(
                            "nutrition_other_restrictions"
                        )
                        or "",
                        "nutrition_notes": patch.get("nutrition_notes") or "",
                        "agreements": patch.get("agreements") or [],
                    },
                )
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            aid = athlete["id"]
            season_patch = {
                k: patch[k]
                for k in (
                    "weekly_focus",
                    "season_start_date",
                    "goal_race_date",
                    "season_swim_hours_target",
                    "season_bike_hours_target",
                    "season_run_hours_target",
                    "season_strength_hours_target",
                    "notes",
                    "goal_text",
                    "injury_notes",
                    "schedule_notes",
                    "fitness_notes",
                    "athlete_type",
                    "sport",
                    "sessions_per_week",
                    "allowed_disciplines",
                    "agreements",
                )
                if k in patch and patch[k] is not None
            }
            if season_patch:
                athlete = update_athlete(conn, aid, season_patch) or athlete
            saved_blocks = replace_plan_blocks(conn, aid, blocks)

        # Ensure athlete_type + history on confirm (mutable; first write here)
        atype = normalize_athlete_type(
            patch.get("athlete_type") or body.athlete_type or athlete.get("athlete_type")
        )
        if not atype:
            inferred = infer_athlete_type(
                "",
                {
                    **draft,
                    **{k: patch.get(k) for k in ("goal_text", "notes", "sport")},
                },
            )
            atype = inferred["athlete_type"]
        old_type = athlete.get("athlete_type") or ""
        type_patch: dict[str, Any] = {
            "athlete_type": atype,
            "sport": patch.get("sport")
            or SPORT_FOR_TYPE.get(atype)
            or body.sport
            or athlete.get("sport")
            or "endurance",
            "setup_completed": True,
        }
        # Training agreements from preview / body — always persist when known
        if patch.get("allowed_disciplines") or body.allowed_disciplines:
            type_patch["allowed_disciplines"] = (
                patch.get("allowed_disciplines") or body.allowed_disciplines
            )
        if patch.get("sessions_per_week") is not None or body.sessions_per_week is not None:
            type_patch["sessions_per_week"] = (
                patch.get("sessions_per_week")
                if patch.get("sessions_per_week") is not None
                else body.sessions_per_week
            )
        for k in (
            "goal_text",
            "injury_notes",
            "notes",
            "weekly_focus",
            "fitness_notes",
            "schedule_notes",
            "goal_race_date",
            "season_start_date",
            "agreements",
        ):
            if patch.get(k) not in (None, ""):
                type_patch[k] = patch[k]
        if old_type != atype:
            type_patch["athlete_type_notes"] = append_type_history(
                athlete.get("athlete_type_notes"),
                old_type=old_type or None,
                new_type=atype,
                reason="setup confirm",
            )
        athlete = update_athlete(conn, aid, type_patch) or athlete

        # Full plan horizon → planned_sessions (app SoT until goal / race date)
        horizon_meta = _persist_plan_horizon_sessions(
            conn, aid, saved_blocks, athlete
        )

        # Optional Intervals credentials (store only — soft verify)
        icu_id = (body.intervals_athlete_id or "").strip()
        api_key_in = (body.intervals_api_key or "").strip()
        intervals_view: dict[str, Any] | None = None
        intervals_prep_error: str | None = None
        if icu_id and api_key_in:
            row = upsert_athlete_secrets(
                conn,
                aid,
                intervals_api_key=api_key_in,
                intervals_athlete_id=icu_id,
            )
            intervals_view = secrets_public_view(row)
            ok, err = smoke_test_intervals(api_key_in, icu_id)
            if intervals_view is not None:
                intervals_view["verified"] = ok
                intervals_view["verify_error"] = err

        if body.prepare_intervals_sync:
            secrets = get_athlete_secrets(conn, aid)
            key = ((secrets or {}).get("intervals_api_key") or "").strip()
            icu = ((secrets or {}).get("intervals_athlete_id") or "").strip()
            if key and icu and saved_blocks:
                try:
                    bundle = _sync_bundle_preferring_stored(
                        conn,
                        aid,
                        saved_blocks,
                        athlete,
                        allow_degraded=True,
                    )
                except Exception as exc:
                    intervals_prep_error = (
                        f"Plan lagret lokalt, men Intervals-forberedelse feilet: "
                        f"{format_exc_nb(exc)}"
                    )
                    bundle = None
                if bundle is not None:
                    if bundle.get("error") and not bundle.get("events"):
                        intervals_prep_error = (
                            f"Plan lagret lokalt. Økt-sync ikke klar: "
                            f"{bundle.get('error')}"
                        )
                    events = bundle.get("events") or []
                    if events:
                        payload = {
                            "op": "push",
                            "block_ids": [b["id"] for b in saved_blocks],
                            "events": events,
                            "intervals_athlete_id": icu,
                            "notes_count": bundle["notes_count"],
                            "workouts_count": bundle["workouts_count"],
                            "zwo_count": bundle["zwo_count"],
                            "weeks": bundle["weeks"],
                            "builder": bundle["builder"],
                            "knowledge_paths": bundle["knowledge_paths"],
                            "from_stored_sessions": bundle.get(
                                "from_stored_sessions", False
                            ),
                        }
                        pending = insert_pending_action(
                            conn, aid, "intervals_calendar_push", payload
                        )
                        intervals_pending = {
                            "pending_id": pending["id"],
                            "op": "push",
                            "count": bundle["count"],
                            "notes_count": bundle["notes_count"],
                            "workouts_count": bundle["workouts_count"],
                            "zwo_count": bundle["zwo_count"],
                            "weeks": bundle["weeks"],
                            "builder": bundle["builder"],
                            "knowledge_paths": bundle["knowledge_paths"],
                            "expires_at": pending.get("expires_at"),
                            "events": bundle["events_preview"][:40],
                            "workouts_preview": bundle["workouts_preview"][:40],
                            "events_truncated": max(0, bundle["count"] - 40),
                            "confirm_required": True,
                            "degraded": bool(bundle.get("error")),
                            "warning": bundle.get("error"),
                            "message": (
                                f"Bekreft for å synce {bundle['workouts_count']} økter "
                                f"(første {bundle['weeks']} uke(r), "
                                f"{bundle['zwo_count']} med ZWO)"
                                + (
                                    f" + {bundle['notes_count']} grovplan-noter"
                                    if int(bundle.get("notes_count") or 0) > 0
                                    else " (uten grovplan-noter)"
                                )
                                + " til Intervals. Avbryt = plan beholdes kun i appen."
                            ),
                        }

    path = write_profile(config.ATHLETES_DATA_DIR, athlete)
    n_sess = int((horizon_meta or {}).get("planned_sessions_count") or 0)
    hz_w = (horizon_meta or {}).get("plan_horizon_weeks")
    d_w = (horizon_meta or {}).get("detalj_weeks") or DETAIL_WEEKS
    msg = (
        f"Profil + grovplan (~{hz_w} uker til måldato) lagret. "
        f"Detaljplan: {n_sess} konkrete økter (~{d_w} uker). "
        "Ingen stille årsomskriving."
    )
    if intervals_pending:
        msg += (
            " Bekreft Intervals-sync for nærvinduet "
            f"({(intervals_pending or {}).get('weeks', 2)} uker WORKOUT + noter)."
        )
    elif intervals_prep_error:
        msg += f" {intervals_prep_error}"
    else:
        msg += " Intervals urørt."
    return {
        "athlete": athlete,
        "plan_blocks": saved_blocks,
        "planned_sessions_count": n_sess,
        "plan_horizon_weeks": hz_w,
        "detalj_weeks": d_w,
        "detalj_start": (horizon_meta or {}).get("detalj_start"),
        "detalj_end": (horizon_meta or {}).get("detalj_end"),
        "tier_model": "grov+detalj",
        "icu_sync_weeks": (horizon_meta or {}).get("icu_sync_weeks"),
        "horizon_note_nb": (horizon_meta or {}).get("horizon_note_nb"),
        "profile_path": str(path.relative_to(config.REPO_ROOT))
        if path.is_relative_to(config.REPO_ROOT)
        else str(path),
        "intervals": intervals_view,
        "intervals_pending": intervals_pending,
        "intervals_prep_error": intervals_prep_error,
        "written_to_intervals": False,
        "message": msg,
    }


@app.post("/v1/athlete/me/setup/reset")
def setup_reset(
    body: SetupResetIn,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Wipe plan + coaching setup fields. Requires double confirmation payload.

    Optional: delete only coach-pushed Intervals events (``ll-coach-*`` /
    ``ll-coach-w-*``) — never the whole calendar. Requires
    ``delete_intervals_coach_events`` + ``acknowledge_intervals_delete``.
    """
    aid = _require_athlete(x_athlete_id)
    phrase = (body.confirm_phrase or "").strip().upper()
    if not body.acknowledge_wipe or phrase != "SLETT":
        raise HTTPException(
            400,
            "Dobbeltbekreftelse kreves: acknowledge_wipe=true og confirm_phrase=SLETT.",
        )
    if body.delete_intervals_coach_events and not body.acknowledge_intervals_delete:
        raise HTTPException(
            400,
            "For å slette coach-økter på Intervals: sett også "
            "acknowledge_intervals_delete=true (dobbelt bekreftelse).",
        )

    intervals_deleted: dict[str, Any] | None = None
    if body.delete_intervals_coach_events and body.acknowledge_intervals_delete:
        with db_session(config.get_db()) as conn:
            athlete0 = get_athlete(conn, aid)
            if not athlete0:
                raise HTTPException(404, "Utøver ikke funnet")
            secrets = get_athlete_secrets(conn, aid)
            blocks = list_plan_blocks(conn, aid)
        key = ((secrets or {}).get("intervals_api_key") or "").strip()
        icu = ((secrets or {}).get("intervals_athlete_id") or "").strip()
        if key and icu:
            win_start, win_end = status_window_for_blocks(blocks)
            from datetime import timedelta

            oldest = (win_start - timedelta(days=400)).isoformat()
            newest = (win_end + timedelta(days=400)).isoformat()
            try:
                existing = filter_coach_events(
                    fetch_events(key, icu, oldest, newest)
                )
                external_ids = [
                    e["external_id"]
                    for e in existing
                    if e.get("external_id")
                ]
                if external_ids:
                    result = delete_events_bulk(key, icu, external_ids)
                    intervals_deleted = {
                        "deleted": result.get("eventsDeleted", len(external_ids)),
                        "external_ids": external_ids[:40],
                        "truncated": max(0, len(external_ids) - 40),
                    }
                else:
                    intervals_deleted = {"deleted": 0, "external_ids": []}
            except RuntimeError as exc:
                raise HTTPException(
                    502,
                    f"Kunne ikke slette coach-økter på Intervals: {exc}",
                ) from exc
        else:
            intervals_deleted = {
                "deleted": 0,
                "skipped": True,
                "reason": "Ingen Intervals-credentials",
            }

    with db_session(config.get_db()) as conn:
        athlete = get_athlete(conn, aid)
        if not athlete:
            raise HTTPException(404, "Utøver ikke funnet")
        n_blocks = delete_all_plan_blocks(conn, aid)
        n_sessions = delete_all_planned_sessions(conn, aid)
        n_msgs = clear_messages(conn, aid)
        cleared = update_athlete(
            conn,
            aid,
            {
                "goal_text": "",
                "injury_notes": "",
                "weekly_focus": "",
                "schedule_notes": "",
                "notes": "",
                "agreements": [],
                "athlete_type": "",
                "athlete_type_notes": "",
                "season_swim_hours_target": None,
                "season_bike_hours_target": None,
                "season_run_hours_target": None,
                "season_strength_hours_target": None,
                "season_start_date": None,
                "goal_race_date": None,
                "setup_completed": False,
            },
        )
    assert cleared is not None
    path = write_profile(config.ATHLETES_DATA_DIR, cleared)
    msg = "Setup nullstilt. Start veiledet oppsett på nytt."
    if intervals_deleted and not intervals_deleted.get("skipped"):
        msg += f" Slettet {intervals_deleted.get('deleted', 0)} coach-hendelse(r) på Intervals."
    return {
        "athlete": cleared,
        "deleted_plan_blocks": n_blocks,
        "deleted_planned_sessions": n_sessions,
        "cleared_messages": n_msgs,
        "intervals_deleted": intervals_deleted,
        "profile_path": str(path.relative_to(config.REPO_ROOT))
        if path.is_relative_to(config.REPO_ROOT)
        else str(path),
        "needs_setup": True,
        "message": msg,
    }


@app.get("/v1/athlete/me")
def get_me(x_athlete_id: str | None = Header(default=None)) -> dict[str, Any]:
    aid = _require_athlete(x_athlete_id)
    with db_session(config.get_db()) as conn:
        athlete = get_athlete(conn, aid)
        unread = count_unread_athlete_events(conn, aid) if athlete else 0
    if not athlete:
        raise HTTPException(404, "Utøver ikke funnet")
    return {
        "athlete": athlete,
        "ticker_unread": unread,
        "email_notify": {
            "opt_in": bool(athlete.get("notify_email")),
            "email_set": bool(athlete.get("email")),
            "resend_configured": resend_configured(),
        },
    }


@app.get("/v1/athlete/me/events")
def list_ticker_events(
    x_athlete_id: str | None = Header(default=None),
    unread_only: bool = Query(default=False),
    limit: int = Query(default=30, ge=1, le=100),
    refresh: bool = Query(
        default=True,
        description="Also evaluate soft triggers (roll/CTL/readiness) — never auto-apply",
    ),
) -> dict[str, Any]:
    """Unread ticker strip. Tap → confirm/plan — never auto-apply or auto-sync."""
    aid = _require_athlete(x_athlete_id)
    created: list[dict[str, Any]] = []
    with db_session(config.get_db()) as conn:
        athlete = get_athlete(conn, aid)
        if not athlete:
            raise HTTPException(404, "Utøver ikke funnet")
        if refresh:
            created = _refresh_ticker_soft(conn, aid, athlete)
        events = list_public_events(
            conn, aid, unread_only=unread_only, limit=limit
        )
        unread = count_unread_athlete_events(conn, aid)
    return {
        "events": events,
        "unread_count": unread,
        "created_soft": [e.get("id") for e in created if e],
        "human_coach": True,
        "auto_apply": False,
        "email_notify": {
            "opt_in": bool(athlete.get("notify_email")),
            "email_set": bool(athlete.get("email")),
            "resend_configured": resend_configured(),
        },
    }


@app.post("/v1/athlete/me/events/{event_id}/read")
def mark_ticker_event_read(
    event_id: str,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    aid = _require_athlete(x_athlete_id)
    with db_session(config.get_db()) as conn:
        if not get_athlete(conn, aid):
            raise HTTPException(404, "Utøver ikke funnet")
        row = ticker_mark_read(conn, aid, event_id)
        if not row:
            raise HTTPException(404, "Hendelse ikke funnet")
        unread = count_unread_athlete_events(conn, aid)
    return {"event": row, "unread_count": unread}


@app.post("/v1/athlete/me/events/read-all")
def mark_all_ticker_events_read(
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    aid = _require_athlete(x_athlete_id)
    with db_session(config.get_db()) as conn:
        if not get_athlete(conn, aid):
            raise HTTPException(404, "Utøver ikke funnet")
        n = mark_all_athlete_events_read(conn, aid)
    return {"ok": True, "marked": n, "unread_count": 0}


def _refresh_ticker_soft(
    conn: Any,
    aid: str,
    athlete: dict[str, Any],
) -> list[dict[str, Any]]:
    """Soft roll/CTL/readiness events — proposal only, never auto-apply."""
    blocks = list_plan_blocks(conn, aid)
    sessions = list_planned_sessions(conn, aid)
    window = get_active_plan_window(conn, aid)
    roll_eval = evaluate_roll_trigger(
        plan_window=window,
        planned_sessions=sessions,
        plan_blocks=blocks,
        athlete=athlete,
        message="",
        in_coach_chat=True,
    )
    load: dict[str, Any] | None = None
    readiness_signals: dict[str, Any] | None = None
    hard_day = False
    try:
        secrets = get_athlete_secrets(conn, aid)
        key = ((secrets or {}).get("intervals_api_key") or "").strip()
        icu = ((secrets or {}).get("intervals_athlete_id") or "").strip()
        if key and icu:
            from wellness import (
                fetch_wellness,
                load_summary_from_wellness,
                recovery_signals_from_wellness,
            )

            newest = date.today().isoformat()
            oldest = (date.today() - timedelta(days=14)).isoformat()
            rows = fetch_wellness(key, icu, oldest, newest) or []
            load = load_summary_from_wellness(rows)
            readiness_signals = recovery_signals_from_wellness(rows)
        today = date.today()
        for s in sessions:
            sd = str(s.get("session_date") or "")[:10]
            if not sd:
                continue
            try:
                d = date.fromisoformat(sd)
            except ValueError:
                continue
            if today <= d <= today + timedelta(days=2):
                st = (s.get("session_type") or s.get("type") or "").lower()
                name = (s.get("name") or "").lower()
                if any(
                    x in st or x in name
                    for x in ("quality", "threshold", "vo2", "interv", "tempo", "hard")
                ):
                    hard_day = True
                    break
    except Exception:  # noqa: BLE001
        pass
    return refresh_soft_ticker(
        conn,
        aid,
        roll_eval=roll_eval,
        load=load,
        readiness_signals=readiness_signals,
        hard_day_ahead=hard_day,
    )


@app.patch("/v1/athlete/me")
def patch_me(
    body: AthletePatch,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    aid = _require_athlete(x_athlete_id)
    patch = body.model_dump(exclude_unset=True)
    if "email" in patch:
        em = validate_email(patch.get("email"))
        if patch.get("email") and not em:
            raise HTTPException(400, "Ugyldig e-postadresse")
        patch["email"] = em or ""
    with db_session(config.get_db()) as conn:
        existing = get_athlete(conn, aid)
        if not existing:
            raise HTTPException(404, "Utøver ikke funnet")
        # Keep agreements lines in sync when sessions/disciplines change
        if (
            "sessions_per_week" in patch
            or "allowed_disciplines" in patch
            or "goal_race_date" in patch
            or "goal_text" in patch
        ):
            from athlete_constraints import resolve_constraints
            from setup_plan import build_agreements_list

            merged = {**existing, **patch}
            constraints = resolve_constraints(merged, athlete_type=merged.get("athlete_type"))
            patch["agreements"] = build_agreements_list(
                {
                    "agreements": patch.get("agreements")
                    if "agreements" in patch
                    else existing.get("agreements"),
                    "athlete_type": merged.get("athlete_type"),
                    "goal_race_date": merged.get("goal_race_date"),
                },
                constraints=constraints,
                goal_text=str(merged.get("goal_text") or ""),
                fitness_notes=str(merged.get("fitness_notes") or ""),
            )
        athlete = update_athlete(conn, aid, patch)
    if not athlete:
        raise HTTPException(404, "Utøver ikke funnet")
    path = write_profile(config.ATHLETES_DATA_DIR, athlete)
    return {
        "athlete": athlete,
        "profile_path": str(path.relative_to(config.REPO_ROOT))
        if path.is_relative_to(config.REPO_ROOT)
        else str(path),
        "email_notify": {
            "opt_in": bool(athlete.get("notify_email")),
            "email_set": bool(athlete.get("email")),
            "resend_configured": resend_configured(),
        },
    }


@app.get("/v1/athlete/me/intervals")
def get_intervals(x_athlete_id: str | None = Header(default=None)) -> dict[str, Any]:
    """Return connection status — never the full API key."""
    aid = _require_athlete(x_athlete_id)
    with db_session(config.get_db()) as conn:
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

    with db_session(config.get_db()) as conn:
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
    with db_session(config.get_db()) as conn:
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


def _require_tp_beta() -> None:
    if not config.TRAININGPEAKS_BETA_ENABLED:
        raise HTTPException(501, "TrainingPeaks beta er deaktivert på serveren")


def _calendar_sync_range(
    start: str | None, end: str | None
) -> tuple[Any, Any]:
    """Optional inclusive YYYY-MM-DD window from calendar UI."""
    from datetime import date as date_cls

    rs = parse_iso_date(start)
    re = parse_iso_date(end)
    if rs and re and re < rs:
        raise HTTPException(400, "Sluttdato må være etter startdato")
    return rs, re


def _apply_range_to_bundle(
    bundle: dict[str, Any], rs: Any, re: Any
) -> dict[str, Any]:
    if not rs or not re:
        return bundle
    events = filter_events_in_date_range(bundle.get("events") or [], rs, re)
    note_events = [e for e in events if (e.get("category") or "").upper() == "NOTE"]
    workout_events = [
        e for e in events if (e.get("category") or "").upper() == "WORKOUT"
    ]
    zwo_n = sum(1 for e in workout_events if e.get("file_contents"))
    out = dict(bundle)
    out["events"] = events
    out["note_events"] = note_events
    out["workout_events"] = workout_events
    out["notes_count"] = len(note_events)
    out["workouts_count"] = len(workout_events)
    out["zwo_count"] = zwo_n
    out["count"] = len(events)
    out["events_preview"] = [public_event_preview(e) for e in events[:80]]
    out["sync_range"] = {"start": rs.isoformat(), "end": re.isoformat()}
    return out


def _require_tp_secrets(aid: str) -> tuple[dict[str, Any], str, str]:
    with db_session(config.get_db()) as conn:
        athlete = get_athlete(conn, aid)
        secrets = get_athlete_secrets(conn, aid)
    if not athlete:
        raise HTTPException(404, "Utøver ikke funnet")
    cookie = ((secrets or {}).get("tp_auth_cookie") or "").strip()
    tp_uid = ((secrets or {}).get("tp_user_id") or "").strip()
    if not cookie:
        raise HTTPException(400, "Lagre TrainingPeaks-cookie (beta) under Du først")
    if not tp_uid:
        raise HTTPException(400, "Verifiser TrainingPeaks-tilkobling først")
    return athlete, cookie, tp_uid


@app.get("/v1/athlete/me/trainingpeaks/beta")
def get_trainingpeaks_beta(
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_tp_beta()
    aid = _require_athlete(x_athlete_id)
    with db_session(config.get_db()) as conn:
        secrets = get_athlete_secrets(conn, aid)
    return tp_public_status(secrets)


@app.put("/v1/athlete/me/trainingpeaks/beta")
def put_trainingpeaks_beta(
    body: TrainingPeaksBetaCredentialsIn,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_tp_beta()
    aid = _require_athlete(x_athlete_id)
    cookie_in = (body.tp_auth_cookie or "").strip()
    with db_session(config.get_db()) as conn:
        if not get_athlete(conn, aid):
            raise HTTPException(404, "Utøver ikke funnet")
        existing = get_athlete_secrets(conn, aid)
        cookie = cookie_in or ((existing or {}).get("tp_auth_cookie") or "").strip()
        if not cookie:
            raise HTTPException(400, "tp_auth_cookie kreves (eller lagret fra før)")
        tp_uid: str | None = (existing or {}).get("tp_user_id")
        verified: bool | None = None
        verify_error: str | None = None
        if body.verify:
            ok, err, uid = verify_tp_credentials(cookie)
            verified = ok
            verify_error = err
            if ok and uid:
                tp_uid = uid
        row = upsert_athlete_secrets(
            conn,
            aid,
            tp_auth_cookie=cookie,
            tp_user_id=tp_uid,
            tp_sync_enabled=body.tp_sync_enabled,
        )
    out = tp_public_status(row)
    out["verified"] = verified
    out["verify_error"] = verify_error
    return out


@app.post("/v1/athlete/me/trainingpeaks/beta/calendar/preview")
def trainingpeaks_calendar_preview(
    body: TpCalendarPreviewIn,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_tp_beta()
    aid = _require_athlete(x_athlete_id)
    athlete, _cookie, tp_uid = _require_tp_secrets(aid)
    with db_session(config.get_db()) as conn:
        blocks = list_plan_blocks(conn, aid)
        stored = list_planned_sessions(conn, aid)
    rs, re = _calendar_sync_range(body.start, body.end)
    selected = select_blocks(
        blocks, block_ids=body.block_ids, start=body.start, end=body.end
    )
    if not selected:
        raise HTTPException(400, "Ingen planblokker i utvalget")
    if stored and rs and re:
        stored = filter_planned_sessions_date_range(stored, rs, re)
    bundle = build_plan_sync_bundle(
        selected,
        athlete=athlete,
        include_notes=bool(body.include_notes),
        planned_sessions=stored if stored else None,
        sync_range_start=rs,
        sync_range_end=re,
    )
    bundle = _apply_range_to_bundle(bundle, rs, re)
    events = bundle["events"]
    if not events:
        raise HTTPException(400, "Ingen økter å speile i valgt periode")
    preview = preview_tp_push(events, athlete_id=tp_uid)
    payload = {
        "events": events,
        "tp_user_id": tp_uid,
        "block_ids": [b["id"] for b in selected],
        "workouts_count": preview["workouts_count"],
    }
    with db_session(config.get_db()) as conn:
        pending = insert_pending_action(conn, aid, "trainingpeaks_beta_push", payload)
    return {
        "pending_id": pending["id"],
        "confirm_required": True,
        "expires_at": pending.get("expires_at"),
        "beta": True,
        **preview,
    }


@app.post("/v1/athlete/me/trainingpeaks/beta/calendar/confirm")
def trainingpeaks_calendar_confirm(
    body: TpCalendarConfirmIn,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_tp_beta()
    aid = _require_athlete(x_athlete_id)
    _athlete, cookie, tp_uid = _require_tp_secrets(aid)
    with db_session(config.get_db()) as conn:
        pending = get_pending_action(conn, aid, body.pending_id)
    if not pending or pending.get("status") != "pending":
        raise HTTPException(404, "Pending handling ikke funnet")
    payload = pending.get("payload") or {}
    events = payload.get("events") or []
    result = push_tp_workouts(cookie, tp_uid, events)
    with db_session(config.get_db()) as conn:
        mark_pending_action(
            conn,
            aid,
            body.pending_id,
            "completed" if not result.get("errors") else "failed",
        )
    return {"beta": True, "tp_user_id": tp_uid, **result}


@app.post("/v1/chat")
def chat(
    body: ChatIn,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    aid = _require_athlete(x_athlete_id)
    with db_session(config.get_db()) as conn:
        athlete = get_athlete(conn, aid)
        if not athlete:
            raise HTTPException(404, "Utøver ikke funnet")
        history = recent_messages(conn, aid, limit=12)
        secrets = get_athlete_secrets(conn, aid)
        comps = completions_by_external_id(conn, aid)
        plan_blocks = list_plan_blocks(conn, aid)
        stored_planned = list_planned_sessions(conn, aid)
        # App planned_sessions + Intervals (completed = ICU activities only)
        sessions_bundle = _sessions_bundle_for_athlete(
            conn, aid, secrets=secrets, comps=comps, past_days=14, future_days=14
        )
    overview = _overview_payload(athlete, secrets)
    sessions_snap = sessions_snapshot_for_chat(sessions_bundle)
    overview["sessions"] = sessions_snap
    linked = secrets_public_view(secrets)
    intervals_ok = bool(linked.get("connected"))
    overview["app_plan"] = plan_summary_for_chat(
        athlete,
        planned_sessions=stored_planned,
        plan_blocks=plan_blocks,
        intervals_connected=intervals_ok,
        icu_sync_weeks=ICU_SYNC_WEEKS,
    )
    # One-shot: «bekreft og push til intervals» → save proposed session + same ICU event.
    # Must run before plan-sync intent (which also matches «push til intervals»).
    if user_requests_confirm_and_push(body.message):
        return _chat_confirm_and_push_workout(
            aid=aid,
            athlete=athlete,
            body_message=body.message,
            history=history,
            secrets=secrets,
            intervals_ok=intervals_ok,
            sessions_snap=sessions_snap,
            overview_app_plan=overview["app_plan"],
            sessions_bundle=sessions_bundle,
        )
    # Deterministic: push/sync plan → Intervals near window from stored SoT.
    # Also catch Kent follow-ups («sync» / «go») after coach already offered Sync.
    if user_requests_intervals_plan_sync(
        body.message
    ) or user_confirms_intervals_plan_sync(body.message, history):
        return _chat_intervals_plan_sync(
            aid=aid,
            athlete=athlete,
            body_message=body.message,
            plan_blocks=plan_blocks,
            stored_planned=stored_planned,
            intervals_ok=intervals_ok,
            secrets=secrets,
            sessions_snap=sessions_snap,
            overview_app_plan=overview["app_plan"],
        )
    # Explicit «neste måned / rull» → detalj roll card (bypass cooldown).
    if user_requests_explicit_roll(body.message):
        return _chat_plan_roll_offer(
            aid=aid,
            athlete=athlete,
            body_message=body.message,
            plan_blocks=plan_blocks,
            stored_planned=stored_planned,
            overview=overview,
            explicit=True,
        )
    # «ok» / «ja» after prose write offer → reopen card; never LLM «jeg har oppdatert».
    if user_confirms_pending_write(body.message, history):
        return _chat_reopen_pending_write(
            aid=aid,
            athlete=athlete,
            body_message=body.message,
            history=history,
            sessions_snap=sessions_snap,
            overview_app_plan=overview["app_plan"],
            sessions_bundle=sessions_bundle,
        )
    # Wellness as signals for coach context (soft-fail, never blocks chat)
    try:
        wl = resolve_wellness_bundle(
            secrets, days=7, include_body=False
        )
        overview["wellness_signals"] = wl.get("recovery_signals") or {
            "available": False,
            "as_signals_only": True,
            "sleep": wl.get("sleep"),
            "load": wl.get("load_wellness"),
            "note": "Wellness = signaler, ikke fasit.",
        }
        if overview["wellness_signals"] and not overview["wellness_signals"].get("sleep_avg_hours"):
            sleep = wl.get("sleep") or {}
            overview["wellness_signals"] = {
                **overview["wellness_signals"],
                "sleep_avg_hours": sleep.get("avg_hours"),
                "sleep_avg_score": sleep.get("avg_score"),
                "ctl": (wl.get("load_wellness") or {}).get("ctl"),
                "atl": (wl.get("load_wellness") or {}).get("atl"),
                "readiness": (wl.get("load_wellness") or {}).get("readiness"),
            }
    except Exception:  # noqa: BLE001
        overview["wellness_signals"] = {
            "available": False,
            "as_signals_only": True,
            "note": "Wellness utilgjengelig denne turen.",
        }
    recent = sessions_bundle.get("recent") or []
    today = sessions_bundle.get("today") or []
    if today:
        # Prefer completed activity on today for last_session; never a NOTE
        pick = next(
            (
                s
                for s in today
                if s.get("kind") == "activity" or s.get("training_status") == "completed"
            ),
            None,
        ) or next(
            (s for s in today if s.get("calendar_role") != "note"),
            today[0],
        )
        overview["last_session"] = {
            "name": pick.get("name"),
            "date": pick.get("date"),
            "kind": pick.get("kind"),
            "training_status": pick.get("training_status"),
        }
    elif recent:
        overview["last_session"] = {
            "name": recent[0].get("name"),
            "date": recent[0].get("date"),
            "kind": recent[0].get("kind"),
            "training_status": recent[0].get("training_status") or "completed",
        }
    focused = None
    if body.session_id:
        found = find_session_in_bundle(sessions_bundle, body.session_id)
        if found:
            focused = session_focus_for_chat(found)
            overview["focused_session"] = focused
    # Main Coach-tab chat + session-detail chat share this prompt (honest voice).
    system = build_system_prompt(
        athlete,
        config.KNOWLEDGE_DIR,
        overview_stub=overview,
        athletes_dir=config.ATHLETES_DATA_DIR,
        query_text=body.message or "",
        focused_session=focused,
        user_message=body.message,
    )
    knowledge_meta = knowledge_meta_for_chat(
        config.KNOWLEDGE_DIR,
        athlete=athlete,
        focused_session=focused,
        user_message=body.message,
    )
    raw_reply = call_llm(
        api_key=config.OPENAI_API_KEY,
        model=config.OPENAI_MODEL,
        system=system,
        history=[{"role": m["role"], "content": m["content"]} for m in history],
        user_message=body.message,
    )
    reply_wp, proposal = extract_workout_proposal(raw_reply)
    reply_rm, removal = extract_workout_removal(raw_reply)
    reply_ty, type_prop = extract_type_update_proposal(raw_reply)
    reply_ag, agr_prop = extract_agreements_update(raw_reply)
    reply_pl, plan_prop = extract_plan_update(raw_reply)
    # LLM often forgets fences — recover when athlete clearly asked for action
    if not proposal:
        proposal = infer_workout_proposal_fallback(
            body.message, raw_reply, today=date.today()
        )
        if proposal:
            reply_wp = (reply_wp or raw_reply or "").strip()
    if not plan_prop:
        plan_prop = infer_plan_update_fallback(body.message)
        if plan_prop:
            reply_pl = (reply_pl or raw_reply or "").strip()
    displays = [d for d in (reply_wp, reply_rm, reply_ty, reply_ag, reply_pl) if d]
    reply = min(displays, key=len) if displays else raw_reply.strip()
    # Prefer card over JSON-in-chat — always strip workouts fences from prose.
    reply = strip_workout_json_from_prose(reply) or reply
    # Keep clean structure in history so «bekreft og push» recovers the same session.
    if proposal:
        summary = workout_proposal_history_summary(proposal)
        if summary and summary.split("\n", 1)[0] not in reply:
            reply = f"{reply}\n\n{summary}".strip()

    with db_session(config.get_db()) as conn:
        add_message(conn, aid, "user", body.message)
        asst = add_message(conn, aid, "assistant", reply)
    out: dict[str, Any] = {
        "reply": reply,
        "message": asst,
        "sessions_in_context": True,
        "sessions_source": sessions_snap.get("source"),
        "knowledge": knowledge_meta,
        "app_plan": overview.get("app_plan"),
    }
    if focused:
        out["focused_session_id"] = focused.get("id")
        out["focused_session"] = {
            "id": focused.get("id"),
            "name": focused.get("name"),
            "date": focused.get("date"),
            "discipline": focused.get("discipline"),
        }
    if proposal:
        with db_session(config.get_db()) as conn:
            planned_this_week = _count_planned_this_week_db(conn, aid)
        gate = validate_workouts_against_constraints(
            athlete,
            proposal.get("workouts") or [],
            existing_planned_this_week=planned_this_week,
        )
        if gate["ok"]:
            out["workout_proposal"] = proposal
            out["confirm_required"] = True
            out["proposal_hint"] = (
                "Treneren foreslo økt(er). "
                "Trykk Forhåndsvis → bekreft for å lagre i planen "
                "(deretter Sync til Intervals om koblet)."
            )
            if proposal.get("inferred"):
                out["proposal_inferred"] = True
        elif gate["accepted"]:
            # Partial accept — only allowed sports/slots
            out["workout_proposal"] = {"workouts": gate["accepted"]}
            out["workout_proposal_rejected"] = gate["rejected"]
            out["constraint_reasons"] = gate["reasons"]
            out["confirm_required"] = True
            out["proposal_hint"] = (
                "Noen foreslåtte økter ble filtrert mot avtalen. "
                + " ".join(gate["reasons"][:2])
            )
        elif gate.get("cap_hit"):
            _attach_cap_replace_offer(
                out, aid=aid, proposal=proposal, gate=gate, reply=reply
            )
        else:
            out["workout_proposal_blocked"] = True
            out["workout_proposal_rejected"] = gate["rejected"]
            out["constraint_reasons"] = gate["reasons"]
            out["constraint_ask"] = gate.get("ask")
            out["proposal_hint"] = (
                gate.get("ask")
                or "Forslaget bryter avtalte disipliner/økter-per-uke og ble ikke lagret."
            )
            # Surface reasons in reply so athlete sees the refuse
            if gate["reasons"] and reply:
                extra = "\n\n⚠️ Avtale-sperre: " + " ".join(gate["reasons"][:3])
                if extra.strip() not in reply:
                    out["reply"] = reply + extra
    if removal:
        out["workout_removal"] = removal
        out["confirm_required"] = True
        out["removal_hint"] = (
            "Treneren foreslo å fjerne coach-økter på Intervals. "
            "Forhåndsvis → bekreft. Kun ll-coach-* slettes."
        )
    if type_prop:
        # Enrich with from→to for UI
        prop = propose_type_update(
            athlete,
            suggested=type_prop.get("athlete_type"),
            text=body.message,
        ) or {
            **type_prop,
            "from": athlete.get("athlete_type") or "general_endurance",
            "to": type_prop["athlete_type"],
            "from_label": label_for(athlete.get("athlete_type")),
            "to_label": label_for(type_prop["athlete_type"]),
            "message": type_prop.get("reason")
            or f"Oppdater hovedprofil til {label_for(type_prop['athlete_type'])}?",
        }
        if type_prop.get("reason") and isinstance(prop, dict):
            prop["reason"] = type_prop["reason"]
        out["athlete_type_proposal"] = prop
        out["confirm_required"] = True
    if agr_prop:
        out["agreements_proposal"] = agr_prop
        out["confirm_required"] = True
        out["agreements_hint"] = (
            "Treneren foreslo oppdaterte treningsavtaler. "
            "Bekreft for å lagre til Du-fanen — deretter foreslås ny grovplan "
            "(preview → confirm). Ingen stille endring."
        )
    if plan_prop and plan_prop.get("rebuild"):
        # Build plan adjust preview immediately so UI can show Forslag → Preview
        try:
            readiness = readiness_adjustment_hints(
                overview.get("wellness_signals")
            )
            if (plan_prop.get("scope") or "full") == "week":
                with db_session(config.get_db()) as conn:
                    blocks = list_plan_blocks(conn, aid)
                    existing_n = count_planned_sessions(conn, aid)
                if not blocks:
                    raise ValueError("Ingen planblokker — kjør full plan først")
                week_built = build_week_adjust_sessions(
                    blocks,
                    athlete=athlete,
                    week_start=plan_prop.get("week_start") or "this_week",
                    ease_load=bool(plan_prop.get("ease_load")),
                )
                out["plan_proposal"] = {
                    **plan_prop,
                    "scope": "week",
                    "week_start": week_built["week_start"],
                    "week_end": week_built["week_end"],
                    "sessions": week_built["sessions"],
                    "count": week_built["count"],
                    "planned_sessions_count": existing_n,
                    "unchanged_note_nb": (
                        f"Resten av horisonten (~{max(0, existing_n - week_built['count'])} "
                        "økter utenfor uka) beholdes."
                    ),
                    "horizon_note_nb": week_built["horizon_note_nb"],
                    "readiness_hints": readiness,
                    "icu_sync_weeks": week_built.get("icu_sync_weeks"),
                    "confirm_hint": (
                        f"Bekreft for å erstatte kun uka {week_built['week_start']}–"
                        f"{week_built['week_end']} ({week_built['count']} økter). "
                        "Ingen full horisont-wipe. Intervals først etter Sync."
                    ),
                }
            else:
                draft = _athlete_draft_for_plan(athlete)
                if plan_prop.get("ease_load"):
                    note = (draft.get("fitness_notes") or "").strip()
                    ease_bit = "Lett uke foreslått (readiness/søvn)."
                    draft["fitness_notes"] = f"{note} {ease_bit}".strip()[:500]
                plan_preview = build_setup_preview(
                    draft,
                    knowledge_dir=config.KNOWLEDGE_DIR,
                    api_key="",
                    enrich=False,
                )
                sync_athlete = {
                    **athlete,
                    **(plan_preview.get("athlete_patch") or {}),
                    "id": aid,
                }
                for key in (
                    "sessions_per_week",
                    "allowed_disciplines",
                    "goal_race_date",
                    "season_start_date",
                    "goal_text",
                ):
                    val = athlete.get(key)
                    if val not in (None, "", []):
                        sync_athlete[key] = val
                sync_prev = events_preview_for_plan_sync(
                    plan_preview["plan_blocks"],
                    signals=plan_preview.get("signals") or {},
                    athlete=sync_athlete,
                )
                hz = persistable_plan_payload(
                    plan_preview["plan_blocks"], athlete=sync_athlete
                )
                out["plan_proposal"] = {
                    **plan_prop,
                    "scope": "full",
                    "plan_blocks": plan_preview["plan_blocks"],
                    "athlete_patch": plan_preview.get("athlete_patch") or {},
                    "intervals_sync": sync_prev,
                    "planned_sessions_count": hz.get("count"),
                    "plan_horizon_weeks": hz.get("weeks"),
                    "icu_sync_weeks": hz.get("icu_sync_weeks"),
                    "horizon_note_nb": hz.get("horizon_note_nb"),
                    "readiness_hints": readiness,
                    "constraints_summary_nb": sync_prev.get("constraints_summary_nb")
                    or plan_preview.get("constraints_summary_nb"),
                    "workout_horizon_note_nb": (
                        f"App-plan: {hz.get('count')} økter / {hz.get('weeks')} uker til måldato. "
                        f"Intervals WORKOUT-sync: første {hz.get('icu_sync_weeks')} uker."
                    ),
                    "confirm_hint": (
                        "Forhåndsvisning klar. Bekreft for å lagre meso-blokker + "
                        "økter til måldato lokalt. Intervals først etter Sync."
                    ),
                }
            out["confirm_required"] = True
            out["plan_hint"] = (
                plan_prop.get("message")
                or "Treneren foreslo planjustering — bekreft forhåndsvisning."
            )
        except Exception as exc:  # noqa: BLE001
            out["plan_proposal"] = {
                **plan_prop,
                "error": format_exc_nb(exc),
                "confirm_required": True,
            }
            out["confirm_required"] = True
            out["plan_hint"] = (
                "Kunne ikke bygge planforhåndsvisning automatisk — "
                "bruk Du → «Snakk med treneren om endringene»."
            )
    # Fail closed: strip hallucinated write/sync success when no confirm card.
    has_card = bool(
        (out.get("workout_proposal") or {}).get("workouts")
        or out.get("plan_proposal")
        or out.get("plan_roll")
        or out.get("workout_replace_proposal")
        or out.get("workout_removal")
        or out.get("agreements_proposal")
        or out.get("athlete_type_proposal")
        or out.get("intervals_pending")
    )
    write_kind = write_intent_kind(body.message)
    if write_kind in ("session", "plan") and not has_card:
        # Intent was a write but LLM returned prose only — last-chance fallback
        if write_kind == "session" and not proposal:
            proposal = infer_workout_proposal_fallback(
                body.message, raw_reply, today=date.today()
            )
            if proposal:
                with db_session(config.get_db()) as conn:
                    planned_n = _count_planned_this_week_db(conn, aid)
                gate = validate_workouts_against_constraints(
                    athlete,
                    proposal.get("workouts") or [],
                    existing_planned_this_week=planned_n,
                )
                if gate["ok"] or gate.get("accepted"):
                    accepted = (
                        proposal.get("workouts")
                        if gate["ok"]
                        else gate["accepted"]
                    )
                    out["workout_proposal"] = {"workouts": accepted, "inferred": True}
                    out["confirm_required"] = True
                    out["proposal_inferred"] = True
                    out["proposal_hint"] = (
                        "Treneren foreslo økt(er). "
                        "Trykk Forhåndsvis → bekreft for å lagre i planen."
                    )
                    has_card = True
                elif gate.get("cap_hit"):
                    _attach_cap_replace_offer(
                        out,
                        aid=aid,
                        proposal=proposal,
                        gate=gate,
                        reply=out.get("reply"),
                    )
                    has_card = bool(
                        (out.get("workout_proposal") or {}).get("workouts")
                        or out.get("workout_replace_proposal")
                    )
        if write_kind == "plan" and not out.get("plan_proposal"):
            plan_prop = infer_plan_update_fallback(body.message)
            if plan_prop:
                # Re-enter plan build path lightly — week scope only for safety
                try:
                    if (plan_prop.get("scope") or "full") == "week":
                        with db_session(config.get_db()) as conn:
                            blocks = list_plan_blocks(conn, aid)
                            existing_n = count_planned_sessions(conn, aid)
                        if blocks:
                            week_built = build_week_adjust_sessions(
                                blocks,
                                athlete=athlete,
                                week_start=plan_prop.get("week_start") or "this_week",
                                ease_load=bool(plan_prop.get("ease_load")),
                            )
                            out["plan_proposal"] = {
                                **plan_prop,
                                "scope": "week",
                                "week_start": week_built["week_start"],
                                "week_end": week_built["week_end"],
                                "sessions": week_built["sessions"],
                                "count": week_built["count"],
                                "planned_sessions_count": existing_n,
                                "confirm_hint": (
                                    f"Bekreft for å erstatte kun uka "
                                    f"{week_built['week_start']}–{week_built['week_end']}."
                                ),
                            }
                            out["confirm_required"] = True
                            out["plan_hint"] = plan_prop.get("message")
                            has_card = True
                except Exception:  # noqa: BLE001
                    pass
        if not has_card:
            out["reply"] = sanitize_unconfirmed_write_claims(
                out.get("reply") or "", has_confirm_card=False
            )
            if write_kind == "session":
                out["reply"] = (
                    (out.get("reply") or "").rstrip()
                    + "\n\n"
                    + "Jeg trenger en bekreftbar økt (dato + varighet). "
                    "Si f.eks. «legg inn rolig løp i morgen 40 min» — "
                    "da får du forhåndsvisningskort. Ingenting er lagret ennå."
                )
            out["write_blocked_no_card"] = True
    else:
        out["reply"] = sanitize_unconfirmed_write_claims(
            out.get("reply") or "", has_confirm_card=has_card
        )
    # Soft roll-forward offer (≤14d left / block elapsed) — never silent apply.
    has_card = bool(
        (out.get("workout_proposal") or {}).get("workouts")
        or out.get("plan_proposal")
        or out.get("plan_roll")
        or out.get("workout_removal")
        or out.get("agreements_proposal")
        or out.get("athlete_type_proposal")
        or out.get("intervals_pending")
    )
    if not has_card and plan_blocks:
        roll_out = _maybe_attach_plan_roll(
            aid=aid,
            athlete=athlete,
            body_message=body.message,
            plan_blocks=plan_blocks,
            stored_planned=stored_planned,
            overview=overview,
            out=out,
            explicit=False,
        )
        if roll_out is not None:
            return roll_out
    return out


def _chat_plan_roll_offer(
    *,
    aid: str,
    athlete: dict[str, Any],
    body_message: str,
    plan_blocks: list[dict[str, Any]],
    stored_planned: list[dict[str, Any]],
    overview: dict[str, Any],
    explicit: bool = False,
) -> dict[str, Any]:
    """Human Coach detalj roll card — proposal only, never auto-save/sync."""
    with db_session(config.get_db()) as conn:
        window = get_active_plan_window(conn, aid)
        # Refresh athlete for cooldown timestamps
        athlete = get_athlete(conn, aid) or athlete
    ev = evaluate_roll_trigger(
        plan_window=window,
        planned_sessions=stored_planned,
        plan_blocks=plan_blocks,
        athlete=athlete,
        message=body_message if explicit else "",
        in_coach_chat=True,
    )
    if explicit:
        # Force offer even if soft eval said cooldown (explicit bypasses)
        ev = {**ev, "should_offer": True, "bypass_cooldown": True, "in_cooldown": False,
              "trigger": ev.get("trigger") or "explicit"}
    readiness = readiness_from_overview(overview)
    card = build_roll_proposal_card(
        plan_blocks,
        athlete=athlete,
        next_start=ev.get("next_start"),
        readiness=readiness,
        roll_eval=ev,
    )
    reply = (
        f"Neste detaljplan (~{DETAIL_WEEKS} uker) er klar til forhåndsvisning. "
        f"{ev.get('reason') or ''} "
        "Bekreft for å lagre i appen — Intervals synces først når du kjører Sync. "
        "Ingen stille rull."
    ).strip()
    with db_session(config.get_db()) as conn:
        add_message(conn, aid, "user", body_message)
        asst = add_message(conn, aid, "assistant", reply)
        mark_detalj_roll_offered(conn, aid)
    return {
        "reply": reply,
        "message": asst,
        "sessions_in_context": True,
        "app_plan": overview.get("app_plan"),
        "plan_roll": card,
        "plan_proposal": card,  # UI that already handles plan_proposal
        "confirm_required": True,
        "plan_hint": card.get("confirm_hint"),
        "roll_eval": {
            "trigger": ev.get("trigger"),
            "reason": ev.get("reason"),
            "bypass_cooldown": True if explicit else ev.get("bypass_cooldown"),
            "constants": ev.get("constants"),
        },
    }


def _maybe_attach_plan_roll(
    *,
    aid: str,
    athlete: dict[str, Any],
    body_message: str,
    plan_blocks: list[dict[str, Any]],
    stored_planned: list[dict[str, Any]],
    overview: dict[str, Any],
    out: dict[str, Any],
    explicit: bool = False,
) -> dict[str, Any] | None:
    with db_session(config.get_db()) as conn:
        window = get_active_plan_window(conn, aid)
        athlete = get_athlete(conn, aid) or athlete
    ev = evaluate_roll_trigger(
        plan_window=window,
        planned_sessions=stored_planned,
        plan_blocks=plan_blocks,
        athlete=athlete,
        message=body_message if explicit else "",
        in_coach_chat=True,
    )
    if not ev.get("should_offer"):
        if ev.get("in_cooldown"):
            out["roll_eval"] = {
                "should_offer": False,
                "in_cooldown": True,
                "trigger": ev.get("trigger"),
                "reason": "Cooldownoldown — ingen ny roll-offer ennå.",
                "constants": ev.get("constants"),
            }
        return None
    readiness = readiness_from_overview(overview)
    card = build_roll_proposal_card(
        plan_blocks,
        athlete=athlete,
        next_start=ev.get("next_start"),
        readiness=readiness,
        roll_eval=ev,
    )
    soft = (
        f"\n\n📅 Detaljplanen nærmer seg slutten — her er forslag til neste "
        f"~{DETAIL_WEEKS} uker (forhåndsvis → bekreft). Ingen stille lagring."
    )
    out["reply"] = ((out.get("reply") or "").rstrip() + soft).strip()
    out["plan_roll"] = card
    out["plan_proposal"] = card
    out["confirm_required"] = True
    out["plan_hint"] = card.get("confirm_hint")
    out["roll_eval"] = {
        "trigger": ev.get("trigger"),
        "reason": ev.get("reason"),
        "bypass_cooldown": ev.get("bypass_cooldown"),
        "constants": ev.get("constants"),
    }
    with db_session(config.get_db()) as conn:
        # Persist updated assistant text + offer timestamp
        add_message(conn, aid, "assistant", soft.strip())
        mark_detalj_roll_offered(conn, aid)
    return out


def _chat_confirm_and_push_workout(
    *,
    aid: str,
    athlete: dict[str, Any],
    body_message: str,
    history: list[dict[str, Any]],
    secrets: dict[str, Any] | None,
    intervals_ok: bool,
    sessions_snap: dict[str, Any],
    overview_app_plan: dict[str, Any],
    sessions_bundle: dict[str, Any],
) -> dict[str, Any]:
    """One-shot: persist proposed workout then ICU-push the *same* session.

    Uses ``build_workout_events`` → CLI ``build_workout_event`` (not a 10min stub).
    """
    last = ""
    for msg in reversed(list(history or [])[-8:]):
        if (msg.get("role") or "") == "assistant" and (msg.get("content") or "").strip():
            last = str(msg.get("content") or "")
            break
    _disp, proposal = extract_workout_proposal(last)
    if not proposal or not proposal.get("workouts"):
        # Clean seed — never embed reply text that mentions Sync/push (blocks session gate).
        seed = "legg inn økt i morgen"
        m_iso = None
        from chat_service import _ISO_DATE_RE as _iso

        m_iso = _iso.search(last)
        if m_iso:
            seed = f"legg inn økt {m_iso.group(1)}"
        proposal = infer_workout_proposal_fallback(
            seed, last, today=date.today()
        )
    workouts = (proposal or {}).get("workouts") or []
    if not workouts:
        reply = (
            "Fant ingen bekreftbar økt i forrige forslag. "
            "Be om økta på nytt, så får du kortet — deretter «bekreft og push til intervals»."
        )
        with db_session(config.get_db()) as conn:
            add_message(conn, aid, "user", body_message)
            asst = add_message(conn, aid, "assistant", reply)
        return {
            "reply": reply,
            "message": asst,
            "pending_write_reopen": True,
            "confirm_push_failed": True,
            "app_plan": overview_app_plan,
            "sessions_in_context": True,
            "sessions_source": sessions_snap.get("source"),
        }

    with db_session(config.get_db()) as conn:
        planned_n = _count_planned_this_week_db(conn, aid)
    gate = validate_workouts_against_constraints(
        athlete,
        workouts,
        existing_planned_this_week=planned_n,
    )
    if not gate["accepted"]:
        if gate.get("cap_hit"):
            out: dict[str, Any] = {
                "reply": (
                    "Uka er full mot avtalen — velg økt å erstatte i kortet, "
                    "deretter bekreft. Ingenting er pushet ennå."
                ),
                "pending_write_reopen": True,
                "app_plan": overview_app_plan,
                "sessions_in_context": True,
                "sessions_source": sessions_snap.get("source"),
            }
            _attach_cap_replace_offer(
                out, aid=aid, proposal={"workouts": workouts}, gate=gate, reply=out["reply"]
            )
            with db_session(config.get_db()) as conn:
                add_message(conn, aid, "user", body_message)
                asst = add_message(conn, aid, "assistant", out["reply"])
            out["message"] = asst
            return out
        reply = (
            gate.get("ask")
            or " ".join((gate.get("reasons") or [])[:2])
            or "Avtale blokkerer lagring."
        )
        with db_session(config.get_db()) as conn:
            add_message(conn, aid, "user", body_message)
            asst = add_message(conn, aid, "assistant", reply)
        return {
            "reply": reply,
            "message": asst,
            "workout_proposal_blocked": True,
            "constraint_reasons": gate.get("reasons"),
            "app_plan": overview_app_plan,
        }

    workouts_ok = gate["accepted"]
    try:
        events = build_workout_events(workouts_ok, athlete=athlete)
    except Exception as exc:  # noqa: BLE001
        from plan_workouts import format_exc_nb as _fmt

        reply = (
            f"Kunne ikke bygge Intervals-struktur for økta: {_fmt(exc)}. "
            "Prøv Forhåndsvis på kortet, eller si ifra."
        )
        with db_session(config.get_db()) as conn:
            add_message(conn, aid, "user", body_message)
            asst = add_message(conn, aid, "assistant", reply)
        return {
            "reply": reply,
            "message": asst,
            "confirm_push_failed": True,
            "workout_proposal": {"workouts": workouts_ok},
            "confirm_required": True,
            "app_plan": overview_app_plan,
        }

    key = ((secrets or {}).get("intervals_api_key") or "").strip()
    icu = ((secrets or {}).get("intervals_athlete_id") or "").strip()
    want_icu = bool(intervals_ok and key and icu)

    planned_rows: list[dict[str, Any]] = []
    for i, w in enumerate(workouts_ok):
        day = str(w.get("date") or "")[:10]
        name = str(w.get("name") or "").strip()
        if not day or not name:
            continue
        external = events[i].get("external_id") if i < len(events) else None
        # Prefer structured description from the built ICU event (clean, no JSON)
        icu_desc = ""
        if i < len(events):
            icu_desc = str(events[i].get("description") or "").strip()
        from plan_workouts import chat_workout_icu_description

        row_desc = icu_desc or chat_workout_icu_description(w)
        row: dict[str, Any] = {
            "session_date": day,
            "sport": str(w.get("sport") or "other").strip().lower() or "other",
            "name": name[:200],
            "description": row_desc[:4000],
            "duration_minutes": w.get("duration_minutes"),
            "start_time": str(w.get("start_time") or "07:00")[:5] or "07:00",
            "external_id": external,
            "source": "chat",
            "status": "planned",
            "planned_path": str(w.get("planned_path") or ""),
        }
        if w.get("steps"):
            row["steps"] = w["steps"]
        planned_rows.append(row)

    if not planned_rows:
        reply = "Ingen gyldige økter å lagre (trenger navn + dato)."
        with db_session(config.get_db()) as conn:
            add_message(conn, aid, "user", body_message)
            asst = add_message(conn, aid, "assistant", reply)
        return {"reply": reply, "message": asst, "confirm_push_failed": True}

    payload: dict[str, Any] = {
        "op": "workout_push",
        "persist_planned_sessions": True,
        "planned_sessions": planned_rows,
        "workouts": workouts_ok,
        "events": events if want_icu else [],
        "intervals_athlete_id": icu if want_icu else None,
        "prepare_intervals_sync": want_icu,
        "one_shot_confirm_push": True,
        "builder": "scripts/intervals_push_calendar.build_workout_event",
    }
    with db_session(config.get_db()) as conn:
        pending = insert_pending_action(conn, aid, "intervals_workout_push", payload)

    # Execute immediately (user already said bekreft+push) via same confirm path.
    try:
        confirm_out = calendar_confirm(
            CalendarConfirmIn(pending_id=pending["id"]),
            x_athlete_id=aid,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        reply = (
            f"Forhåndsvisning klar, men bekreftelse feilet: {detail[:280]}. "
            "Kortet under lar deg prøve Ja på nytt — samme økt, ikke et 10min-bibliotekstub."
        )
        with db_session(config.get_db()) as conn:
            add_message(conn, aid, "user", body_message)
            asst = add_message(conn, aid, "assistant", reply)
        return {
            "reply": reply,
            "message": asst,
            "intervals_pending": {
                "pending_id": pending["id"],
                "op": "workout_push",
                "count": len(planned_rows),
                "planned_sessions_count": len(planned_rows),
                "intervals_event_count": len(events) if want_icu else 0,
                "events": [public_event_preview(e) for e in (events if want_icu else [])][
                    :40
                ],
                "sessions": [
                    {
                        "session_date": r["session_date"],
                        "name": r["name"],
                        "sport": r["sport"],
                        "duration_minutes": r.get("duration_minutes"),
                    }
                    for r in planned_rows
                ],
                "confirm_required": True,
                "message": "Bekreft lagring av samme økt (CLI-struktur).",
            },
            "confirm_required": True,
            "app_plan": overview_app_plan,
        }

    saved = int(confirm_out.get("planned_sessions_saved") or len(planned_rows))
    pushed = int(confirm_out.get("pushed") or 0)
    names = [str(r.get("name") or "") for r in planned_rows]
    reply = confirm_write_success_reply_nb(saved=saved, pushed=pushed, names=names)
    if not want_icu:
        reply += " Intervals er ikke koblet — kun app-plan lagret."
    with db_session(config.get_db()) as conn:
        add_message(conn, aid, "user", body_message)
        asst = add_message(conn, aid, "assistant", reply)
    return {
        "reply": reply,
        "message": asst,
        "confirm_push_done": True,
        "planned_sessions_saved": saved,
        "pushed": pushed,
        "op": "workout_push",
        "app_plan": overview_app_plan,
        "sessions_in_context": True,
        "sessions_source": sessions_snap.get("source"),
        "workout_proposal": None,
        "write_success": True,
        **{
            k: confirm_out[k]
            for k in (
                "sessions_refetched",
                "planned_count",
                "completed_count",
            )
            if k in confirm_out
        },
    }


def _chat_reopen_pending_write(
    *,
    aid: str,
    athlete: dict[str, Any],
    body_message: str,
    history: list[dict[str, Any]],
    sessions_snap: dict[str, Any],
    overview_app_plan: dict[str, Any],
    sessions_bundle: dict[str, Any],
) -> dict[str, Any]:
    """Short «ok»/«ja» after write offer → re-show card; never claim success."""
    reply, proposal, plan_prop = reopen_pending_write_reply(
        history, today=date.today()
    )
    with db_session(config.get_db()) as conn:
        add_message(conn, aid, "user", body_message)
        asst = add_message(conn, aid, "assistant", reply)
    out: dict[str, Any] = {
        "reply": reply,
        "message": asst,
        "sessions_in_context": True,
        "sessions_source": sessions_snap.get("source"),
        "app_plan": overview_app_plan,
        "pending_write_reopen": True,
        "workout_proposal": None,
        "plan_proposal": None,
    }
    if proposal and proposal.get("workouts"):
        with db_session(config.get_db()) as conn:
            planned_this_week = _count_planned_this_week_db(conn, aid)
        gate = validate_workouts_against_constraints(
            athlete,
            proposal.get("workouts") or [],
            existing_planned_this_week=planned_this_week,
        )
        if gate["ok"]:
            out["workout_proposal"] = proposal
            out["confirm_required"] = True
            out["proposal_inferred"] = True
            out["proposal_hint"] = (
                "Bekreft forhåndsvisningskortet — ingenting er lagret/synket ennå."
            )
        elif gate.get("accepted"):
            out["workout_proposal"] = {"workouts": gate["accepted"], "inferred": True}
            out["confirm_required"] = True
            out["proposal_inferred"] = True
            out["constraint_reasons"] = gate.get("reasons")
        elif gate.get("cap_hit"):
            _attach_cap_replace_offer(
                out, aid=aid, proposal=proposal, gate=gate, reply=reply
            )
        else:
            out["reply"] = sanitize_unconfirmed_write_claims(
                reply, has_confirm_card=False
            )
            out["workout_proposal_blocked"] = True
            out["constraint_reasons"] = gate.get("reasons")
    elif plan_prop and plan_prop.get("rebuild"):
        try:
            with db_session(config.get_db()) as conn:
                blocks = list_plan_blocks(conn, aid)
                existing_n = count_planned_sessions(conn, aid)
            if blocks and (plan_prop.get("scope") or "week") == "week":
                week_built = build_week_adjust_sessions(
                    blocks,
                    athlete=athlete,
                    week_start=plan_prop.get("week_start") or "this_week",
                    ease_load=bool(plan_prop.get("ease_load")),
                )
                out["plan_proposal"] = {
                    **plan_prop,
                    "scope": "week",
                    "week_start": week_built["week_start"],
                    "week_end": week_built["week_end"],
                    "sessions": week_built["sessions"],
                    "count": week_built["count"],
                    "planned_sessions_count": existing_n,
                    "confirm_hint": (
                        f"Bekreft for å erstatte kun uka "
                        f"{week_built['week_start']}–{week_built['week_end']}."
                    ),
                }
                out["confirm_required"] = True
                out["plan_hint"] = (
                    "Bekreft planjustering — ingenting er lagret/synket ennå."
                )
            else:
                out["reply"] = sanitize_unconfirmed_write_claims(
                    reply, has_confirm_card=False
                )
        except Exception as exc:  # noqa: BLE001
            out["reply"] = (
                sanitize_unconfirmed_write_claims(reply, has_confirm_card=False)
                + f" ({format_exc_nb(exc)})"
            )
    else:
        out["reply"] = sanitize_unconfirmed_write_claims(
            out.get("reply") or reply, has_confirm_card=False
        )
    # Final sanitize — never claim success from this path
    has_card = bool(
        (out.get("workout_proposal") or {}).get("workouts")
        or out.get("plan_proposal")
        or out.get("workout_replace_proposal")
    )
    out["reply"] = sanitize_unconfirmed_write_claims(
        out.get("reply") or "", has_confirm_card=has_card
    )
    return out


def _chat_intervals_plan_sync(
    *,
    aid: str,
    athlete: dict[str, Any],
    body_message: str,
    plan_blocks: list[dict[str, Any]],
    stored_planned: list[dict[str, Any]],
    intervals_ok: bool,
    secrets: dict[str, Any] | None,
    sessions_snap: dict[str, Any],
    overview_app_plan: dict[str, Any],
) -> dict[str, Any]:
    """Sync existing planned_sessions → Intervals near window. No new plan inventing."""
    planned_n = len(stored_planned or [])
    intervals_pending = None
    intervals_sync: dict[str, Any] | None = None
    prep_error = None
    workouts_count = None
    from_stored = False
    blocks = list(plan_blocks or [])

    # Prefer stored planned_sessions; plan_blocks optional (notes only when present).
    if planned_n > 0 and intervals_ok:
        key = ((secrets or {}).get("intervals_api_key") or "").strip()
        icu = ((secrets or {}).get("intervals_athlete_id") or "").strip()
        try:
            with db_session(config.get_db()) as conn:
                bundle = _sync_bundle_preferring_stored(
                    conn,
                    aid,
                    blocks,
                    athlete,
                    allow_degraded=True,
                )
            from_stored = bool(bundle.get("from_stored_sessions"))
            workouts_count = bundle.get("workouts_count")
            intervals_sync = {
                "will_push": True,
                "kind": bundle.get("kind"),
                "description": bundle.get("description_no"),
                "events_count": bundle.get("count"),
                "notes_count": bundle.get("notes_count"),
                "workouts_count": bundle.get("workouts_count"),
                "zwo_count": bundle.get("zwo_count"),
                "weeks": bundle.get("weeks"),
                "icu_sync_weeks": bundle.get("icu_sync_weeks", ICU_SYNC_WEEKS),
                "from_stored_sessions": from_stored,
                "events_preview": (bundle.get("events_preview") or [])[:40],
                "workouts_preview": (bundle.get("workouts_preview") or [])[:40],
            }
            if bundle.get("events") and key and icu:
                with db_session(config.get_db()) as conn:
                    pending = insert_pending_action(
                        conn,
                        aid,
                        "intervals_calendar_push",
                        {
                            "op": "push",
                            "block_ids": [b["id"] for b in blocks if b.get("id")],
                            "events": bundle["events"],
                            "intervals_athlete_id": icu,
                            "notes_count": bundle["notes_count"],
                            "workouts_count": bundle["workouts_count"],
                            "zwo_count": bundle["zwo_count"],
                            "weeks": bundle["weeks"],
                            "builder": bundle["builder"],
                            "knowledge_paths": bundle.get("knowledge_paths") or [],
                            "from_stored_sessions": from_stored,
                        },
                    )
                intervals_pending = {
                    "pending_id": pending["id"],
                    "op": "push",
                    "count": bundle["count"],
                    "notes_count": bundle["notes_count"],
                    "workouts_count": bundle["workouts_count"],
                    "zwo_count": bundle.get("zwo_count", 0),
                    "weeks": bundle.get("weeks", ICU_SYNC_WEEKS),
                    "events": (bundle.get("events_preview") or [])[:40],
                    "events_truncated": max(
                        0, int(bundle.get("count") or 0) - 40
                    ),
                    "from_stored_sessions": from_stored,
                    "confirm_required": True,
                    "message": (
                        f"Bekreft Sync: {bundle.get('workouts_count', 0)} økter "
                        f"fra lagrede planned_sessions (første "
                        f"{bundle.get('weeks', ICU_SYNC_WEEKS)} uker)"
                        + (
                            f" + {bundle.get('notes_count', 0)} grovplan-noter"
                            if int(bundle.get("notes_count") or 0) > 0
                            else " (uten grovplan-noter)"
                        )
                        + f" til Intervals. Full plan ({planned_n} økter) blir i appen."
                    ),
                }
            elif not key or not icu:
                prep_error = (
                    "Intervals-opplysninger mangler (athlete-ID / API-nøkkel). "
                    "Gå til Du → Intervals."
                )
            elif not bundle.get("events"):
                prep_error = (
                    bundle.get("error")
                    or "Ingen hendelser å synce i nærvinduet fra lagrede økter."
                )
        except Exception as exc:  # noqa: BLE001
            prep_error = format_exc_nb(exc)

    reply = intervals_plan_sync_reply_nb(
        planned_count=planned_n,
        icu_sync_weeks=ICU_SYNC_WEEKS,
        workouts_count=workouts_count,
        intervals_connected=intervals_ok,
        from_stored=from_stored or planned_n > 0,
    )
    if prep_error and intervals_ok and planned_n > 0:
        reply = (
            f"{reply}\n\nKunne ikke bygge Sync-forhåndsvisning: {prep_error} "
            "Prøv Plan → Sync til Intervals, eller si ifra. "
            "Jeg finner ikke opp økter i JSON for å late som de er i Intervals."
        )

    with db_session(config.get_db()) as conn:
        add_message(conn, aid, "user", body_message)
        asst = add_message(conn, aid, "assistant", reply)

    out: dict[str, Any] = {
        "reply": reply,
        "message": asst,
        "sessions_in_context": True,
        "sessions_source": sessions_snap.get("source"),
        "app_plan": overview_app_plan,
        "intervals_sync_intent": True,
        "planned_sessions_count": planned_n,
        "icu_sync_weeks": ICU_SYNC_WEEKS,
        # Hard rule: sync path never invents workout/plan fences for the LLM UI.
        "workout_proposal": None,
        "plan_proposal": None,
    }
    if intervals_sync:
        out["intervals_sync"] = intervals_sync
    if intervals_pending:
        out["intervals_pending"] = intervals_pending
        out["confirm_required"] = True
        out["sync_hint"] = intervals_pending.get("message")
    elif not intervals_ok and planned_n > 0:
        out["intervals_connect_hint"] = (
            "Koble Intervals under Du (athlete-ID + API-nøkkel), deretter Sync nærvindu."
        )
    elif planned_n <= 0:
        out["proposal_hint"] = (
            "Ingen planned_sessions — fullfør setup/confirm før Intervals-sync."
        )
    if prep_error:
        out["intervals_prep_error"] = prep_error
    return out


@app.get("/v1/overview")
def overview(x_athlete_id: str | None = Header(default=None)) -> dict[str, Any]:
    aid = _require_athlete(x_athlete_id)
    with db_session(config.get_db()) as conn:
        athlete = get_athlete(conn, aid)
        if not athlete:
            raise HTTPException(404, "Utøver ikke funnet")
        secrets = get_athlete_secrets(conn, aid)
        blocks = list_plan_blocks(conn, aid)
    return _overview_payload(athlete, secrets, blocks)


@app.get("/v1/beta/forecasts")
def beta_forecasts(
    x_athlete_id: str | None = Header(default=None),
    lookback_days: int = Query(default=90, ge=14, le=180),
    horizon_days: int = Query(default=28, ge=7, le=120),
) -> dict[str, Any]:
    """Experimental Beta: CTL/ATL/TSB past+planlagt, ACWR bands, race-form.

    Never auto-applies plan changes. Past = ICU activities/wellness;
    future = planned_sessions (labeled planlagt).
    """
    aid = _require_athlete(x_athlete_id)
    with db_session(config.get_db()) as conn:
        athlete = get_athlete(conn, aid)
        if not athlete:
            raise HTTPException(404, "Utøver ikke funnet")
        secrets = get_athlete_secrets(conn, aid)
        today = date.today()
        past_start = today - timedelta(days=lookback_days - 1)
        future_end = today + timedelta(days=horizon_days - 1)
        # Include planned through goal when near — build_beta_forecasts may extend
        days_g = days_to_goal(athlete, today=today)
        if days_g is not None and 0 < days_g <= 180:
            future_end = max(future_end, today + timedelta(days=days_g))
        planned_rows = list_planned_sessions(
            conn,
            aid,
            start_date=past_start.isoformat(),
            end_date=future_end.isoformat(),
        )
    return build_beta_forecasts(
        athlete=athlete,
        secrets=secrets,
        planned_sessions=planned_rows,
        today=today,
        lookback_days=lookback_days,
        horizon_days=horizon_days,
    )


@app.get("/v1/dashboard")
def dashboard(
    x_athlete_id: str | None = Header(default=None),
    period: str | None = Query(
        default=None,
        description="Periode-preset: 7d, 14d, 30d, 90d eller custom (default 14d)",
    ),
    from_: str | None = Query(
        default=None,
        alias="from",
        description="Custom startdato YYYY-MM-DD (sammen med to)",
    ),
    to: str | None = Query(
        default=None,
        description="Custom sluttdato YYYY-MM-DD (sammen med from)",
    ),
) -> dict[str, Any]:
    """Period training + sleep/body + season compliance (separate blocks).

    Query ``period`` / ``from`` / ``to`` scopes training + wellness to a window.
    Compliance stays season/plan targets and is never written to Intervals.
    """
    try:
        period_meta = parse_period_window(period, from_, to)
    except PeriodValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    start = date.fromisoformat(period_meta["start"])
    end = date.fromisoformat(period_meta["end"])
    period_days = int(period_meta["days"])

    aid = _require_athlete(x_athlete_id)
    with db_session(config.get_db()) as conn:
        athlete = get_athlete(conn, aid)
        if not athlete:
            raise HTTPException(404, "Utøver ikke funnet")
        secrets = get_athlete_secrets(conn, aid)
        blocks = list_plan_blocks(conn, aid)
        planned_rows = list_planned_sessions(
            conn,
            aid,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )
    overview_data = _overview_payload(athlete, secrets, blocks)
    show_body = bool(athlete.get("show_body_metrics", False))
    training = resolve_period_training(
        secrets, start, end, planned_sessions=planned_rows
    )
    wellness = resolve_wellness_bundle(
        secrets,
        days=period_days,
        include_body=show_body,
        start=start,
        end=end,
    )
    # CTL/ATL: ICU wellness only — never invent; strip future fake projections
    load_series = wellness.get("load_series") or {}
    if isinstance(load_series, dict):
        load_series = {
            **load_series,
            "series_kind": "executed",
            "label_nb": "CTL/ATL (Intervals wellness)",
            "note": (
                load_series.get("note")
                or "CTL/ATL fra Intervals wellness. Ingen LLM-inventerte tall."
            ),
            "projected": False,
        }
    progress = overview_data.get("progress") or {}
    session_compliance_4w = None
    try:
        with db_session(config.get_db()) as conn:
            comps = completions_by_external_id(conn, aid)
        sess_bundle = list_sessions(secrets, comps, past_days=28, future_days=1)
        session_compliance_4w = sess_bundle.get("rolling_compliance_4w")
    except Exception:  # noqa: BLE001 — soft-fail; season compliance still works
        session_compliance_4w = None
    # Back-compat: hours/load mirror period training (no season targets mixed in)
    hours = {
        "disciplines": [
            {
                "id": d["id"],
                "label": d["label"],
                "completed_hours": d["hours"],
                "session_count": d["session_count"],
            }
            for d in (training.get("disciplines") or [])
        ],
        "window": training.get("window"),
        "days": training.get("days"),
        "source": training.get("source"),
        "activity_count": training.get("activity_count"),
        "total_hours": training.get("total_hours"),
        "fetch_error": training.get("fetch_error"),
        "fetch_error_detail": training.get("fetch_error_detail"),
        "note": training.get("note"),
    }
    load = {
        "from_wellness": wellness.get("load_wellness"),
        "series": load_series,
        "hours_summary": hours,
        "note": (
            "Belastning: CTL/ATL = Intervals wellness (gjennomført). "
            "Volum: ICU-aktiviteter bakover, planned_sessions fremover (planlagt). "
            "LLM/chat inventerer ikke CTL/ATL."
        ),
    }
    return {
        "show_body_metrics": show_body,
        "period": period_meta,
        "training": training,
        "hours": hours,
        "load": load,
        "sleep": wellness.get("sleep"),
        "body": wellness.get("body"),
        "body_hidden": (not show_body) or bool(wellness.get("body_hidden")),
        "wellness_window": wellness.get("window"),
        "wellness_source": wellness.get("source"),
        "wellness_fetch_error": wellness.get("fetch_error"),
        "wellness_fetch_error_detail": wellness.get("fetch_error_detail"),
        "compliance": progress,
        "compliance_app_computed": True,
        "compliance_written_to_intervals": False,
        "session_compliance_4w": session_compliance_4w,
        "periodization": overview_data.get("periodization"),
        "form": {
            "ftp_tested": overview_data.get("ftp_tested"),
            "ftp_estimated": overview_data.get("ftp_estimated"),
            "vo2_estimate": overview_data.get("vo2_estimate"),
            "estimate_confidence": overview_data.get("estimate_confidence"),
            "gate_open": overview_data.get("gate_open"),
            "qualifying_sessions": overview_data.get("qualifying_sessions"),
            "required_sessions": overview_data.get("required_sessions"),
            "estimate_disclaimer": overview_data.get("estimate_disclaimer"),
        },
        "uplift_line": overview_data.get("uplift_line"),
        "intervals_linked": overview_data.get("intervals_linked"),
        "intervals_hint": overview_data.get("intervals_hint"),
    }


@app.get("/v1/sessions/completions/recent")
def get_recent_completions(
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    aid = _require_athlete(x_athlete_id)
    with db_session(config.get_db()) as conn:
        if not get_athlete(conn, aid):
            raise HTTPException(404, "Utøver ikke funnet")
        rows = list_session_completions(conn, aid, limit=50)
    return {"completions": rows}


@app.get("/v1/sessions")
def get_sessions(x_athlete_id: str | None = Header(default=None)) -> dict[str, Any]:
    """Recent + upcoming: app planned_sessions + Intervals; soft-fail without ICU."""
    aid = _require_athlete(x_athlete_id)
    with db_session(config.get_db()) as conn:
        if not get_athlete(conn, aid):
            raise HTTPException(404, "Utøver ikke funnet")
        return _sessions_bundle_for_athlete(conn, aid)


@app.get("/v1/sessions/{session_id}")
def get_session_detail(
    session_id: str,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Structured session detail for library → detail view (+ chat seed)."""
    aid = _require_athlete(x_athlete_id)
    with db_session(config.get_db()) as conn:
        if not get_athlete(conn, aid):
            raise HTTPException(404, "Utøver ikke funnet")
        secrets = get_athlete_secrets(conn, aid)
        comps = completions_by_external_id(conn, aid)
        payload = _sessions_bundle_for_athlete(
            conn, aid, secrets=secrets, comps=comps
        )
    found = find_session_in_bundle(payload, session_id)
    if not found:
        sid = session_id.strip()
        found = {
            "id": sid,
            "external_id": sid.split(":", 1)[-1] if ":" in sid else sid,
            "kind": "unknown",
            "name": "Økt",
            "date": None,
            "completion": comps.get(sid)
            or comps.get(sid.split(":", 1)[-1] if ":" in sid else sid),
            "editable": False,
        }
    detail = session_detail_payload(payload, found)
    return detail


@app.post("/v1/sessions/{session_id}/edit/preview")
def session_edit_preview(
    session_id: str,
    body: SessionEditPreviewIn,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Athlete (or coach-proposed) field edits → same ICU preview→confirm path."""
    aid = _require_athlete(x_athlete_id)
    athlete, _key, icu = _require_intervals_secrets(aid)
    from sessions_service import (
        builder_steps_to_description,
        normalize_builder_steps,
        total_builder_duration,
    )

    steps = normalize_builder_steps(body.steps) if body.steps else []
    description = body.description or ""
    if steps and not description.strip():
        description = builder_steps_to_description(steps)
    dur = body.duration_minutes
    if dur is None and steps:
        dur = total_builder_duration(steps)
    workout: dict[str, Any] = {
        "name": body.name.strip(),
        "date": body.date.strip()[:10],
        "sport": (body.sport or "other").strip().lower(),
        "description": description,
        "start_time": body.start_time or "07:00",
    }
    if dur is not None:
        workout["duration_minutes"] = dur
    # Editing an existing coach workout does not add a new session slot
    gate = validate_workouts_against_constraints(
        athlete,
        [workout],
        existing_planned_this_week=0,
    )
    if not gate["accepted"]:
        raise HTTPException(
            400,
            gate.get("ask")
            or (
                " ".join(gate["reasons"][:3])
                if gate["reasons"]
                else "Avtale blokkerer øktendringen."
            ),
        )
    workout = gate["accepted"][0]
    try:
        events = build_workout_events([workout], athlete=athlete)
    except Exception as exc:  # noqa: BLE001
        from plan_workouts import format_exc_nb as _fmt

        raise HTTPException(500, f"Økt-bygger feilet: {_fmt(exc)}") from exc
    if not events:
        raise HTTPException(400, "Ugyldig økt (trenger name + date YYYY-MM-DD)")
    # Prefer upsert of the same coach external_id when editing an existing day
    eid = (body.external_id or "").strip()
    if eid.startswith("ll-coach-w-"):
        events[0]["external_id"] = eid
    payload = {
        "op": "workout_push",
        "events": events,
        "workouts": [workout],
        "builder_steps": steps,
        "intervals_athlete_id": icu,
        "source_session_id": session_id.strip(),
    }
    summary = [public_event_preview(e) for e in events]
    with db_session(config.get_db()) as conn:
        pending = insert_pending_action(conn, aid, "intervals_workout_push", payload)
    return {
        "pending_id": pending["id"],
        "op": "workout_push",
        "count": len(events),
        "expires_at": pending.get("expires_at"),
        "events": summary[:40],
        "events_truncated": max(0, len(events) - 40),
        "confirm_required": True,
        "session_id": session_id.strip(),
        "builder_steps": steps,
        "message": (
            f"Bekreft for å oppdatere {len(events)} økt(er) på Intervals. "
            "Ingenting skrives før du bekrefter."
        ),
        "write_gap": (
            "Strukturerte ZWO/CSV-økter pushes fortsatt via CLI "
            "(scripts/intervals_push_calendar.py), ikke via chat/redigering."
        ),
        "constraints_summary_nb": gate.get("constraints_summary_nb"),
    }


@app.post("/v1/sessions/{session_id}/builder/confirm")
def session_builder_confirm(
    session_id: str,
    body: SessionBuilderConfirmIn,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Visual øktbygger: confirm → save steps_json on planned_sessions (app SoT).

    Optional Intervals sync only via prepare_intervals_sync + pending confirm — never silent.
    """
    aid = _require_athlete(x_athlete_id)
    from sessions_service import (
        builder_steps_to_description,
        normalize_builder_steps,
        total_builder_duration,
    )

    steps = normalize_builder_steps(body.steps)
    if not steps:
        raise HTTPException(422, "Legg til minst ett steg (warmup/work/recover/cooldown).")
    description = (body.description or "").strip() or builder_steps_to_description(steps)
    dur = body.duration_minutes
    if dur is None:
        dur = total_builder_duration(steps)
    intervals_pending = None
    with db_session(config.get_db()) as conn:
        athlete = get_athlete(conn, aid)
        if not athlete:
            raise HTTPException(404, "Utøver ikke funnet")
        existing = get_planned_session(conn, aid, session_id)
        if existing:
            saved = update_planned_session_builder(
                conn,
                aid,
                existing["id"],
                {
                    "name": body.name.strip(),
                    "session_date": body.date.strip()[:10],
                    "sport": (body.sport or "other").strip().lower(),
                    "duration_minutes": dur,
                    "start_time": body.start_time or "07:00",
                    "description": description,
                    "steps": steps,
                },
            )
        else:
            # Create new detalj row when opening builder for a fresh day
            rows = insert_planned_session_rows(
                conn,
                aid,
                [
                    {
                        "name": body.name.strip(),
                        "session_date": body.date.strip()[:10],
                        "sport": (body.sport or "other").strip().lower(),
                        "duration_minutes": dur,
                        "start_time": body.start_time or "07:00",
                        "description": description,
                        "steps": steps,
                        "external_id": (body.external_id or "").strip() or None,
                        "source": "builder",
                        "plan_tier": "detalj",
                    }
                ],
            )
            saved = rows[0] if rows else None
        if body.prepare_intervals_sync and saved:
            secrets = get_athlete_secrets(conn, aid)
            key = ((secrets or {}).get("intervals_api_key") or "").strip()
            icu = ((secrets or {}).get("intervals_athlete_id") or "").strip()
            if key and icu:
                workout = {
                    "name": saved.get("name"),
                    "date": saved.get("session_date"),
                    "sport": saved.get("sport"),
                    "description": saved.get("description") or "",
                    "duration_minutes": saved.get("duration_minutes"),
                    "start_time": saved.get("start_time") or "07:00",
                    "steps": steps or saved.get("steps"),
                    "planned_path": saved.get("planned_path") or "",
                }
                ath = get_athlete(conn, aid)
                events = build_workout_events([workout], athlete=ath)
                eid = (saved.get("external_id") or "").strip()
                if eid.startswith("ll-coach-w-") and events:
                    events[0]["external_id"] = eid
                if events:
                    pending = insert_pending_action(
                        conn,
                        aid,
                        "intervals_workout_push",
                        {
                            "op": "workout_push",
                            "events": events,
                            "workouts": [workout],
                            "builder_steps": steps,
                            "intervals_athlete_id": icu,
                            "source_session_id": session_id.strip(),
                        },
                    )
                    intervals_pending = {
                        "pending_id": pending["id"],
                        "confirm_required": True,
                        "count": len(events),
                        "message": (
                            "Økt lagret i planen. Bekreft Sync for å skrive til Intervals."
                        ),
                    }
    return {
        "ok": True,
        "session": saved,
        "builder_steps": steps,
        "written_to_intervals": False,
        "intervals_pending": intervals_pending,
        "confirm_required": bool(intervals_pending),
        "message": (
            "Struktur lagret i planned_sessions (app). "
            + (
                "Bekreft Sync for Intervals."
                if intervals_pending
                else "Intervals urørt til du kjører Sync."
            )
        ),
    }


@app.post("/v1/sessions/{session_id}/completion")
def post_session_completion(
    session_id: str,
    body: SessionCompletionIn,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Log completion/skip reason in SQLite (+ optional profile notes). Not ICU."""
    aid = _require_athlete(x_athlete_id)
    external = session_id.strip()
    data = {
        "external_session_id": external,
        "source": body.source or "intervals",
        "session_name": body.session_name or "",
        "session_date": body.session_date,
        "discipline": body.discipline or "",
        "status": body.status,
        "reason": body.reason or "",
        "note": body.note or "",
    }
    try:
        with db_session(config.get_db()) as conn:
            athlete = get_athlete(conn, aid)
            if not athlete:
                raise HTTPException(404, "Utøver ikke funnet")
            row = upsert_session_completion(conn, aid, data)
            if body.append_profile_note:
                line = completion_note_line({**data, **(row or {})})
                prev = (athlete.get("notes") or "").rstrip()
                marker = "Øktlogg (app)"
                if marker in prev:
                    notes = f"{prev}\n- {line}"
                else:
                    notes = f"{prev}\n\n## {marker}\n- {line}".strip()
                athlete = update_athlete(conn, aid, {"notes": notes}) or athlete
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    path = write_profile(config.ATHLETES_DATA_DIR, athlete)
    return {
        "completion": row,
        "athlete_notes": athlete.get("notes"),
        "profile_path": str(path.relative_to(config.REPO_ROOT))
        if path.is_relative_to(config.REPO_ROOT)
        else str(path),
        "written_to_intervals": False,
    }


@app.get("/v1/athlete/me/plan-blocks")
def get_plan_blocks(x_athlete_id: str | None = Header(default=None)) -> dict[str, Any]:
    aid = _require_athlete(x_athlete_id)
    with db_session(config.get_db()) as conn:
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
    with db_session(config.get_db()) as conn:
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
    with db_session(config.get_db()) as conn:
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
    with db_session(config.get_db()) as conn:
        if not get_athlete(conn, aid):
            raise HTTPException(404, "Utøver ikke funnet")
        ok = delete_plan_block(conn, aid, block_id)
    if not ok:
        raise HTTPException(404, "Blokk ikke funnet")
    return {"ok": True}


def _require_intervals_secrets(aid: str) -> tuple[dict[str, Any], str, str]:
    with db_session(config.get_db()) as conn:
        athlete = get_athlete(conn, aid)
        secrets = get_athlete_secrets(conn, aid)
    if not athlete:
        raise HTTPException(404, "Utøver ikke funnet")
    key = ((secrets or {}).get("intervals_api_key") or "").strip()
    icu = ((secrets or {}).get("intervals_athlete_id") or "").strip()
    if not key or not icu:
        raise HTTPException(400, "Koble Intervals under Du først")
    return athlete, key, icu


@app.post("/v1/form/recompute")
def form_recompute(x_athlete_id: str | None = Header(default=None)) -> dict[str, Any]:
    """Recompute FTP/VO₂ estimates from Intervals bike+power (90d) and persist."""
    aid = _require_athlete(x_athlete_id)
    with db_session(config.get_db()) as conn:
        athlete = get_athlete(conn, aid)
        secrets = get_athlete_secrets(conn, aid)
        if not athlete:
            raise HTTPException(404, "Utøver ikke funnet")
    clear_form_caches()
    estimates = resolve_form_estimates(athlete, secrets, use_cache=False)
    patch = persist_estimates_patch(estimates)
    if patch:
        with db_session(config.get_db()) as conn:
            athlete = update_athlete(conn, aid, patch) or athlete
    return {
        "athlete": {
            "ftp_estimated": athlete.get("ftp_estimated"),
            "vo2_estimate": athlete.get("vo2_estimate"),
            "estimate_confidence": athlete.get("estimate_confidence"),
            "estimate_updated_at": athlete.get("estimate_updated_at"),
            "estimate_source": athlete.get("estimate_source"),
        },
        "estimates": estimates,
    }


@app.post("/v1/athlete/me/intervals/calendar/preview")
def calendar_preview(
    body: CalendarSyncPreviewIn,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Build pending push/delete — confirm required before ICU write."""
    aid = _require_athlete(x_athlete_id)
    op = (body.op or "").strip().lower()
    if op not in ("push", "delete"):
        raise HTTPException(400, "op må være push eller delete")
    _athlete, key, icu = _require_intervals_secrets(aid)
    with db_session(config.get_db()) as conn:
        blocks = list_plan_blocks(conn, aid)
        stored_for_push = (
            list_planned_sessions(conn, aid) if op == "push" else []
        )
    rs, re = _calendar_sync_range(body.start, body.end)
    selected = select_blocks(
        blocks, block_ids=body.block_ids, start=body.start, end=body.end
    )
    if not selected:
        raise HTTPException(400, "Ingen planblokker i utvalget")
    if op == "push" and stored_for_push and rs and re:
        stored_for_push = filter_planned_sessions_date_range(
            stored_for_push, rs, re
        )

    if op == "push":
        try:
            bundle = build_plan_sync_bundle(
                selected,
                athlete=_athlete,
                include_notes=bool(body.include_notes),
                planned_sessions=stored_for_push if stored_for_push else None,
                sync_range_start=rs,
                sync_range_end=re,
            )
            bundle = _apply_range_to_bundle(bundle, rs, re)
        except (ImportError, OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(
                500,
                f"Kunne ikke bygge økter til Intervals: {exc}",
            ) from exc
        events = bundle["events"]
        if not events:
            raise HTTPException(400, "Blokkene mangler start/slutt-dato")
        payload = {
            "op": "push",
            "block_ids": [b["id"] for b in selected],
            "events": events,
            "intervals_athlete_id": icu,
            "notes_count": bundle["notes_count"],
            "workouts_count": bundle["workouts_count"],
            "zwo_count": bundle["zwo_count"],
            "weeks": bundle["weeks"],
            "builder": bundle["builder"],
            "knowledge_paths": bundle["knowledge_paths"],
            "from_stored_sessions": bundle.get("from_stored_sessions", False),
            "sync_range": bundle.get("sync_range"),
        }
        summary = bundle["events_preview"]
        count = bundle["count"]
    else:
        events = build_block_note_events(selected)
        external_ids = [e["external_id"] for e in events]
        # Also include any coach events already on calendar in the window
        win_start, win_end = status_window_for_blocks(selected)
        try:
            existing = filter_coach_events(
                fetch_events(key, icu, win_start.isoformat(), win_end.isoformat())
            )
        except RuntimeError:
            existing = []
        for ev in existing:
            eid = ev.get("external_id")
            if eid and eid not in external_ids:
                external_ids.append(eid)
        if not external_ids:
            raise HTTPException(400, "Ingen agent-hendelser (noter/økter) å fjerne i utvalget")
        payload = {
            "op": "delete",
            "block_ids": [b["id"] for b in selected],
            "external_ids": external_ids,
            "intervals_athlete_id": icu,
        }
        summary = [{"external_id": eid} for eid in external_ids]
        count = len(external_ids)

    with db_session(config.get_db()) as conn:
        pending = insert_pending_action(conn, aid, f"intervals_calendar_{op}", payload)
    out: dict[str, Any] = {
        "pending_id": pending["id"],
        "op": op,
        "count": count,
        "expires_at": pending.get("expires_at"),
        "blocks": [
            {
                "id": b.get("id"),
                "title": b.get("title"),
                "start_date": b.get("start_date"),
                "end_date": b.get("end_date"),
            }
            for b in selected
        ],
        "events": summary[:40],
        "events_truncated": max(0, count - 40),
        "confirm_required": True,
    }
    if op == "push":
        out["notes_count"] = payload.get("notes_count", 0)
        out["workouts_count"] = payload.get("workouts_count", 0)
        out["weeks"] = payload.get("weeks", 2)
        out["zwo_count"] = payload.get("zwo_count", 0)
        out["builder"] = payload.get("builder")
        out["knowledge_paths"] = payload.get("knowledge_paths") or []
        out["from_stored_sessions"] = payload.get("from_stored_sessions", False)
        if payload.get("sync_range"):
            out["sync_range"] = payload["sync_range"]
        out["workouts_preview"] = [
            e for e in summary if e.get("category") == "WORKOUT"
        ][:40]
        src = (
            "lagrede økter (planned_sessions)"
            if out["from_stored_sessions"]
            else "øktbibliotek"
        )
        notes_bit = (
            f" + {out['notes_count']} grovplan-noter"
            if int(out["notes_count"] or 0) > 0
            else " (uten grovplan-noter)"
        )
        range_bit = ""
        if out.get("sync_range"):
            sr = out["sync_range"]
            range_bit = f" periode {sr.get('start')}–{sr.get('end')},"
        out["message"] = (
            f"Bekreft for å synce {out['workouts_count']} økter fra {src}{range_bit} "
            f"({out['zwo_count']} med ZWO)"
            f"{notes_bit} til Intervals. "
            "Upsert ll-coach-… / ll-coach-w-…."
        )
    else:
        out["message"] = (
            f"Bekreft for å fjerne {count} agent-hendelser (noter + økter) fra Intervals."
        )
    return out


@app.post("/v1/athlete/me/intervals/calendar/confirm")
def calendar_confirm(
    body: CalendarConfirmIn,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Execute a previously previewed push/delete/workout against Intervals.

    Chat workout_push may persist ``planned_sessions`` locally even when
    Intervals is not connected (events list empty).
    """
    aid = _require_athlete(x_athlete_id)
    with db_session(config.get_db()) as conn:
        athlete = get_athlete(conn, aid)
        secrets = get_athlete_secrets(conn, aid)
        pending = get_pending_action(conn, aid, body.pending_id)
    if not athlete:
        raise HTTPException(404, "Utøver ikke funnet")
    if not pending:
        raise HTTPException(404, "Pending handling ikke funnet")
    if pending.get("status") != "pending":
        raise HTTPException(400, f"Handling allerede {pending.get('status')}")
    expires = pending.get("expires_at")
    if expires:
        from datetime import datetime, timezone

        try:
            exp = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp:
                with db_session(config.get_db()) as conn:
                    mark_pending_action(conn, aid, body.pending_id, "expired")
                raise HTTPException(400, "Forhåndsvisning utløpt — lag ny")
        except ValueError:
            pass

    key = ((secrets or {}).get("intervals_api_key") or "").strip()
    icu = ((secrets or {}).get("intervals_athlete_id") or "").strip()
    payload = pending.get("payload") or {}
    op = payload.get("op")
    try:
        if op in ("push", "workout_push"):
            persisted: list[dict[str, Any]] = []
            if op == "workout_push" and payload.get("persist_planned_sessions"):
                rows = payload.get("planned_sessions") or []
                if rows:
                    with db_session(config.get_db()) as conn:
                        replace_ids = [
                            str(x).strip()
                            for x in (payload.get("replace_session_ids") or [])
                            if str(x).strip()
                        ]
                        if replace_ids:
                            delete_planned_sessions_by_ids(conn, aid, replace_ids)
                        ext_ids = [
                            str(r.get("external_id") or "").strip()
                            for r in rows
                            if str(r.get("external_id") or "").strip()
                        ]
                        if ext_ids:
                            delete_planned_sessions_by_external_ids(conn, aid, ext_ids)
                        persisted = insert_planned_session_rows(conn, aid, rows)
            events = payload.get("events") or []
            expected = len(events)
            if expected == 0:
                if op == "push":
                    raise HTTPException(400, "Ingen hendelser å synce")
                outcome = {
                    "pushed": 0,
                    "expected": 0,
                    "planned_sessions_saved": len(persisted),
                    "result": {"count": 0, "local_only": True},
                    "retry_safe": True,
                }
            else:
                if not key or not icu:
                    raise HTTPException(400, "Koble Intervals under Du først")
                result = post_events_bulk(key, icu, events, upsert=True)
                pushed = int(result.get("count") or 0)
                # Fail closed on empty/partial — do NOT mark pending confirmed
                if expected > 0 and pushed < expected:
                    raise RuntimeError(
                        f"Intervals synket bare {pushed}/{expected} hendelser. "
                        "Pending beholdes — prøv bekreft igjen (upsert er trygg)."
                    )
                outcome = {
                    "pushed": pushed,
                    "expected": expected,
                    "planned_sessions_saved": len(persisted),
                    "result": result,
                    "retry_safe": True,
                }
            # Ticker: local save and/or ICU sync (never auto-apply)
            replace_ids = [
                str(x).strip()
                for x in (payload.get("replace_session_ids") or [])
                if str(x).strip()
            ]
            with db_session(config.get_db()) as conn:
                if persisted:
                    emit_sessions_saved(
                        conn,
                        aid,
                        count=len(persisted),
                        source=str(op or "workout_push"),
                        replace=bool(replace_ids),
                    )
                if expected > 0 and int(outcome.get("pushed") or 0) > 0:
                    emit_sync_ok(
                        conn,
                        aid,
                        pushed=int(outcome["pushed"]),
                        expected=expected,
                    )
        elif op == "delete":
            if not key or not icu:
                raise HTTPException(400, "Koble Intervals under Du først")
            ids = payload.get("external_ids") or []
            result = delete_events_bulk(key, icu, ids)
            deleted = result.get("eventsDeleted", len(ids))
            outcome = {"deleted": deleted, "result": result, "retry_safe": True}
            with db_session(config.get_db()) as conn:
                emit_sync_ok(
                    conn,
                    aid,
                    pushed=int(deleted or 0),
                    expected=len(ids),
                )
        else:
            raise HTTPException(400, "Ugyldig pending op")
    except RuntimeError as exc:
        # Leave pending as-is so client can retry confirm safely (upsert)
        try:
            with db_session(config.get_db()) as conn:
                emit_sync_fail(conn, aid, error=str(exc))
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(
            502,
            f"{str(exc)[:480]} Pending er ikke bekreftet — trygg å prøve igjen.",
        ) from exc

    with db_session(config.get_db()) as conn:
        mark_pending_action(conn, aid, body.pending_id, "confirmed")
    # Bust caches so next overview/sessions read sees fresh ICU state
    clear_progress_cache()
    clear_wellness_cache()
    clear_form_caches()
    # Soft re-fetch sessions for client trust (soft-fail — confirm already succeeded)
    sessions_bundle: dict[str, Any] | None = None
    try:
        with db_session(config.get_db()) as conn:
            sessions_bundle = _sessions_bundle_for_athlete(
                conn,
                aid,
                secrets=secrets,
                past_days=14,
                future_days=14,
            )
    except Exception:  # noqa: BLE001
        sessions_bundle = None
    out: dict[str, Any] = {
        "ok": True,
        "op": op,
        "pending_id": body.pending_id,
        "caches_cleared": True,
        "sessions_refetched": sessions_bundle is not None,
        **outcome,
    }
    if sessions_bundle is not None:
        out["rolling_compliance_4w"] = sessions_bundle.get("rolling_compliance_4w")
        out["sessions_window"] = sessions_bundle.get("window")
        out["planned_count"] = len(sessions_bundle.get("planned") or [])
        out["completed_count"] = len(sessions_bundle.get("completed") or [])
        out["app_planned_merged"] = sessions_bundle.get("app_planned_merged")
    return out


@app.post("/v1/athlete/me/intervals/workouts/preview")
def workouts_preview(
    body: WorkoutPreviewIn,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Preview chat workouts → planned_sessions (+ optional Intervals).

    Always prepares SQLite planned_session rows (app SoT). Intervals events are
    included only when credentials exist and ``prepare_intervals_sync`` is true.
    Description-only WORKOUT on ICU (no ZWO attach via chat).
    Fail-closed against athlete constraints (disciplines / sessions_per_week / injury).
    """
    aid = _require_athlete(x_athlete_id)
    with db_session(config.get_db()) as conn:
        athlete = get_athlete(conn, aid)
        secrets = get_athlete_secrets(conn, aid)
        comps = completions_by_external_id(conn, aid)
        sessions_bundle = _sessions_bundle_for_athlete(
            conn, aid, secrets=secrets, comps=comps
        )
    if not athlete:
        raise HTTPException(404, "Utøver ikke funnet")
    key = ((secrets or {}).get("intervals_api_key") or "").strip()
    icu = ((secrets or {}).get("intervals_athlete_id") or "").strip()
    intervals_ok = bool(key and icu)
    want_icu = bool(body.prepare_intervals_sync) and intervals_ok

    replace_ids = [
        str(x).strip() for x in (body.replace_session_ids or []) if str(x).strip()
    ]
    with db_session(config.get_db()) as conn:
        planned_n = _count_planned_this_week_db(conn, aid)
    effective_existing = max(0, planned_n - len(replace_ids))
    gate = validate_workouts_against_constraints(
        athlete,
        body.workouts,
        existing_planned_this_week=effective_existing,
    )
    if not gate["accepted"]:
        # Cap-hit without replace → structured replace candidates (not bare 400 text).
        if gate.get("cap_hit") and not replace_ids:
            with db_session(config.get_db()) as conn:
                candidates = _replace_candidates_for_workouts(
                    conn, aid, body.workouts
                )
            raise HTTPException(
                400,
                detail={
                    "message": gate.get("ask")
                    or (
                        " ".join(gate["reasons"][:3])
                        if gate["reasons"]
                        else "Avtale blokkerer øktene."
                    ),
                    "cap_hit": True,
                    "replace_required": True,
                    "replace_candidates": candidates,
                    "reasons": gate.get("reasons") or [],
                },
            )
        raise HTTPException(
            400,
            gate.get("ask")
            or (
                " ".join(gate["reasons"][:3])
                if gate["reasons"]
                else "Avtale blokkerer øktene."
            ),
        )
    workouts_ok = gate["accepted"]
    try:
        events = build_workout_events(workouts_ok, athlete=athlete)
    except Exception as exc:  # noqa: BLE001
        from plan_workouts import format_exc_nb as _fmt

        raise HTTPException(
            500,
            f"Kunne ikke bygge Intervals-økt via CLI-bygger: {_fmt(exc)}",
        ) from exc
    if not events:
        raise HTTPException(
            400,
            "Ingen gyldige økter (trenger name + date YYYY-MM-DD)",
        )
    from plan_workouts import chat_workout_icu_description

    planned_rows: list[dict[str, Any]] = []
    for i, w in enumerate(workouts_ok):
        day = str(w.get("date") or "")[:10]
        name = str(w.get("name") or "").strip()
        if not day or not name:
            continue
        external = None
        if i < len(events):
            external = events[i].get("external_id")
        icu_desc = (
            str(events[i].get("description") or "").strip() if i < len(events) else ""
        )
        row_desc = icu_desc or chat_workout_icu_description(w)
        row: dict[str, Any] = {
            "session_date": day,
            "sport": str(w.get("sport") or "other").strip().lower() or "other",
            "name": name[:200],
            "description": row_desc[:4000],
            "duration_minutes": w.get("duration_minutes"),
            "start_time": str(w.get("start_time") or "07:00")[:5] or "07:00",
            "external_id": external,
            "source": "chat",
            "status": "planned",
            "planned_path": str(w.get("planned_path") or ""),
        }
        if w.get("steps"):
            row["steps"] = w["steps"]
        planned_rows.append(row)
    payload: dict[str, Any] = {
        "op": "workout_push",
        "persist_planned_sessions": True,
        "planned_sessions": planned_rows,
        "workouts": workouts_ok,
        "events": events if want_icu else [],
        "intervals_athlete_id": icu if want_icu else None,
        "constraint_filtered": not gate["ok"],
        "constraint_reasons": gate["reasons"],
        "prepare_intervals_sync": want_icu,
        "replace_session_ids": replace_ids,
    }
    summary = [public_event_preview(e) for e in (events if want_icu else events)]
    # Always show proposed sessions in preview (app plan), even without ICU
    session_preview = [
        {
            "session_date": r["session_date"],
            "name": r["name"],
            "sport": r["sport"],
            "duration_minutes": r.get("duration_minutes"),
            "external_id": r.get("external_id"),
        }
        for r in planned_rows
    ]
    with db_session(config.get_db()) as conn:
        pending = insert_pending_action(conn, aid, "intervals_workout_push", payload)
    msg_bits = [
        f"Bekreft for å lagre {len(planned_rows)} økt(er) i app-planen",
    ]
    if replace_ids:
        msg_bits.insert(
            0,
            f"Erstatter {len(replace_ids)} eksisterende økt(er)",
        )
    if want_icu:
        msg_bits.append(
            f"og synce {len(events)} til Intervals-kalenderen (beskrivelse, ingen ZWO)"
        )
    elif body.prepare_intervals_sync and not intervals_ok:
        msg_bits.append("(Intervals ikke koblet — kun lokal plan)")
    out: dict[str, Any] = {
        "pending_id": pending["id"],
        "op": "workout_push",
        "count": len(planned_rows),
        "planned_sessions_count": len(planned_rows),
        "intervals_event_count": len(events) if want_icu else 0,
        "expires_at": pending.get("expires_at"),
        "events": summary[:40] if want_icu else [],
        "sessions": session_preview[:40],
        "events_truncated": max(0, (len(events) if want_icu else 0) - 40),
        "confirm_required": True,
        "message": ". ".join(msg_bits) + ".",
        "persist_planned_sessions": True,
        "replace_session_ids": replace_ids,
        "write_gap": (
            None
            if want_icu
            else (
                "Strukturerte ZWO/CSV-økter pushes via Plan-sync / CLI; "
                "chat lagrer planned_sessions og kan legge description-WORKOUT på Intervals."
            )
        ),
        "constraints_summary_nb": gate.get("constraints_summary_nb"),
        "intervals_connected": intervals_ok,
        "prepare_intervals_sync": want_icu,
    }
    if gate["reasons"]:
        out["constraint_reasons"] = gate["reasons"]
        out["rejected"] = gate["rejected"]
    return out


@app.post("/v1/athlete/me/intervals/workouts/remove/preview")
def workouts_remove_preview(
    body: WorkoutRemovePreviewIn,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Preview delete of coach-scheduled Intervals workouts — confirm required.

    Only ``ll-coach-*`` / ``ll-coach-w-*`` external ids. Never wipes the calendar.
    """
    aid = _require_athlete(x_athlete_id)
    _athlete, key, icu = _require_intervals_secrets(aid)
    from datetime import timedelta

    today = date.today()
    oldest = (body.oldest or (today - timedelta(days=60)).isoformat())[:10]
    newest = (body.newest or (today + timedelta(days=120)).isoformat())[:10]
    try:
        existing = filter_coach_events(fetch_events(key, icu, oldest, newest))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)[:500]) from exc

    wanted_ids = {
        str(x).strip()
        for x in (body.external_ids or [])
        if str(x).strip().startswith("ll-coach-")
    }
    wanted_dates = {str(x).strip()[:10] for x in (body.dates or []) if str(x).strip()}
    wanted_names = {
        str(x).strip().lower() for x in (body.names or []) if str(x).strip()
    }

    matched: list[dict[str, Any]] = []
    for ev in existing:
        eid = str(ev.get("external_id") or "")
        if not eid.startswith("ll-coach-"):
            continue
        day = str(ev.get("start_date_local") or "")[:10]
        name = str(ev.get("name") or "").strip().lower()
        ok = False
        if wanted_ids and eid in wanted_ids:
            ok = True
        if wanted_dates and day in wanted_dates:
            ok = True
        if wanted_names and any(n in name for n in wanted_names):
            ok = True
        if not wanted_ids and not wanted_dates and not wanted_names:
            # Explicit empty filters → refuse (no silent mass delete from chat)
            continue
        if ok:
            matched.append(ev)

    external_ids = [e["external_id"] for e in matched if e.get("external_id")]
    if not external_ids:
        raise HTTPException(
            400,
            "Ingen matchende coach-økter (ll-coach-*) å fjerne i vinduet.",
        )
    payload = {
        "op": "delete",
        "external_ids": external_ids,
        "intervals_athlete_id": icu,
        "source": "chat_workout_removal",
    }
    with db_session(config.get_db()) as conn:
        pending = insert_pending_action(conn, aid, "intervals_calendar_delete", payload)
    return {
        "pending_id": pending["id"],
        "op": "delete",
        "count": len(external_ids),
        "expires_at": pending.get("expires_at"),
        "events": matched[:40],
        "events_truncated": max(0, len(matched) - 40),
        "confirm_required": True,
        "message": (
            f"Bekreft for å slette {len(external_ids)} coach-hendelse(r) "
            "(ll-coach-*) fra Intervals. Andre kalenderøkter urørt."
        ),
    }


@app.post("/v1/athlete/me/athlete-type")
def update_athlete_type(
    body: AthleteTypeUpdateIn,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Persist mutable hovedprofil after explicit confirm (chat/setup).

    Does not silently rewrite plan_blocks — returns optional plan preview when
    ``rebuild_plan_preview`` so the athlete can confirm a new periodization next.
    """
    aid = _require_athlete(x_athlete_id)
    new_type = normalize_athlete_type(body.athlete_type)
    if not new_type:
        raise HTTPException(422, f"Ugyldig athlete_type: {body.athlete_type}")
    with db_session(config.get_db()) as conn:
        athlete = get_athlete(conn, aid)
        if not athlete:
            raise HTTPException(404, "Utøver ikke funnet")
        old = athlete.get("athlete_type") or ""
        notes = append_type_history(
            athlete.get("athlete_type_notes"),
            old_type=old or None,
            new_type=new_type,
            reason=body.reason or "chat/confirm",
        )
        athlete = update_athlete(
            conn,
            aid,
            {
                "athlete_type": new_type,
                "athlete_type_notes": notes,
                "sport": SPORT_FOR_TYPE.get(new_type, athlete.get("sport") or "endurance"),
            },
        ) or athlete
    path = write_profile(config.ATHLETES_DATA_DIR, athlete)
    plan_preview = None
    if body.rebuild_plan_preview:
        draft = {
            "display_name": athlete.get("display_name") or "",
            "goal_text": athlete.get("goal_text") or "",
            "injury_notes": athlete.get("injury_notes") or "",
            "schedule_notes": athlete.get("schedule_notes") or "",
            "notes": athlete.get("notes") or "",
            "athlete_type": new_type,
            "sport": athlete.get("sport") or "",
            "weekly_hours_target": None,
            "season_start_date": athlete.get("season_start_date"),
            "goal_race_date": athlete.get("goal_race_date"),
        }
        plan_preview = build_setup_preview(
            draft,
            knowledge_dir=config.KNOWLEDGE_DIR,
            api_key="",
            enrich=False,
        )
    return {
        "athlete": athlete,
        "from": old or None,
        "to": new_type,
        "to_label": label_for(new_type),
        "profile_path": str(path.relative_to(config.REPO_ROOT))
        if path.is_relative_to(config.REPO_ROOT)
        else str(path),
        "plan_preview": {
            "athlete_type": plan_preview.get("athlete_type") if plan_preview else None,
            "athlete_archetype": plan_preview.get("athlete_archetype")
            if plan_preview
            else None,
            "season_targets": plan_preview.get("season_targets") if plan_preview else None,
            "plan_blocks": (plan_preview or {}).get("plan_blocks") or [],
            "overview_md": (plan_preview or {}).get("overview_md"),
            "confirm_hint": (
                "Ny type lagret. Bekreft ny grovplan via setup/Plan hvis du vil "
                "erstatte meso-blokkene (ikke auto-skrevet)."
            ),
        }
        if plan_preview
        else None,
        "message": (
            f"Hovedprofil oppdatert til «{label_for(new_type)}». "
            "Videre økter/plan følger den nye typen."
        ),
    }


def _athlete_draft_for_plan(athlete: dict[str, Any]) -> dict[str, Any]:
    """Build setup-preview draft from persisted Du-fields."""
    return {
        "display_name": athlete.get("display_name") or "",
        "goal_text": athlete.get("goal_text") or "",
        "injury_notes": athlete.get("injury_notes") or "",
        "schedule_notes": athlete.get("schedule_notes") or "",
        "notes": athlete.get("notes") or "",
        "fitness_notes": athlete.get("fitness_notes") or "",
        "weekly_focus": athlete.get("weekly_focus") or "",
        "athlete_type": athlete.get("athlete_type") or "",
        "sport": athlete.get("sport") or "",
        "sessions_per_week": athlete.get("sessions_per_week"),
        "allowed_disciplines": athlete.get("allowed_disciplines") or [],
        "agreements": athlete.get("agreements") or [],
        "season_start_date": athlete.get("season_start_date"),
        "goal_race_date": athlete.get("goal_race_date"),
        "ftp_tested": athlete.get("ftp_tested"),
        "weight_kg": athlete.get("weight_kg"),
        "age_years": athlete.get("age_years"),
        "nutrition_ibs": athlete.get("nutrition_ibs") or "no",
        "nutrition_gluten": athlete.get("nutrition_gluten") or "none",
        "nutrition_lactose": bool(athlete.get("nutrition_lactose")),
        "nutrition_notes": athlete.get("nutrition_notes") or "",
    }


@app.post("/v1/athlete/me/plan/adjust/preview")
def plan_adjust_preview(
    body: PlanAdjustPreviewIn,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Knowledge-grounded plan rebuild from current Du-profile — no silent write."""
    aid = _require_athlete(x_athlete_id)
    with db_session(config.get_db()) as conn:
        athlete = get_athlete(conn, aid)
        if not athlete:
            raise HTTPException(404, "Utøver ikke funnet")
        secrets = get_athlete_secrets(conn, aid)
    draft = _athlete_draft_for_plan(athlete)
    preview = build_setup_preview(
        draft,
        knowledge_dir=config.KNOWLEDGE_DIR,
        api_key=config.OPENAI_API_KEY or "" if body.enrich_with_llm else "",
        model=config.OPENAI_MODEL or "gpt-4o-mini",
        enrich=bool(body.enrich_with_llm),
    )
    # Persisted Du fields win over any LLM/rebuild noise in athlete_patch
    sync_athlete: dict[str, Any] = {
        **athlete,
        **(preview.get("athlete_patch") or {}),
        "id": aid,
        "athlete_type": preview.get("athlete_type") or athlete.get("athlete_type"),
    }
    for key in (
        "sessions_per_week",
        "allowed_disciplines",
        "goal_race_date",
        "season_start_date",
        "goal_text",
        "injury_notes",
        "fitness_notes",
        "schedule_notes",
    ):
        val = athlete.get(key)
        if val not in (None, "", []):
            sync_athlete[key] = val
    sync_prev = events_preview_for_plan_sync(
        preview["plan_blocks"],
        signals=preview.get("signals") or {},
        athlete=sync_athlete,
    )
    sync_prev["credentials_present"] = bool(
        ((secrets or {}).get("intervals_api_key") or "").strip()
        and ((secrets or {}).get("intervals_athlete_id") or "").strip()
    )
    preview["intervals_sync"] = sync_prev
    # Surface live constraints (not stale setup agreements text)
    if sync_prev.get("constraints_summary_nb"):
        preview["constraints_summary_nb"] = sync_prev["constraints_summary_nb"]
    if sync_prev.get("constraints"):
        preview["constraints"] = sync_prev["constraints"]
    if sync_athlete.get("sessions_per_week") is not None:
        preview["sessions_per_week"] = sync_athlete["sessions_per_week"]
    if sync_prev.get("prescription_rationale_nb"):
        preview["prescription_rationale_nb"] = sync_prev["prescription_rationale_nb"]

    horizon = persistable_plan_payload(
        preview["plan_blocks"], athlete=sync_athlete
    )
    preview["planned_sessions_count"] = horizon.get("count")
    preview["plan_horizon_weeks"] = horizon.get("weeks")
    preview["icu_sync_weeks"] = horizon.get("icu_sync_weeks")
    preview["horizon_note_nb"] = horizon.get("horizon_note_nb")
    preview["workout_horizon_note_nb"] = (
        f"App-plan: {horizon.get('count')} økter over {horizon.get('weeks')} uker "
        f"til måldato {sync_athlete.get('goal_race_date') or '—'}. "
        f"Intervals WORKOUT: kun første {horizon.get('icu_sync_weeks')} uker "
        "(avtalt økter/uke × sync-vindu). Grovplan-noter dekker sesong."
    )

    # Readiness → coach recommendations only (soft-fail)
    readiness: dict[str, Any]
    try:
        wl = resolve_wellness_bundle(secrets, days=7, include_body=False)
        recovery = wl.get("recovery_signals") or {"available": False}
        readiness = readiness_adjustment_hints(recovery)
    except Exception:  # noqa: BLE001
        readiness = readiness_adjustment_hints({"available": False})
    preview["readiness_hints"] = readiness
    if readiness.get("summary_nb"):
        preview["readiness_note_nb"] = readiness["summary_nb"]

    preview["seed_chat_prompt"] = (
        "Jeg har oppdatert profilen under Du (mål / skade / avtaler / notater / fokus). "
        f"Mål: {athlete.get('goal_text') or '—'}; "
        f"skade: {athlete.get('injury_notes') or 'ingen'}; "
        f"fokus: {athlete.get('weekly_focus') or '—'}; "
        f"økter/uke: {athlete.get('sessions_per_week') or '—'}; "
        f"avtaler: {', '.join(athlete.get('agreements') or []) or 'ingen'}. "
        f"Readiness: {readiness.get('summary_nb') or 'ingen data'}. "
        "Foreslå justering av grovplan og kommende økter ut fra knowledge — "
        "ikke synce Intervals før jeg bekrefter forhåndsvisning."
    )
    preview["confirm_hint"] = (
        "Forhåndsvisning klar. Bekreft for å erstatte meso-blokker + lagre "
        f"~{horizon.get('count')} økter til måldato lokalt. "
        "Intervals WORKOUT (nærvindu) skrives etter ekstra Sync-bekreftelse."
    )
    return preview


@app.post("/v1/athlete/me/plan/adjust/confirm")
def plan_adjust_confirm(
    body: PlanAdjustConfirmIn,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Replace plan_blocks + planned_sessions. Optional Intervals pending — never silent ICU write."""
    aid = _require_athlete(x_athlete_id)
    blocks = list(body.plan_blocks or [])
    if not blocks:
        raise HTTPException(422, "plan_blocks mangler — kjør forhåndsvis først.")
    patch = dict(body.athlete_patch or {})
    intervals_pending = None
    intervals_prep_error = None
    horizon_meta: dict[str, Any] = {}
    with db_session(config.get_db()) as conn:
        athlete = get_athlete(conn, aid)
        if not athlete:
            raise HTTPException(404, "Utøver ikke funnet")
        if patch:
            # Only apply known athlete fields; do not wipe with empty unless intentional
            apply = {
                k: v
                for k, v in patch.items()
                if v is not None
                and k
                in (
                    "goal_text",
                    "injury_notes",
                    "notes",
                    "weekly_focus",
                    "fitness_notes",
                    "schedule_notes",
                    "goal_race_date",
                    "season_start_date",
                    "sessions_per_week",
                    "allowed_disciplines",
                    "agreements",
                    "athlete_type",
                    "sport",
                    "season_swim_hours_target",
                    "season_bike_hours_target",
                    "season_run_hours_target",
                    "season_strength_hours_target",
                )
            }
            if apply:
                athlete = update_athlete(conn, aid, apply) or athlete
        saved_blocks = replace_plan_blocks(conn, aid, blocks)
        horizon_meta = _persist_plan_horizon_sessions(
            conn, aid, saved_blocks, athlete
        )
        if body.prepare_intervals_sync:
            secrets = get_athlete_secrets(conn, aid)
            key = ((secrets or {}).get("intervals_api_key") or "").strip()
            icu = ((secrets or {}).get("intervals_athlete_id") or "").strip()
            if key and icu and saved_blocks:
                try:
                    bundle = _sync_bundle_preferring_stored(
                        conn,
                        aid,
                        saved_blocks,
                        athlete,
                        allow_degraded=True,
                    )
                except Exception as exc:
                    intervals_prep_error = (
                        f"Plan lagret lokalt, men Intervals-forberedelse feilet: "
                        f"{format_exc_nb(exc)}"
                    )
                    bundle = None
                if bundle is not None and bundle.get("events"):
                    pending = insert_pending_action(
                        conn,
                        aid,
                        "intervals_calendar_push",
                        {
                            "op": "push",
                            "block_ids": [b["id"] for b in saved_blocks],
                            "events": bundle["events"],
                            "intervals_athlete_id": icu,
                            "notes_count": bundle["notes_count"],
                            "workouts_count": bundle["workouts_count"],
                            "zwo_count": bundle["zwo_count"],
                            "weeks": bundle["weeks"],
                            "builder": bundle["builder"],
                            "knowledge_paths": bundle["knowledge_paths"],
                            "from_stored_sessions": bundle.get(
                                "from_stored_sessions", False
                            ),
                        },
                    )
                    intervals_pending = {
                        "pending_id": pending["id"],
                        "op": "push",
                        "count": bundle["count"],
                        "notes_count": bundle["notes_count"],
                        "workouts_count": bundle["workouts_count"],
                        "confirm_required": True,
                        "from_stored_sessions": bundle.get(
                            "from_stored_sessions", False
                        ),
                        "message": (
                            "Plan justert lokalt (full horisont). "
                            "Bekreft Sync for nærvindu til Intervals "
                            "(fra lagrede planned_sessions)."
                        ),
                    }
    path = write_profile(config.ATHLETES_DATA_DIR, athlete)
    n_sess = int(horizon_meta.get("planned_sessions_count") or 0)
    return {
        "athlete": athlete,
        "plan_blocks": saved_blocks,
        "planned_sessions_count": n_sess,
        "plan_horizon_weeks": horizon_meta.get("plan_horizon_weeks"),
        "icu_sync_weeks": horizon_meta.get("icu_sync_weeks"),
        "horizon_note_nb": horizon_meta.get("horizon_note_nb"),
        "profile_path": str(path.relative_to(config.REPO_ROOT))
        if path.is_relative_to(config.REPO_ROOT)
        else str(path),
        "intervals_pending": intervals_pending,
        "intervals_prep_error": intervals_prep_error,
        "written_to_intervals": False,
        "message": (
            f"Grovplan + {n_sess} økter til måldato lagret lokalt. "
            "Intervals uendret til du bekrefter Sync."
        ),
    }


@app.get("/v1/athlete/me/planned-sessions")
def get_planned_sessions(
    x_athlete_id: str | None = Header(default=None),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=2000),
) -> dict[str, Any]:
    """First-class app plan sessions (SQLite) — full horizon, not ICU."""
    aid = _require_athlete(x_athlete_id)
    with db_session(config.get_db()) as conn:
        athlete = get_athlete(conn, aid)
        if not athlete:
            raise HTTPException(404, "Utøver ikke funnet")
        sessions = list_planned_sessions(
            conn, aid, start_date=start, end_date=end, limit=limit
        )
        total = count_planned_sessions(conn, aid)
        blocks = list_plan_blocks(conn, aid)
    return {
        "sessions": sessions,
        "count": len(sessions),
        "total": total,
        "plan_horizon_weeks": plan_horizon_weeks(blocks, athlete=athlete),
        "goal_race_date": athlete.get("goal_race_date"),
        "icu_sync_weeks": 2,
    }


@app.post("/v1/athlete/me/plan/week-adjust/preview")
def plan_week_adjust_preview(
    body: WeekAdjustPreviewIn,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Preview surgical rebuild of one week — does not write DB or ICU."""
    aid = _require_athlete(x_athlete_id)
    with db_session(config.get_db()) as conn:
        athlete = get_athlete(conn, aid)
        blocks = list_plan_blocks(conn, aid)
        if not athlete:
            raise HTTPException(404, "Utøver ikke funnet")
        if not blocks:
            raise HTTPException(400, "Ingen planblokker — kjør full plan først")
        existing = list_planned_sessions(conn, aid)
        secrets = get_athlete_secrets(conn, aid)
    built = build_week_adjust_sessions(
        blocks,
        athlete=athlete,
        week_start=body.week_start,
        ease_load=body.ease_load,
    )
    start_s = built["week_start"]
    end_s = built["week_end"]
    outside = [
        s
        for s in existing
        if not (start_s <= str(s.get("session_date") or "")[:10] <= end_s)
    ]
    readiness: dict[str, Any]
    try:
        wl = resolve_wellness_bundle(secrets, days=7, include_body=False)
        recovery = wl.get("recovery_signals") or {"available": False}
        readiness = readiness_adjustment_hints(recovery)
    except Exception:  # noqa: BLE001
        readiness = readiness_adjustment_hints({"available": False})
    return {
        "scope": "week",
        "week_start": start_s,
        "week_end": end_s,
        "ease_load": bool(body.ease_load),
        "sessions": built["sessions"],
        "count": built["count"],
        "unchanged_sessions_count": len(outside),
        "horizon_note_nb": built["horizon_note_nb"],
        "readiness_hints": readiness,
        "confirm_required": True,
        "confirm_hint": (
            f"Bekreft for å erstatte kun uka {start_s}–{end_s} "
            f"({built['count']} økter). Resten av planen ({len(outside)} økter) "
            "beholdes. Intervals uendret til Sync."
        ),
    }


@app.get("/v1/athlete/me/plan/roll/check")
def plan_roll_check(
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Dashboard/chat load: should we soft-offer next detalj window? Never auto-applies."""
    aid = _require_athlete(x_athlete_id)
    with db_session(config.get_db()) as conn:
        athlete = get_athlete(conn, aid)
        if not athlete:
            raise HTTPException(404, "Utøver ikke funnet")
        blocks = list_plan_blocks(conn, aid)
        sessions = list_planned_sessions(conn, aid)
        window = get_active_plan_window(conn, aid)
    ev = evaluate_roll_trigger(
        plan_window=window,
        planned_sessions=sessions,
        plan_blocks=blocks,
        athlete=athlete,
        message="",
        in_coach_chat=True,
    )
    return {
        **ev,
        "human_coach": True,
        "auto_apply": False,
        "hint_nb": (
            "Si «plan neste måned» eller «rull videre» for å få forhåndsvisningskort, "
            "eller vent til coach chatter når trigger treffer (med cooldown)."
            if not ev.get("should_offer")
            else "Klar for neste detaljvindu — åpne Coach for forslagskort (bekreft før lagring)."
        ),
    }


@app.post("/v1/athlete/me/plan/roll/confirm")
def plan_roll_confirm(
    body: PlanRollConfirmIn,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Confirm next detaljplan window → DB only. Intervals only via separate Sync."""
    aid = _require_athlete(x_athlete_id)
    start_s = (body.detalj_start or "")[:10]
    end_s = (body.detalj_end or "")[:10]
    sessions = list(body.sessions or [])
    if not start_s or not end_s:
        raise HTTPException(422, "detalj_start og detalj_end kreves")
    if not sessions:
        raise HTTPException(422, "sessions mangler — kjør forhåndsvis/roll-kort først")
    intervals_pending = None
    intervals_prep_error = None
    with db_session(config.get_db()) as conn:
        athlete = get_athlete(conn, aid)
        if not athlete:
            raise HTTPException(404, "Utøver ikke funnet")
        blocks = list_plan_blocks(conn, aid)
        result = replace_detalj_window(
            conn,
            aid,
            start_date=start_s,
            end_date=end_s,
            sessions=sessions,
            source="roll",
            readiness=body.readiness or {},
        )
        mark_detalj_roll_confirmed(conn, aid)
        total = count_planned_sessions(conn, aid)
        emit_sessions_saved(
            conn,
            aid,
            count=len(result["sessions"]),
            source="plan_roll",
            replace=True,
        )
        if body.prepare_intervals_sync:
            secrets = get_athlete_secrets(conn, aid)
            key = ((secrets or {}).get("intervals_api_key") or "").strip()
            icu = ((secrets or {}).get("intervals_athlete_id") or "").strip()
            if key and icu and blocks:
                try:
                    bundle = _sync_bundle_preferring_stored(
                        conn, aid, blocks, athlete, allow_degraded=True
                    )
                except Exception as exc:
                    intervals_prep_error = (
                        f"Detalj lagret lokalt, men Intervals-forberedelse feilet: "
                        f"{format_exc_nb(exc)}"
                    )
                    bundle = None
                if bundle is not None and bundle.get("events"):
                    pending = insert_pending_action(
                        conn,
                        aid,
                        "intervals_calendar_push",
                        {
                            "op": "push",
                            "events": bundle["events"],
                            "intervals_athlete_id": icu,
                            "notes_count": bundle["notes_count"],
                            "workouts_count": bundle["workouts_count"],
                            "weeks": bundle["weeks"],
                            "from_stored_sessions": True,
                            "source": "plan_roll",
                        },
                    )
                    intervals_pending = {
                        "pending_id": pending["id"],
                        "confirm_required": True,
                        "workouts_count": bundle["workouts_count"],
                        "weeks": bundle["weeks"],
                        "message": (
                            f"Bekreft Sync for nærvindu ({bundle['weeks']} uker) "
                            "til Intervals. Detaljplan er allerede lagret i appen."
                        ),
                    }
    return {
        "ok": True,
        "tier_model": "grov+detalj",
        "detalj_weeks": DETAIL_WEEKS,
        "detalj_start": start_s,
        "detalj_end": end_s,
        "planned_sessions_saved": len(result["sessions"]),
        "planned_sessions_count": total,
        "plan_window": result.get("window"),
        "written_to_intervals": False,
        "intervals_pending": intervals_pending,
        "intervals_prep_error": intervals_prep_error,
        "message": (
            f"Detaljplan lagret ({len(result['sessions'])} økter, "
            f"{start_s} → {end_s}). Grovplan uendret. "
            + (
                "Bekreft Sync for Intervals nærvindu."
                if intervals_pending
                else "Intervals urørt til du kjører Sync."
            )
        ),
    }


@app.post("/v1/athlete/me/plan/week-adjust/confirm")
def plan_week_adjust_confirm(
    body: WeekAdjustConfirmIn,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Replace one week of planned_sessions. Optional near-window ICU pending."""
    aid = _require_athlete(x_athlete_id)
    start_s = (body.week_start or "")[:10]
    end_s = (body.week_end or "")[:10]
    if not start_s or not end_s:
        raise HTTPException(422, "week_start og week_end kreves")
    sessions = list(body.sessions or [])
    if not sessions:
        raise HTTPException(422, "sessions mangler — kjør forhåndsvis først")
    intervals_pending = None
    intervals_prep_error = None
    with db_session(config.get_db()) as conn:
        athlete = get_athlete(conn, aid)
        if not athlete:
            raise HTTPException(404, "Utøver ikke funnet")
        blocks = list_plan_blocks(conn, aid)
        saved = replace_planned_sessions_range(
            conn, aid, start_s, end_s, sessions
        )
        total = count_planned_sessions(conn, aid)
        emit_sessions_saved(
            conn,
            aid,
            count=len(saved),
            source="week_adjust",
            replace=True,
        )
        if body.prepare_intervals_sync:
            secrets = get_athlete_secrets(conn, aid)
            key = ((secrets or {}).get("intervals_api_key") or "").strip()
            icu = ((secrets or {}).get("intervals_athlete_id") or "").strip()
            if key and icu and blocks:
                try:
                    bundle = _sync_bundle_preferring_stored(
                        conn, aid, blocks, athlete, allow_degraded=True
                    )
                except Exception as exc:
                    intervals_prep_error = (
                        f"Uke lagret lokalt, men Intervals-forberedelse feilet: "
                        f"{format_exc_nb(exc)}"
                    )
                    bundle = None
                if bundle is not None and bundle.get("events"):
                    pending = insert_pending_action(
                        conn,
                        aid,
                        "intervals_calendar_push",
                        {
                            "op": "push",
                            "block_ids": [b["id"] for b in blocks],
                            "events": bundle["events"],
                            "intervals_athlete_id": icu,
                            "notes_count": bundle["notes_count"],
                            "workouts_count": bundle["workouts_count"],
                            "zwo_count": bundle["zwo_count"],
                            "weeks": bundle["weeks"],
                            "builder": bundle["builder"],
                            "knowledge_paths": bundle["knowledge_paths"],
                            "from_stored_sessions": True,
                            "week_adjust": {
                                "week_start": start_s,
                                "week_end": end_s,
                            },
                        },
                    )
                    intervals_pending = {
                        "pending_id": pending["id"],
                        "op": "push",
                        "count": bundle["count"],
                        "workouts_count": bundle["workouts_count"],
                        "confirm_required": True,
                        "from_stored_sessions": True,
                        "message": (
                            f"Uke {start_s}–{end_s} lagret. "
                            "Bekreft Sync for nærvindu til Intervals."
                        ),
                    }
    return {
        "scope": "week",
        "week_start": start_s,
        "week_end": end_s,
        "sessions": saved,
        "replaced_count": len(saved),
        "planned_sessions_count": total,
        "ease_load": bool(body.ease_load),
        "intervals_pending": intervals_pending,
        "intervals_prep_error": intervals_prep_error,
        "written_to_intervals": False,
        "message": (
            f"Uke {start_s}–{end_s}: {len(saved)} økter lagret. "
            f"Full horisont nå {total} økter. Intervals uendret til Sync."
        ),
    }


@app.get("/v1/athlete/me/intervals/calendar/status")
def calendar_status(x_athlete_id: str | None = Header(default=None)) -> dict[str, Any]:
    """List coach-pushed calendar notes currently on Intervals."""
    aid = _require_athlete(x_athlete_id)
    _athlete, key, icu = _require_intervals_secrets(aid)
    with db_session(config.get_db()) as conn:
        blocks = list_plan_blocks(conn, aid)
    win_start, win_end = status_window_for_blocks(blocks)
    try:
        events = filter_coach_events(
            fetch_events(key, icu, win_start.isoformat(), win_end.isoformat())
        )
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)[:500]) from exc
    return {
        "window": {"start": win_start.isoformat(), "end": win_end.isoformat()},
        "count": len(events),
        "events": events,
        "external_prefix": "ll-coach-",
        "note": (
            "Teller både grovplan-NOTE (ll-coach-…) og WORKOUT (ll-coach-w-…). "
            "Andre Intervals-hendelser uten dette prefikset telles ikke."
        ),
    }


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


def _iso_week_bounds(today: date | None = None) -> tuple[date, date]:
    """Monday–Sunday of the ISO week containing ``today``."""
    day0 = today or date.today()
    start = day0 - timedelta(days=day0.weekday())
    end = start + timedelta(days=6)
    return start, end


def _count_planned_this_week_db(
    conn: Any,
    athlete_id: str,
    *,
    today: date | None = None,
) -> int:
    """Count planned_sessions rows in the current ISO week (authoritative)."""
    start, end = _iso_week_bounds(today)
    rows = list_planned_sessions(
        conn,
        athlete_id,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
    )
    return len(rows)


def _replace_candidates_for_workouts(
    conn: Any,
    athlete_id: str,
    workouts: list[dict[str, Any]] | None,
    *,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Existing planned rows this ISO week — same-date first for replace offer."""
    start, end = _iso_week_bounds(today)
    rows = list_planned_sessions(
        conn,
        athlete_id,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
    )
    proposed_dates = {
        str(w.get("date") or w.get("session_date") or "")[:10]
        for w in (workouts or [])
        if isinstance(w, dict)
    }
    proposed_dates.discard("")
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for r in rows:
        day = str(r.get("session_date") or "")[:10]
        score = 0 if day in proposed_dates else 1
        scored.append((score, day, r))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [
        {
            "id": r.get("id"),
            "session_date": r.get("session_date"),
            "name": r.get("name"),
            "sport": r.get("sport"),
            "duration_minutes": r.get("duration_minutes"),
            "same_date": str(r.get("session_date") or "")[:10] in proposed_dates,
        }
        for _, _, r in scored
        if r.get("id")
    ]


def _attach_cap_replace_offer(
    out: dict[str, Any],
    *,
    aid: str,
    proposal: dict[str, Any],
    gate: dict[str, Any],
    reply: str | None = None,
) -> dict[str, Any]:
    """When weekly cap blocks add — offer replace candidates instead of dead-end."""
    workouts = list(proposal.get("workouts") or [])
    with db_session(config.get_db()) as conn:
        candidates = _replace_candidates_for_workouts(conn, aid, workouts)
        emit_weekly_cap_replace(conn, aid, candidates=len(candidates))
    # Prefer auto-select same-date candidates (1:1 with proposed count)
    auto_ids = [
        c["id"]
        for c in candidates
        if c.get("same_date")
    ][: max(1, len(workouts))]
    if not auto_ids and candidates:
        auto_ids = [candidates[0]["id"]]
    out["workout_proposal"] = {
        **proposal,
        "workouts": workouts,
        "replace_required": True,
        "replace_candidates": candidates,
        "replace_session_ids": auto_ids,
    }
    out["workout_replace_proposal"] = {
        "workouts": workouts,
        "replace_candidates": candidates,
        "replace_session_ids": auto_ids,
        "cap_hit": True,
        "reasons": gate.get("reasons") or [],
        "ask": gate.get("ask"),
        "confirm_required": True,
        "message": (
            "Avtalt økter/uke er fylt. Velg eksisterende økt(er) å erstatte "
            "— deretter forhåndsvis → bekreft. Ingen stille lagring."
        ),
    }
    out["workout_proposal_blocked"] = False
    out["confirm_required"] = True
    out["constraint_reasons"] = gate.get("reasons")
    out["constraint_ask"] = gate.get("ask")
    out["proposal_hint"] = out["workout_replace_proposal"]["message"]
    if candidates:
        extra = (
            "\n\n⚠️ Avtale-sperre (full uke): tilbyr erstatning av eksisterende økt(er) "
            "på de datoene — velg i kortet, deretter forhåndsvis → bekreft."
        )
        base = (out.get("reply") or reply or "").rstrip()
        if "erstatning" not in base.lower():
            out["reply"] = (base + extra).strip()
    else:
        out["workout_proposal_blocked"] = True
        out["workout_proposal"] = None
        out["proposal_hint"] = (
            gate.get("ask")
            or "Avtalt økter/uke er fylt og det finnes ingen økter å erstatte denne uka."
        )
    return out


def _count_planned_this_week(sessions_bundle: dict[str, Any] | None) -> int:
    """Count planned WORKOUT events in the current ISO week (for session caps).

    Dedupes across planned/upcoming/today buckets (they overlap after merge).
    Prefer ``_count_planned_this_week_db`` when a DB connection is available.
    """
    if not sessions_bundle:
        return 0
    today = date.today()
    iso = today.isocalendar()
    seen: set[str] = set()
    n = 0
    for bucket in ("planned", "upcoming", "today"):
        for s in sessions_bundle.get(bucket) or []:
            if s.get("calendar_role") == "note" or s.get("training_status") == "note":
                continue
            if s.get("kind") == "activity":
                continue
            d_raw = s.get("date")
            if not d_raw:
                continue
            try:
                d = date.fromisoformat(str(d_raw)[:10])
            except ValueError:
                continue
            if d.isocalendar()[:2] != iso[:2]:
                continue
            key = (
                str(s.get("planned_row_id") or "").strip()
                or str(s.get("external_id") or "").strip()
                or str(s.get("id") or "").strip()
                or f"{d.isoformat()}:{s.get('name') or ''}"
            )
            if key in seen:
                continue
            seen.add(key)
            n += 1
    return n


def _overview_payload(
    athlete: dict[str, Any],
    secrets: dict[str, Any] | None = None,
    blocks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Form estimates + progress/compliance + plan strip."""
    estimates = resolve_form_estimates(athlete, secrets)
    # Persist only when gate opens with a fresh estimate (don't wipe on thin fetch)
    if (
        estimates.get("fetch_source") == "intervals"
        and estimates.get("gate_open")
        and estimates.get("ftp_estimated") is not None
    ):
        patch = {
            "ftp_estimated": estimates.get("ftp_estimated"),
            "vo2_estimate": estimates.get("vo2_estimate"),
            "estimate_confidence": estimates.get("estimate_confidence"),
            "estimate_source": estimates.get("estimate_source") or "intervals",
            "estimate_updated_at": utc_now(),
        }
        aid = athlete.get("id")
        if aid:
            try:
                with db_session(config.get_db()) as conn:
                    updated = update_athlete(conn, aid, patch)
                    if updated:
                        athlete = updated
            except Exception:
                pass

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

    ftp_est = athlete.get("ftp_estimated")
    if ftp_est is None:
        ftp_est = estimates.get("ftp_estimated")
    vo2 = athlete.get("vo2_estimate")
    if vo2 is None:
        vo2 = estimates.get("vo2_estimate")
    confidence = athlete.get("estimate_confidence") or estimates.get(
        "estimate_confidence"
    )

    return {
        "plan_headline": (picked["current"] or {}).get("title") if picked.get("current") else None,
        "last_session": None,
        "load": None,
        "intervals_linked": intervals_linked,
        "intervals_hint": intervals_hint,
        "intervals_athlete_id": linked.get("intervals_athlete_id"),
        "ftp_tested": athlete.get("ftp_tested"),
        "ftp_tested_at": athlete.get("ftp_tested_at"),
        "ftp_estimated": ftp_est,
        "vo2_estimate": vo2,
        "estimate_confidence": confidence,
        "estimate_disclaimer": estimates.get("disclaimer"),
        "estimate_source": estimates.get("fetch_source") or athlete.get("estimate_source"),
        "gate_open": estimates.get("gate_open"),
        "qualifying_sessions": estimates.get("qualifying_sessions"),
        "required_sessions": estimates.get("required_sessions"),
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

