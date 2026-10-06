"""Two-tier plan model: grovplan (meso → goal) + detaljplan (~4 weeks rolling).

Grovplan lives in ``plan_blocks`` (themes, hours band, session-type mix).
Detaljplan lives in ``planned_sessions`` for an active ``plan_windows`` row.
Intervals sync only from the detalj/near window — never silent year rewrite.

Roll-forward (Human Coach only — proposal → confirm → save → sync):
  DETAIL_WEEKS / ROLL_TRIGGER_* / ROLL_COOLDOWN_DAYS — see evaluate_roll_trigger.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from athlete_constraints import (
    ICU_SYNC_WEEKS,
    MAX_PLAN_HORIZON_WEEKS,
    normalize_disciplines,
    normalize_sessions_per_week,
    resolve_constraints,
)
from plan_workouts import (
    build_planned_session_dicts,
    plan_horizon_weeks,
    parse_iso_date,
)

# --- Roll-forward / detalj constants (tunable; keep names stable) ---
DETAIL_WEEKS = 4
DETALJ_PLAN_WEEKS = DETAIL_WEEKS  # alias
# Soft-offer when ≤21d left of detalj (4w window ≈ mid-window; was 14 → rarely fired)
ROLL_TRIGGER_DAYS_LEFT = 21
ROLL_TRIGGER_BLOCK_ELAPSED_DAYS = 14
ROLL_COOLDOWN_DAYS = 5

SESSION_TYPES = ("easy", "quality", "long", "strength", "recovery")

_EXPLICIT_ROLL_RE = re.compile(
    r"(?i)"
    r"(?:neste\s+måned|neste\s+maaned|neste\s+4\s*uker|neste\s+detalj|"
    r"rull\s+(?:videre|planen|detalj)|rull\s+frem|"
    r"plan(?:legg)?\s+neste\s+(?:måned|maaned|uke|periode)|"
    r"juster\s+fremover|fremover\s+plan|"
    r"roll\s+(?:forward|next)|next\s+(?:month|block|detail))"
)


def default_session_type_mix(
    *,
    sessions_per_week: int | None,
    disciplines: list[str] | None = None,
) -> dict[str, int]:
    """Typical weekly session-type counts for a grovplan block."""
    spw = normalize_sessions_per_week(sessions_per_week) or 4
    discs = normalize_disciplines(disciplines) or ["run"]
    has_strength = "strength" in discs
    strength_n = 1 if has_strength and spw >= 3 else 0
    remaining = max(0, spw - strength_n)
    if remaining <= 1:
        easy, quality, long_ = remaining, 0, 0
    elif remaining == 2:
        easy, quality, long_ = 1, 1, 0
    elif remaining == 3:
        easy, quality, long_ = 1, 1, 1
    else:
        long_ = 1
        quality = 1
        easy = remaining - long_ - quality
    return {
        "easy": max(0, easy),
        "quality": max(0, quality),
        "long": max(0, long_),
        "strength": strength_n,
        "recovery": 0,
    }


def infer_session_type(session: dict[str, Any]) -> str:
    """Best-effort type tag for a concrete planned session."""
    sport = str(session.get("sport") or "").lower()
    name = str(session.get("name") or "").lower()
    desc = str(session.get("description") or "").lower()
    blob = f"{name} {desc}"
    if sport in ("strength", "weighttraining") or "styrke" in blob:
        return "strength"
    if any(k in blob for k in ("interv", "terske", "quality", "vo2", "tempo", "hard")):
        return "quality"
    if any(k in blob for k in ("langtur", "long", "lengre", "utholdenhet lang")):
        return "long"
    if any(k in blob for k in ("restit", "recovery", "lett restit")):
        return "recovery"
    return "easy"


def enrich_grov_blocks(
    blocks: list[dict[str, Any]],
    *,
    athlete: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Ensure each meso block is first-class grovplan (layer, hours band, mix)."""
    cons = resolve_constraints(athlete or {})
    spw = cons.get("sessions_per_week")
    discs = cons.get("disciplines") or []
    mix = default_session_type_mix(sessions_per_week=spw, disciplines=discs)
    out: list[dict[str, Any]] = []
    for b in blocks:
        row = dict(b)
        wh = row.get("weekly_hours")
        try:
            wh_f = float(wh) if wh is not None and str(wh).strip() != "" else None
        except (TypeError, ValueError):
            wh_f = None
        if wh_f is not None:
            row.setdefault("hours_min", round(wh_f * 0.85, 1))
            row.setdefault("hours_max", round(wh_f * 1.15, 1))
        raw_mix = row.get("session_types") or row.get("session_types_json")
        if isinstance(raw_mix, str) and raw_mix.strip():
            try:
                parsed = json.loads(raw_mix)
                if isinstance(parsed, dict) and parsed:
                    row["session_types"] = {
                        k: int(parsed.get(k) or 0) for k in SESSION_TYPES
                    }
                else:
                    row["session_types"] = dict(mix)
            except json.JSONDecodeError:
                row["session_types"] = dict(mix)
        elif isinstance(raw_mix, dict) and raw_mix:
            row["session_types"] = {
                k: int(raw_mix.get(k) or 0) for k in SESSION_TYPES
            }
        else:
            row["session_types"] = dict(mix)
        row["layer"] = str(row.get("layer") or "grov")
        out.append(row)
    return out


