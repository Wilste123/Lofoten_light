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
    completions_by_external_id,
    db_session,
    delete_plan_block,
    get_athlete,
    get_athlete_secrets,
    get_pending_action,
    init_db,
    insert_athlete,
    insert_pending_action,
    insert_plan_block,
    invite_token_valid,
    list_plan_blocks,
    list_session_completions,
    mark_pending_action,
    recent_messages,
    secrets_public_view,
    update_athlete,
    update_plan_block,
    upsert_athlete_secrets,
    upsert_session_completion,
    utc_now,
)
from form_from_intervals import clear_form_caches, persist_estimates_patch, resolve_form_estimates
from intervals_calendar import (
    build_block_note_events,
    delete_events_bulk,
    fetch_events,
    filter_coach_events,
    post_events_bulk,
    public_event_preview,
    select_blocks,
    status_window_for_blocks,
)
from intervals_smoke import smoke_test_intervals
from profile import write_profile
from progress_compliance import (
    days_to_goal,
    pick_current_and_next,
    public_block,
    resolve_progress,
)
from sessions_service import (
    completion_note_line,
    list_sessions,
    seed_chat_prompt,
)
from wellness import resolve_wellness_bundle


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


class LoginIn(BaseModel):
    athlete_id: str = Field(min_length=1)
    invite_token: str | None = None


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
    show_body_metrics: bool | None = None


class ChatIn(BaseModel):
    message: str = Field(min_length=1)


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


class CalendarConfirmIn(BaseModel):
    pending_id: str = Field(min_length=1)


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


@app.post("/v1/session/login")
def session_login(body: LoginIn) -> dict[str, Any]:
    """Reconnect to an existing athlete. Never creates a new profile."""
    aid = body.athlete_id.strip()
    if not aid:
        raise HTTPException(404, "Ukjent profil-ID. Sjekk at ID er riktig, eller opprett ny bruker.")
    token = (body.invite_token or "").strip() or None
    with db_session(config.DATABASE_PATH) as conn:
        athlete = get_athlete(conn, aid)
        if not athlete:
            raise HTTPException(
                404,
                "Ukjent profil-ID. Sjekk at ID er riktig, eller opprett ny bruker.",
            )
        if token is not None and not invite_token_valid(conn, token):
            raise HTTPException(401, "Ugyldig invite-token.")
    return {"athlete": athlete, "needs_onboarding": False}


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


