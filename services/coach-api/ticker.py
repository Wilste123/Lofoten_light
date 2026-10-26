"""Coach ticker — sparse athlete_events + optional email.

Human Coach only: events open confirm/plan cards — never auto-apply plans
or auto-sync Intervals. Spec: store docs/coach-ticker.md.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from db import (
    Connection,
    get_athlete,
    insert_athlete_event,
    latest_event_of_kind,
    list_athlete_events,
    mark_athlete_event_read,
    utc_now,
)

log = logging.getLogger("coach.ticker")

# Sparse kinds only — see coach-ticker.md
KIND_ROLL_FORWARD = "roll_forward_due"
KIND_SESSIONS_SAVED = "sessions_saved"
KIND_SYNC_OK = "sync_ok"
KIND_SYNC_FAIL = "sync_fail"
KIND_WEEKLY_CAP = "weekly_cap_replace"
KIND_READINESS = "readiness_soft"
KIND_CTL_OVERLOAD = "ctl_overload"

SPARSE_KINDS = frozenset(
    {
        KIND_ROLL_FORWARD,
        KIND_SESSIONS_SAVED,
        KIND_SYNC_OK,
        KIND_SYNC_FAIL,
        KIND_WEEKLY_CAP,
        KIND_READINESS,
        KIND_CTL_OVERLOAD,
    }
)

# Cooldowns (hours) — avoid login spam
COOLDOWN_HOURS: dict[str, float] = {
    KIND_ROLL_FORWARD: 48,
    KIND_WEEKLY_CAP: 12,
    KIND_READINESS: 72,
    KIND_CTL_OVERLOAD: 120,  # 5 days; worsen can re-fire via force
    KIND_SESSIONS_SAVED: 0,  # always notify saves
    KIND_SYNC_OK: 0,
    KIND_SYNC_FAIL: 0,
}

# IOC/Gabbett-ish bands (knowledge/skader/belastningsstyring-acwr.md)
ACWR_SOFT = 1.3
ACWR_HARD = 1.5

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def resend_configured() -> bool:
    return bool(os.environ.get("RESEND_API_KEY", "").strip())


def email_from_address() -> str:
    return (
        os.environ.get("RESEND_FROM_EMAIL", "").strip()
        or os.environ.get("COACH_EMAIL_FROM", "").strip()
        or "Lofoten Coach <onboarding@resend.dev>"
    )


def app_base_url() -> str:
    return (
        os.environ.get("COACH_APP_URL", "").strip()
        or os.environ.get("APP_PUBLIC_URL", "").strip()
        or "https://lofoten-coach.fly.dev"
    )


def validate_email(raw: str | None) -> str | None:
    s = (raw or "").strip().lower()
    if not s:
        return None
    if not _EMAIL_RE.match(s) or len(s) > 254:
        return None
    return s


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


def within_cooldown(
    conn: Connection,
    athlete_id: str,
    kind: str,
    *,
    hours: float | None = None,
) -> bool:
    """True if a same-kind event was created inside the cooldown window."""
    h = COOLDOWN_HOURS.get(kind, 24.0) if hours is None else hours
    if h <= 0:
        return False
    prev = latest_event_of_kind(conn, athlete_id, kind)
    if not prev:
        return False
    created = _parse_ts(prev.get("created_at"))
    if not created:
        return False
    return datetime.now(timezone.utc) - created < timedelta(hours=h)


def acwr_ratio(atl: float | None, ctl: float | None) -> float | None:
    if atl is None or ctl is None:
        return None
    if ctl <= 0:
        return None
    return round(float(atl) / float(ctl), 3)


def evaluate_ctl_overload(
    *,
    ctl: float | None,
    atl: float | None,
) -> dict[str, Any] | None:
    """Return alert dict when ATL:CTL is clearly elevated — never medical diagnosis."""
    ratio = acwr_ratio(atl, ctl)
    if ratio is None:
        return None
    if ratio < ACWR_SOFT:
        return None
    severity = "hard" if ratio >= ACWR_HARD else "soft"
    title = (
        "Høy akutt belastning — vurder å lette"
        if severity == "hard"
        else "Akutt belastning litt høy"
    )
    message = (
        f"ATL/CTL ≈ {ratio:.2f} (ATL {atl:.0f} / CTL {ctl:.0f}). "
        "Høy akutt belastning — vil du lette de neste øktene? "
        "Åpner forslagskort; ingen økter slettes automatisk."
    )
    return {
        "kind": KIND_CTL_OVERLOAD,
        "title": title,
        "payload": {
            "action": "open_ease",
            "ctl": ctl,
            "atl": atl,
            "acwr": ratio,
            "severity": severity,
            "threshold_soft": ACWR_SOFT,
            "threshold_hard": ACWR_HARD,
            "message": message,
            "auto_apply": False,
        },
    }


def evaluate_readiness_soft(
    *,
    sleep_avg_hours: float | None = None,
    hrv_latest: float | None = None,
    hrv_avg_7d: float | None = None,
    hard_day_ahead: bool = False,
) -> dict[str, Any] | None:
    """Rare soft hint before a hard day — info only."""
    if not hard_day_ahead:
        return None
    flags: list[str] = []
    if sleep_avg_hours is not None and sleep_avg_hours < 6.5:
        flags.append(f"søvn ~{sleep_avg_hours:.1f} t")
    if (
        hrv_latest is not None
        and hrv_avg_7d is not None
        and hrv_avg_7d > 0
        and hrv_latest < 0.85 * hrv_avg_7d
    ):
        flags.append("HRV under 7d-snitt")
    if not flags:
        return None
    detail = ", ".join(flags)
    return {
        "kind": KIND_READINESS,
        "title": "Myk readiness-hint før hard dag",
        "payload": {
            "action": "open_coach",
            "flags": flags,
            "message": (
                f"Signaler ({detail}) — vurder lettere alternativ. "
                "Kun info; ingen planendring uten bekreftelse."
            ),
            "auto_apply": False,
        },
    }


def emit_event(
    conn: Connection,
    athlete_id: str,
    *,
    kind: str,
    title: str,
    payload: dict[str, Any] | None = None,
    respect_cooldown: bool = True,
    force: bool = False,
) -> dict[str, Any] | None:
    """Insert athlete_event (+ optional email). Returns row or None if skipped."""
    if kind not in SPARSE_KINDS:
        log.warning("ticker skip unknown kind=%s", kind)
        return None
    if respect_cooldown and not force and within_cooldown(conn, athlete_id, kind):
        return None
    body = dict(payload or {})
    body.setdefault("auto_apply", False)
    body.setdefault("human_coach", True)
    row = insert_athlete_event(
        conn,
        athlete_id,
        kind=kind,
        title=title,
        payload=body,
    )
    # Email best-effort (never raises into confirm path)
    try:
        athlete = get_athlete(conn, athlete_id)
        if athlete:
            send_event_email(athlete, row)
    except Exception as exc:  # noqa: BLE001
        log.info("ticker email soft-fail: %s", exc)
    return row


def emit_sessions_saved(
    conn: Connection,
    athlete_id: str,
    *,
    count: int,
    source: str = "confirm",
    replace: bool = False,
) -> dict[str, Any] | None:
    if count <= 0:
        return None
    title = (
        f"{count} økt(er) lagret (erstattet)"
        if replace
        else f"{count} økt(er) lagret i plan"
    )
    return emit_event(
        conn,
        athlete_id,
        kind=KIND_SESSIONS_SAVED,
        title=title,
        payload={
            "action": "open_plan",
            "count": count,
            "source": source,
            "replace": replace,
        },
        respect_cooldown=False,
    )


def emit_sync_ok(
    conn: Connection,
    athlete_id: str,
    *,
    pushed: int,
    expected: int | None = None,
) -> dict[str, Any] | None:
    exp = expected if expected is not None else pushed
    return emit_event(
        conn,
        athlete_id,
        kind=KIND_SYNC_OK,
        title=f"Intervals Sync OK ({pushed}/{exp})",
        payload={
            "action": "open_plan",
            "pushed": pushed,
            "expected": exp,
        },
        respect_cooldown=False,
    )


def emit_sync_fail(
    conn: Connection,
    athlete_id: str,
    *,
    error: str,
) -> dict[str, Any] | None:
    short = (error or "ukjent feil")[:180]
    return emit_event(
        conn,
        athlete_id,
        kind=KIND_SYNC_FAIL,
        title="Intervals Sync feilet",
        payload={
            "action": "open_coach",
            "error": short,
            "message": f"Sync feilet: {short}. Pending beholdes — trygg å prøve igjen.",
        },
        respect_cooldown=False,
    )


def emit_weekly_cap_replace(
    conn: Connection,
    athlete_id: str,
    *,
    candidates: int = 0,
) -> dict[str, Any] | None:
    return emit_event(
        conn,
        athlete_id,
        kind=KIND_WEEKLY_CAP,
        title="Ukeskap full — tilbyr erstatning",
        payload={
            "action": "open_coach",
            "candidates": candidates,
            "message": (
                "Avtalt økter/uke er fylt. Åpne Coach for erstatningskort "
                "(forhåndsvis → bekreft)."
            ),
        },
        respect_cooldown=True,
    )


def emit_roll_forward_due(
    conn: Connection,
    athlete_id: str,
    *,
    reason: str = "",
    days_left: int | None = None,
) -> dict[str, Any] | None:
    bits = []
    if days_left is not None:
        bits.append(f"{days_left} dager igjen")
    if reason:
        bits.append(reason)
    detail = " · ".join(bits) if bits else "detaljvindu"
    return emit_event(
        conn,
        athlete_id,
        kind=KIND_ROLL_FORWARD,
        title="Foreslå neste 2–4 uker",
        payload={
            "action": "open_roll",
            "days_left": days_left,
            "reason": reason,
            "message": (
                f"Roll-forward ({detail}). Åpne Coach for forslagskort — "
                "bekreft før lagring. Ingen auto-apply."
            ),
            "auto_apply": False,
        },
        respect_cooldown=True,
    )


def maybe_emit_ctl_from_load(
    conn: Connection,
    athlete_id: str,
    load: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not load or not load.get("available"):
        return None
    alert = evaluate_ctl_overload(ctl=load.get("ctl"), atl=load.get("atl"))
    if not alert:
        return None
    # Re-fire early only if severity worsened vs last event
    force = False
    prev = latest_event_of_kind(conn, athlete_id, KIND_CTL_OVERLOAD)
    if prev:
        prev_sev = (prev.get("payload") or {}).get("severity")
        new_sev = (alert["payload"] or {}).get("severity")
        if prev_sev == "soft" and new_sev == "hard":
            force = True
    return emit_event(
        conn,
        athlete_id,
        kind=alert["kind"],
        title=alert["title"],
        payload=alert["payload"],
        respect_cooldown=True,
        force=force,
    )


def maybe_emit_readiness(
    conn: Connection,
    athlete_id: str,
    signals: dict[str, Any] | None,
    *,
    hard_day_ahead: bool = False,
) -> dict[str, Any] | None:
    if not signals or not signals.get("available"):
        return None
    alert = evaluate_readiness_soft(
        sleep_avg_hours=signals.get("sleep_avg_hours"),
        hrv_latest=signals.get("hrv_latest"),
        hrv_avg_7d=signals.get("hrv_avg_7d"),
        hard_day_ahead=hard_day_ahead,
    )
    if not alert:
        return None
    return emit_event(
        conn,
        athlete_id,
        kind=alert["kind"],
        title=alert["title"],
        payload=alert["payload"],
        respect_cooldown=True,
    )


def refresh_soft_ticker(
    conn: Connection,
    athlete_id: str,
    *,
    roll_eval: dict[str, Any] | None = None,
    load: dict[str, Any] | None = None,
    readiness_signals: dict[str, Any] | None = None,
    hard_day_ahead: bool = False,
) -> list[dict[str, Any]]:
    """Create soft events when triggers fire. Never auto-applies plans."""
    created: list[dict[str, Any]] = []
    if roll_eval and roll_eval.get("should_offer"):
        row = emit_roll_forward_due(
            conn,
            athlete_id,
            reason=str(roll_eval.get("reason") or ""),
            days_left=roll_eval.get("days_left"),
        )
        if row:
            created.append(row)
    ctl_row = maybe_emit_ctl_from_load(conn, athlete_id, load)
    if ctl_row:
        created.append(ctl_row)
    ready_row = maybe_emit_readiness(
        conn,
        athlete_id,
        readiness_signals,
        hard_day_ahead=hard_day_ahead,
    )
    if ready_row:
        created.append(ready_row)
    return created


def public_event(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": row.get("id"),
        "kind": row.get("kind"),
        "title": row.get("title") or "",
        "payload": row.get("payload") or {},
        "read_at": row.get("read_at"),
        "created_at": row.get("created_at"),
        "unread": not bool(row.get("read_at")),
    }


def list_public_events(
    conn: Connection,
    athlete_id: str,
    *,
    unread_only: bool = False,
    limit: int = 30,
) -> list[dict[str, Any]]:
    rows = list_athlete_events(
        conn, athlete_id, unread_only=unread_only, limit=limit
    )
    return [public_event(r) for r in rows if r]  # type: ignore[misc]


def mark_read(
    conn: Connection, athlete_id: str, event_id: str
) -> dict[str, Any] | None:
    return public_event(mark_athlete_event_read(conn, athlete_id, event_id))


def send_event_email(
    athlete: dict[str, Any],
    event: dict[str, Any],
) -> dict[str, Any]:
    """Send sparse event email if opt-in + address + RESEND_API_KEY.

    Never invents secrets. Returns status dict for tests/logs.
    """
    if not athlete.get("notify_email"):
        return {"sent": False, "reason": "opt_in_off"}
    to = validate_email(athlete.get("email"))
    if not to:
        return {"sent": False, "reason": "no_email"}
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    if not api_key:
        return {
            "sent": False,
            "reason": "no_resend_key",
            "hint": "Set Fly secret RESEND_API_KEY (+ optional RESEND_FROM_EMAIL)",
        }
    kind = event.get("kind") or ""
    title = event.get("title") or kind
    payload = event.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {}
    msg = payload.get("message") or title
    coach = athlete.get("coach_display_name") or "Coach"
    name = athlete.get("display_name") or "utøver"
    link = app_base_url().rstrip("/")
    subject = f"[Lofoten Coach] {title}"
    text = (
        f"Hei {name},\n\n"
        f"{coach}: {msg}\n\n"
        f"Åpne appen for å bekrefte eller se plan (ingen auto-apply):\n{link}\n\n"
        f"— Lofoten Coach ticker ({kind})\n"
    )
    html = (
        f"<p>Hei {name},</p>"
        f"<p><strong>{coach}:</strong> {msg}</p>"
        f'<p><a href="{link}">Åpne Coach</a> — Human Coach: bekreft før lagring/sync.</p>'
        f"<p style='color:#888;font-size:12px'>Ticker · {kind} · {utc_now()}</p>"
    )
    try:
        with httpx.Client(timeout=12.0) as client:
            r = client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": email_from_address(),
                    "to": [to],
                    "subject": subject,
                    "text": text,
                    "html": html,
                },
            )
        if r.status_code >= 400:
            log.warning("Resend %s: %s", r.status_code, r.text[:300])
            return {
                "sent": False,
                "reason": "resend_error",
                "status": r.status_code,
                "body": r.text[:300],
            }
        data = r.json() if r.content else {}
        return {"sent": True, "provider": "resend", "id": data.get("id")}
    except Exception as exc:  # noqa: BLE001
        log.warning("Resend failed: %s", exc)
        return {"sent": False, "reason": "network", "error": str(exc)[:200]}
