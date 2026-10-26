"""Beta: app ICU-shaped events → TrainingPeaks planned workouts."""

from __future__ import annotations

from datetime import date
from typing import Any

from trainingpeaks_beta.auth import fetch_bearer_token, fetch_tp_user, normalize_tp_auth_cookie
from trainingpeaks_beta.client import create_planned_workout
from trainingpeaks_beta.structure import structure_from_icu_event

ICU_TYPE_TO_TP: dict[str, int] = {
    "ride": 2,
    "virtualride": 2,
    "bike": 2,
    "run": 3,
    "swim": 1,
    "weighttraining": 9,
    "walk": 13,
    "other": 100,
}


def tp_public_status(secrets: dict[str, Any] | None) -> dict[str, Any]:
    row = secrets or {}
    cookie = (row.get("tp_auth_cookie") or "").strip()
    enabled = bool(row.get("tp_sync_enabled"))
    uid = (row.get("tp_user_id") or "").strip() or None
    connected = bool(cookie)
    return {
        "beta": True,
        "connected": connected,
        "sync_enabled": enabled and connected,
        "tp_user_id": uid,
        "cookie_hint": "••••" if connected else None,
        "warning_nb": (
            "Uoffisiell tpapi-sync (beta). Cookie utløper; bruk på eget ansvar."
            if connected
            else None
        ),
    }


def icu_workout_events_for_tp(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ev in events:
        if (ev.get("category") or "").upper() != "WORKOUT":
            continue
        out.append(ev)
    return out


def _workout_type_id(ev: dict[str, Any]) -> int:
    t = str(ev.get("type") or ev.get("_sport") or "").replace(" ", "").lower()
    return ICU_TYPE_TO_TP.get(t, 100)


def _workout_day(ev: dict[str, Any]) -> str:
    raw = str(ev.get("start_date_local") or ev.get("_day") or "")[:10]
    if raw:
        return raw
    return date.today().isoformat()


def _hours_planned(ev: dict[str, Any]) -> float | None:
    mins = ev.get("_duration_minutes")
    if mins is not None:
        try:
            return max(0.05, float(mins) / 60.0)
        except (TypeError, ValueError):
            pass
    mt = ev.get("moving_time")
    if mt is not None:
        try:
            return max(0.05, float(mt) / 3600.0)
        except (TypeError, ValueError):
            pass
    return None


def icu_event_to_tp_payload(ev: dict[str, Any], athlete_id: str) -> dict[str, Any]:
    title = str(ev.get("name") or "Workout").strip()[:120]
    description = str(ev.get("description") or "").strip()
    structure = structure_from_icu_event(ev)
    tss = ev.get("icu_training_load")
    tss_planned = int(tss) if tss is not None and str(tss).isdigit() else None
    return {
        "athleteId": athlete_id,
        "workoutDay": _workout_day(ev),
        "workoutTypeValueId": _workout_type_id(ev),
        "title": title,
        "description": description or None,
        "totalTime": None,
        "totalTimePlanned": _hours_planned(ev),
        "tssActual": None,
        "tssPlanned": tss_planned,
        "structure": structure,
    }


def preview_tp_push(
    events: list[dict[str, Any]],
    *,
    athlete_id: str,
) -> dict[str, Any]:
    workouts = icu_workout_events_for_tp(events)
    previews = []
    structured = 0
    for ev in workouts:
        payload = icu_event_to_tp_payload(ev, athlete_id)
        if payload.get("structure"):
            structured += 1
        previews.append(
            {
                "day": payload["workoutDay"],
                "title": payload["title"],
                "workout_type": payload["workoutTypeValueId"],
                "has_structure": bool(payload.get("structure")),
                "hours_planned": payload.get("totalTimePlanned"),
            }
        )
    return {
        "workouts_count": len(previews),
        "structured_count": structured,
        "previews": previews[:40],
        "truncated": max(0, len(previews) - 40),
        "message_nb": (
            f"Beta: {len(previews)} planlagte økter til TrainingPeaks "
            f"({structured} med strukturert hoveddel). Bekreft for å skrive."
        ),
    }


def push_tp_workouts(
    auth_cookie: str,
    athlete_id: str,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    cookie = normalize_tp_auth_cookie(auth_cookie)
    workouts = icu_workout_events_for_tp(events)
    pushed = 0
    errors: list[str] = []
    for ev in workouts:
        payload = icu_event_to_tp_payload(ev, athlete_id)
        try:
            create_planned_workout(cookie, athlete_id, payload)
            pushed += 1
        except Exception as exc:
            errors.append(f"{payload.get('workoutDay')} {payload.get('title')}: {exc}")
    return {
        "pushed": pushed,
        "attempted": len(workouts),
        "errors": errors[:10],
    }


def verify_tp_credentials(auth_cookie: str) -> tuple[bool, str | None, str | None]:
    """Return ok, error_message, tp_user_id."""
    try:
        cookie = normalize_tp_auth_cookie(auth_cookie)
        bearer = fetch_bearer_token(cookie)
        user = fetch_tp_user(bearer)
        uid = str(user.get("userId") or user.get("user", {}).get("userId") or "")
        if not uid:
            return False, "Fant ikke userId i TP-svar", None
        return True, None, uid
    except Exception as exc:
        return False, str(exc), None