def detalj_weeks_for_athlete(athlete: dict[str, Any] | None = None) -> int:
    """Detaljplan length in weeks (~1 month). Caps at remaining weeks to goal."""
    today = date.today()
    remaining = plan_horizon_weeks(athlete=athlete, today=today)
    return max(1, min(DETAIL_WEEKS, remaining))


def build_two_tier_plan_payload(
    blocks: list[dict[str, Any]],
    *,
    athlete: dict[str, Any] | None = None,
    signals: dict[str, bool] | None = None,
    today: date | None = None,
    detalj_weeks: int | None = None,
    detalj_start: date | None = None,
    readiness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Grovplan meta (to goal) + detaljplan concrete sessions (~1 month)."""
    today = today or date.today()
    grov_blocks = enrich_grov_blocks(blocks, athlete=athlete)
    grov_weeks = plan_horizon_weeks(grov_blocks, athlete=athlete, today=today)
    d_weeks = (
        detalj_weeks
        if detalj_weeks is not None
        else min(DETAIL_WEEKS, max(1, grov_weeks))
    )
    d_weeks = max(1, min(int(d_weeks), MAX_PLAN_HORIZON_WEEKS))
    start = detalj_start or today
    built = build_planned_session_dicts(
        grov_blocks,
        athlete=athlete,
        signals=signals,
        today=start,
        weeks=d_weeks,
    )
    sessions: list[dict[str, Any]] = []
    for s in built.get("sessions") or []:
        row = dict(s)
        row["plan_tier"] = "detalj"
        row["session_type"] = infer_session_type(row)
        row["source"] = row.get("source") or "detalj"
        sessions.append(row)
    plan_start = parse_iso_date(built.get("plan_start")) or start
    end = plan_start + timedelta(days=7 * d_weeks - 1)
    return {
        "grov_blocks": grov_blocks,
        "grov_horizon_weeks": grov_weeks,
        "detalj_weeks": d_weeks,
        "detalj_start": plan_start.isoformat(),
        "detalj_end": end.isoformat(),
        "sessions": sessions,
        "count": len(sessions),
        "weeks": d_weeks,
        "plan_start": plan_start.isoformat(),
        "goal_race_date": (athlete or {}).get("goal_race_date"),
        "icu_sync_weeks": ICU_SYNC_WEEKS,
        "readiness": readiness or {},
        "horizon_note_nb": (
            f"Grovplan: {len(grov_blocks)} meso-blokker (~{grov_weeks} uker til måldato). "
            f"Detaljplan: {len(sessions)} konkrete økter over {d_weeks} uker "
            f"({plan_start.isoformat()} → {end.isoformat()}). "
            f"Intervals WORKOUT-sync: nærvindu {ICU_SYNC_WEEKS} uker fra detaljplan "
            f"(preview → confirm). Ingen stille årsomskriving."
        ),
        "tier_model": "grov+detalj",
    }


def readiness_from_signals(
    *,
    ctl: float | None = None,
    atl: float | None = None,
    sleep_hours_avg: float | None = None,
    hrv_trend: str | None = None,
    recent_activities_count: int | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Snapshot used when proposing the next rolling detalj window."""
    return {
        "ctl": ctl,
        "atl": atl,
        "sleep_hours_avg": sleep_hours_avg,
        "hrv_trend": hrv_trend,
        "recent_activities_count": recent_activities_count,
        "notes": notes or "",
    }


def readiness_from_overview(overview: dict[str, Any] | None) -> dict[str, Any]:
    """Pull soft readiness hints from chat overview / wellness_signals."""
    ov = overview or {}
    wl = ov.get("wellness_signals") or {}
    sleep = wl.get("sleep") if isinstance(wl.get("sleep"), dict) else {}
    load = wl.get("load") if isinstance(wl.get("load"), dict) else {}
    form = ov.get("form") or ov.get("fitness") or {}
    ctl = load.get("ctl") or form.get("ctl")
    atl = load.get("atl") or form.get("atl")
    try:
        ctl_f = float(ctl) if ctl is not None else None
    except (TypeError, ValueError):
        ctl_f = None
    try:
        atl_f = float(atl) if atl is not None else None
    except (TypeError, ValueError):
        atl_f = None
    sleep_avg = sleep.get("avg_hours") or sleep.get("hours_avg")
    try:
        sleep_f = float(sleep_avg) if sleep_avg is not None else None
    except (TypeError, ValueError):
        sleep_f = None
    return readiness_from_signals(
        ctl=ctl_f,
        atl=atl_f,
        sleep_hours_avg=sleep_f,
        hrv_trend=str(sleep.get("hrv_trend") or wl.get("hrv_trend") or "") or None,
        recent_activities_count=(ov.get("sessions") or {}).get("completed_count"),
        notes=str(wl.get("note") or ""),
    )


def next_detalj_start_after(
    window_end: str | date | None, *, today: date | None = None
) -> date:
    """Monday on or after day following previous detalj end (or today)."""
    today = today or date.today()
    if window_end is None:
        base = today
    elif isinstance(window_end, date):
        base = window_end + timedelta(days=1)
    else:
        parsed = parse_iso_date(str(window_end)[:10])
        base = (parsed + timedelta(days=1)) if parsed else today
    if base < today:
        base = today
    return base if base.weekday() == 0 else base + timedelta(days=(7 - base.weekday()) % 7)


def user_requests_explicit_roll(message: str) -> bool:
    """«neste måned / rull videre» — bypasses cooldown."""
    return bool(_EXPLICIT_ROLL_RE.search(message or ""))


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _days_since(ts: datetime | None, *, now: datetime | None = None) -> float | None:
    if ts is None:
        return None
    now = now or datetime.now(timezone.utc)
    return (now - ts).total_seconds() / 86400.0


def current_grov_block(
    blocks: list[dict[str, Any]], *, today: date | None = None
) -> dict[str, Any] | None:
    today = today or date.today()
    for b in blocks or []:
        s = parse_iso_date(b.get("start_date"))
        e = parse_iso_date(b.get("end_date"))
        if s and e and s <= today <= e:
            return b
        if s and not e and s <= today:
            return b
    return None


def detalj_covers_through(
    planned_sessions: list[dict[str, Any]],
    target: date,
) -> bool:
    """True if any planned_session date is on or after target."""
    for s in planned_sessions or []:
        d = parse_iso_date(str(s.get("session_date") or "")[:10])
        if d and d >= target:
            return True
    return False


def active_detalj_bounds(
    *,
    plan_window: dict[str, Any] | None = None,
    planned_sessions: list[dict[str, Any]] | None = None,
) -> tuple[date | None, date | None]:
    """Resolve current detalj start/end from window row or session dates."""
    if plan_window:
        s = parse_iso_date(plan_window.get("start_date"))
        e = parse_iso_date(plan_window.get("end_date"))
        if s or e:
            return s, e
    sessions = planned_sessions or []
    dates: list[date] = []
    for s in sessions:
        d = parse_iso_date(str(s.get("session_date") or "")[:10])
        if d:
            dates.append(d)
    if not dates:
        return None, None
    return min(dates), max(dates)


def evaluate_roll_trigger(
    *,
    today: date | None = None,
    plan_window: dict[str, Any] | None = None,
    planned_sessions: list[dict[str, Any]] | None = None,
    plan_blocks: list[dict[str, Any]] | None = None,
    athlete: dict[str, Any] | None = None,
    message: str = "",
    in_coach_chat: bool = True,
) -> dict[str, Any]:
    """Decide whether to offer next ~4w detalj proposal (never auto-apply).

    Returns dict with ``should_offer``, ``reason``, ``bypass_cooldown``, etc.
    """
    today = today or date.today()
    explicit = user_requests_explicit_roll(message)
    detalj_start, detalj_end = active_detalj_bounds(
        plan_window=plan_window, planned_sessions=planned_sessions
    )
    block = current_grov_block(plan_blocks or [], today=today)
    reasons: list[str] = []
    trigger: str | None = None

    if explicit:
        trigger = "explicit"
        reasons.append("Utøver ba eksplisitt om neste detaljvindu / rull.")
    else:
        if detalj_end is not None:
            days_left = (detalj_end - today).days
            if days_left <= ROLL_TRIGGER_DAYS_LEFT:
                trigger = "days_left"
                reasons.append(
                    f"≤{ROLL_TRIGGER_DAYS_LEFT} dager igjen av detaljplan "
                    f"(slutt {detalj_end.isoformat()}, {days_left} d igjen)."
                )
        if trigger is None and in_coach_chat and block:
            b_start = parse_iso_date(block.get("start_date"))
            if b_start is not None:
                elapsed = (today - b_start).days
                cover_target = b_start + timedelta(days=28)
                if elapsed >= ROLL_TRIGGER_BLOCK_ELAPSED_DAYS and not detalj_covers_through(
                    planned_sessions or [], cover_target
                ):
                    trigger = "block_elapsed"
                    reasons.append(
                        f"≥{ROLL_TRIGGER_BLOCK_ELAPSED_DAYS} dager inn i meso-blokk "
                        f"«{block.get('title') or block.get('id')}» uten detalj "
                        f"som dekker til {cover_target.isoformat()}."
                    )

    if trigger is None:
        return {
            "should_offer": False,
            "reason": None,
            "reasons": [],
            "trigger": None,
            "bypass_cooldown": False,
            "in_cooldown": False,
            "detalj_start": detalj_start.isoformat() if detalj_start else None,
            "detalj_end": detalj_end.isoformat() if detalj_end else None,
            "next_start": None,
            "constants": {
                "DETAIL_WEEKS": DETAIL_WEEKS,
                "ROLL_TRIGGER_DAYS_LEFT": ROLL_TRIGGER_DAYS_LEFT,
                "ROLL_TRIGGER_BLOCK_ELAPSED_DAYS": ROLL_TRIGGER_BLOCK_ELAPSED_DAYS,
                "ROLL_COOLDOWN_DAYS": ROLL_COOLDOWN_DAYS,
                "ICU_SYNC_WEEKS": ICU_SYNC_WEEKS,
            },
        }

    bypass = explicit
    ath = athlete or {}
    last_offer = _parse_ts(ath.get("detalj_roll_offered_at"))
    last_confirm = _parse_ts(ath.get("detalj_roll_confirmed_at"))
    last = max([t for t in (last_offer, last_confirm) if t is not None], default=None)
    days_since = _days_since(last)
    in_cooldown = (
        (not bypass)
        and days_since is not None
        and days_since < ROLL_COOLDOWN_DAYS
    )
    next_start = next_detalj_start_after(detalj_end, today=today)
    return {
        "should_offer": not in_cooldown,
        "reason": reasons[0] if reasons else trigger,
        "reasons": reasons,
        "trigger": trigger,
        "bypass_cooldown": bypass,
        "in_cooldown": in_cooldown,
        "cooldown_days_since": days_since,
        "detalj_start": detalj_start.isoformat() if detalj_start else None,
        "detalj_end": detalj_end.isoformat() if detalj_end else None,
        "next_start": next_start.isoformat(),
        "block_id": (block or {}).get("id"),
        "constants": {
            "DETAIL_WEEKS": DETAIL_WEEKS,
            "ROLL_TRIGGER_DAYS_LEFT": ROLL_TRIGGER_DAYS_LEFT,
            "ROLL_TRIGGER_BLOCK_ELAPSED_DAYS": ROLL_TRIGGER_BLOCK_ELAPSED_DAYS,
            "ROLL_COOLDOWN_DAYS": ROLL_COOLDOWN_DAYS,
            "ICU_SYNC_WEEKS": ICU_SYNC_WEEKS,
        },
    }


def build_roll_proposal_card(
    blocks: list[dict[str, Any]],
    *,
    athlete: dict[str, Any] | None = None,
    signals: dict[str, bool] | None = None,
    today: date | None = None,
    next_start: date | str | None = None,
    readiness: dict[str, Any] | None = None,
    roll_eval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Structured plan_roll card — Human Coach confirm required, never silent."""
    today = today or date.today()
    if isinstance(next_start, str):
        start = parse_iso_date(next_start) or next_detalj_start_after(None, today=today)
    elif isinstance(next_start, date):
        start = next_start
    else:
        start = next_detalj_start_after(None, today=today)
    payload = build_two_tier_plan_payload(
        blocks,
        athlete=athlete,
        signals=signals,
        today=start,
        detalj_weeks=DETAIL_WEEKS,
        detalj_start=start,
        readiness=readiness,
    )
    ev = roll_eval or {}
    return {
        "op": "plan_roll",
        "confirm_required": True,
        "rebuild": True,
        "scope": "detalj",
        "tier_model": "grov+detalj",
        "detalj_weeks": payload["detalj_weeks"],
        "detalj_start": payload["detalj_start"],
        "detalj_end": payload["detalj_end"],
        "sessions": payload["sessions"],
        "count": payload["count"],
        "planned_sessions_count": payload["count"],
        "grov_horizon_weeks": payload["grov_horizon_weeks"],
        "icu_sync_weeks": ICU_SYNC_WEEKS,
        "readiness": readiness or {},
        "roll": {
            "trigger": ev.get("trigger"),
            "reason": ev.get("reason"),
            "bypass_cooldown": ev.get("bypass_cooldown"),
        },
        "horizon_note_nb": payload["horizon_note_nb"],
        "message": (
            f"Forslag: neste detaljplan ({DETAIL_WEEKS} uker, "
            f"{payload['detalj_start']} → {payload['detalj_end']}). "
            "Bekreft for å lagre — Intervals først etter Sync. Ingen stille rull."
        ),
        "confirm_hint": (
            "Human Coach: forslag → forhåndsvis → bekreft → lagre detaljplan → "
            "valgfri Sync nærvindu. Grovplan (meso) beholdes."
        ),
    }