@app.get("/v1/dashboard")
def dashboard(x_athlete_id: str | None = Header(default=None)) -> dict[str, Any]:
    """Hours/load + sleep + optional body metrics + app-computed compliance.

    Compliance is never written to Intervals — only computed here from
    activities vs season targets (same as /v1/overview progress).
    """
    aid = _require_athlete(x_athlete_id)
    with db_session(config.DATABASE_PATH) as conn:
        athlete = get_athlete(conn, aid)
        if not athlete:
            raise HTTPException(404, "Utøver ikke funnet")
        secrets = get_athlete_secrets(conn, aid)
        blocks = list_plan_blocks(conn, aid)
    overview_data = _overview_payload(athlete, secrets, blocks)
    show_body = bool(athlete.get("show_body_metrics", True))
    wellness = resolve_wellness_bundle(secrets, days=14, include_body=show_body)
    progress = overview_data.get("progress") or {}
    hours = {
        "disciplines": progress.get("disciplines") or [],
        "window": progress.get("window"),
        "source": progress.get("source"),
        "activity_count": progress.get("activity_count"),
        "fetch_error": progress.get("fetch_error"),
        "formula": progress.get("formula"),
    }
    load = {
        "from_wellness": wellness.get("load_wellness"),
        "hours_summary": hours,
        "note": (
            "Belastning/timer er app-beregnet fra Intervals-aktiviteter. "
            "Compliance lagres ikke i Intervals."
        ),
    }
    return {
        "show_body_metrics": show_body,
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
    with db_session(config.DATABASE_PATH) as conn:
        if not get_athlete(conn, aid):
            raise HTTPException(404, "Utøver ikke funnet")
        rows = list_session_completions(conn, aid, limit=50)
    return {"completions": rows}


@app.get("/v1/sessions")
def get_sessions(x_athlete_id: str | None = Header(default=None)) -> dict[str, Any]:
    """Recent + upcoming Intervals sessions; soft-fail without credentials."""
    aid = _require_athlete(x_athlete_id)
    with db_session(config.DATABASE_PATH) as conn:
        if not get_athlete(conn, aid):
            raise HTTPException(404, "Utøver ikke funnet")
        secrets = get_athlete_secrets(conn, aid)
        comps = completions_by_external_id(conn, aid)
    return list_sessions(secrets, comps)


@app.get("/v1/sessions/{session_id}")
def get_session_detail(
    session_id: str,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Find one session in the list window + seed prompt for Coach chat."""
    aid = _require_athlete(x_athlete_id)
    with db_session(config.DATABASE_PATH) as conn:
        if not get_athlete(conn, aid):
            raise HTTPException(404, "Utøver ikke funnet")
        secrets = get_athlete_secrets(conn, aid)
        comps = completions_by_external_id(conn, aid)
    payload = list_sessions(secrets, comps)
    sid = session_id.strip()
    found = None
    for bucket in ("today", "upcoming", "recent"):
        for s in payload.get(bucket) or []:
            if s.get("id") == sid or s.get("external_id") == sid:
                found = s
                break
        if found:
            break
    if not found:
        found = {
            "id": sid,
            "external_id": sid.split(":", 1)[-1] if ":" in sid else sid,
            "kind": "unknown",
            "name": "Økt",
            "date": None,
            "completion": comps.get(sid)
            or comps.get(sid.split(":", 1)[-1] if ":" in sid else sid),
        }
    return {
        "session": found,
        "seed_prompt": seed_chat_prompt(found),
        "compliance_note": payload.get("compliance_note"),
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
        with db_session(config.DATABASE_PATH) as conn:
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


def _require_intervals_secrets(aid: str) -> tuple[dict[str, Any], str, str]:
    with db_session(config.DATABASE_PATH) as conn:
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
    with db_session(config.DATABASE_PATH) as conn:
        athlete = get_athlete(conn, aid)
        secrets = get_athlete_secrets(conn, aid)
        if not athlete:
            raise HTTPException(404, "Utøver ikke funnet")
    clear_form_caches()
    estimates = resolve_form_estimates(athlete, secrets, use_cache=False)
    patch = persist_estimates_patch(estimates)
    if patch:
        with db_session(config.DATABASE_PATH) as conn:
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
    with db_session(config.DATABASE_PATH) as conn:
        blocks = list_plan_blocks(conn, aid)
    selected = select_blocks(
        blocks, block_ids=body.block_ids, start=body.start, end=body.end
    )
    if not selected:
        raise HTTPException(400, "Ingen planblokker i utvalget")

    if op == "push":
        events = build_block_note_events(selected)
        if not events:
            raise HTTPException(400, "Blokkene mangler start/slutt-dato")
        payload = {
            "op": "push",
            "block_ids": [b["id"] for b in selected],
            "events": events,
            "intervals_athlete_id": icu,
        }
        summary = [public_event_preview(e) for e in events]
        count = len(events)
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
            raise HTTPException(400, "Ingen agent-noter å fjerne i utvalget")
        payload = {
            "op": "delete",
            "block_ids": [b["id"] for b in selected],
            "external_ids": external_ids,
            "intervals_athlete_id": icu,
        }
        summary = [{"external_id": eid} for eid in external_ids]
        count = len(external_ids)

    with db_session(config.DATABASE_PATH) as conn:
        pending = insert_pending_action(conn, aid, f"intervals_calendar_{op}", payload)
    return {
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
        "message": (
            f"Bekreft for å {'synce' if op == 'push' else 'fjerne'} "
            f"{count} Intervals-hendelser."
        ),
    }


@app.post("/v1/athlete/me/intervals/calendar/confirm")
def calendar_confirm(
    body: CalendarConfirmIn,
    x_athlete_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Execute a previously previewed push/delete against Intervals."""
    aid = _require_athlete(x_athlete_id)
    _athlete, key, icu = _require_intervals_secrets(aid)
    with db_session(config.DATABASE_PATH) as conn:
        pending = get_pending_action(conn, aid, body.pending_id)
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
                with db_session(config.DATABASE_PATH) as conn:
                    mark_pending_action(conn, aid, body.pending_id, "expired")
                raise HTTPException(400, "Forhåndsvisning utløpt — lag ny")
        except ValueError:
            pass

    payload = pending.get("payload") or {}
    op = payload.get("op")
    try:
        if op == "push":
            events = payload.get("events") or []
            result = post_events_bulk(key, icu, events, upsert=True)
            outcome = {"pushed": result.get("count", len(events)), "result": result}
        elif op == "delete":
            ids = payload.get("external_ids") or []
            result = delete_events_bulk(key, icu, ids)
            deleted = result.get("eventsDeleted", len(ids))
            outcome = {"deleted": deleted, "result": result}
        else:
            raise HTTPException(400, "Ugyldig pending op")
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)[:500]) from exc

    with db_session(config.DATABASE_PATH) as conn:
        mark_pending_action(conn, aid, body.pending_id, "confirmed")
    return {"ok": True, "op": op, "pending_id": body.pending_id, **outcome}


@app.get("/v1/athlete/me/intervals/calendar/status")
def calendar_status(x_athlete_id: str | None = Header(default=None)) -> dict[str, Any]:
    """List coach-pushed calendar notes currently on Intervals."""
    aid = _require_athlete(x_athlete_id)
    _athlete, key, icu = _require_intervals_secrets(aid)
    with db_session(config.DATABASE_PATH) as conn:
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
                with db_session(config.DATABASE_PATH) as conn:
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

