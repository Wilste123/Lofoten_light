"""Deterministic week analysis helpers — load, intensity, prescriptions, Plan B.

Used by «sjekk uka mi» to close the gap toward agent-modus coach reports.
Never writes to Intervals.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import Any

from beta_forecasts import activity_tss
from plan_calendar_merge import extract_plan_b_lines, extract_weekly_risk_lines
from sessions_service import parse_session_structure

_QUALITY_HINT = re.compile(
    r"(interval|terskel|threshold|vo2|css|tempo|crisscross|elghufs|"
    r"\d+\s*[x×]\s*\d+|hoveddel|main\s*set|kvalitet)",
    re.IGNORECASE,
)


def _float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def session_duration_hours(s: dict[str, Any]) -> float | None:
    h = _float(s.get("duration_hours"))
    if h is not None:
        return h
    m = _float(s.get("duration_minutes"))
    if m is not None:
        return round(m / 60.0, 2)
    return None


def session_load(s: dict[str, Any]) -> float | None:
    for key in (
        "training_load",
        "icu_training_load",
        "tss",
        "load",
        "projected_tss",
    ):
        v = _float(s.get(key))
        if v is not None and v >= 0:
            return v
    # Proxy from duration when ICU load missing (same as beta_forecasts)
    return activity_tss(s)


def session_intensity(s: dict[str, Any]) -> float | None:
    for key in ("intensity", "icu_intensity", "if"):
        v = _float(s.get(key))
        if v is not None:
            # Intervals IF often 0–1.2; sometimes 0–100
            if v > 3:
                return round(v / 100.0, 3)
            return v
    return None


def summarize_week_load(
    completed: list[dict[str, Any]],
    *,
    planned: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Hours + TSS-like load + intensity from ICU activities (completed)."""
    hours = 0.0
    load = 0.0
    intens_vals: list[float] = []
    by_sport: dict[str, float] = defaultdict(float)
    n_with_load = 0
    for s in completed or []:
        h = session_duration_hours(s)
        if h is not None:
            hours += h
        tss = session_load(s)
        if tss is not None:
            load += tss
            n_with_load += 1
            sport = str(
                s.get("discipline_label")
                or s.get("discipline")
                or s.get("sport")
                or s.get("type")
                or "annet"
            )
            by_sport[sport] += tss
        inten = session_intensity(s)
        if inten is not None:
            intens_vals.append(inten)

    planned_hours = 0.0
    planned_load = 0.0
    for s in planned or []:
        h = session_duration_hours(s)
        if h is not None:
            planned_hours += h
        tss = session_load(s)
        if tss is not None:
            planned_load += tss

    avg_if = round(sum(intens_vals) / len(intens_vals), 3) if intens_vals else None
    return {
        "sessions": len(completed or []),
        "hours": round(hours, 1),
        "load": round(load, 0),
        "sessions_with_load": n_with_load,
        "avg_intensity": avg_if,
        "load_by_sport": {k: round(v, 0) for k, v in sorted(by_sport.items(), key=lambda x: -x[1])},
        "planned_hours": round(planned_hours, 1) if planned else None,
        "planned_load": round(planned_load, 0) if planned else None,
    }


def load_bits_nb(summary: dict[str, Any] | None) -> list[str]:
    if not summary:
        return []
    bits: list[str] = []
    bits.append(
        f"Gjennomført: ~{summary.get('hours', 0)} t · "
        f"load ~{int(summary.get('load') or 0)} "
        f"({summary.get('sessions', 0)} aktiviteter)"
    )
    if summary.get("avg_intensity") is not None:
        bits.append(f"Snitt intensitet (IF) ~{summary['avg_intensity']:.2f}")
    by = summary.get("load_by_sport") or {}
    if by:
        top = ", ".join(f"{k} {int(v)}" for k, v in list(by.items())[:4])
        bits.append(f"Load per sport: {top}")
    if summary.get("planned_hours") is not None:
        bits.append(
            f"Planlagt (kalender): ~{summary['planned_hours']} t"
            + (
                f" · proj. load ~{int(summary['planned_load'])}"
                if summary.get("planned_load")
                else ""
            )
        )
    return bits


def _is_quality_session(s: dict[str, Any]) -> bool:
    text = " ".join(
        str(x)
        for x in (
            s.get("name"),
            s.get("description"),
            s.get("description_preview"),
        )
        if x
    )
    if _QUALITY_HINT.search(text):
        return True
    structure = parse_session_structure(s.get("description"))
    phases = structure.get("phases") or []
    main = next((p for p in phases if p.get("id") == "main"), None)
    if main and (main.get("items") or []):
        return True
    return False


def format_session_prescription_nb(s: dict[str, Any]) -> str | None:
    """Warmup / main / cooldown block for one session — full, not «60 min easy»."""
    day = str(s.get("session_date") or s.get("date") or "")[:10]
    name = str(s.get("name") or "Økt")
    sport = str(
        s.get("discipline_label") or s.get("discipline") or s.get("sport") or ""
    )
    desc = str(s.get("description") or "")
    structure = parse_session_structure(desc)
    phases = structure.get("phases") or []
    lines: list[str] = [
        f"{day} · {name}" + (f" ({sport})" if sport else ""),
    ]
    if phases:
        for phase in phases:
            items = phase.get("items") or []
            if not items:
                continue
            label = phase.get("label") or phase.get("id") or "Del"
            lines.append(f"  {label}:")
            for it in items[:8]:
                lines.append(f"    - {it}")
    else:
        # Thin description — still surface what we have (honest)
        preview = (s.get("description_preview") or desc or "").strip()
        if preview:
            # Keep first ~4 non-empty lines
            body_lines = [ln.strip() for ln in preview.splitlines() if ln.strip()][:4]
            if not body_lines:
                body_lines = [preview[:240]]
            for ln in body_lines:
                lines.append(f"  - {ln}")
        else:
            dur = session_duration_hours(s)
            if dur is not None:
                lines.append(f"  - Ca. {int(round(dur * 60))} min (ingen detaljert resept i kalender)")
            else:
                return None
    # Plan B / risk on this session
    for m in re.finditer(r"Plan\s*B\s*:\s*([^\n]+)", desc, re.IGNORECASE):
        lines.append(f"  Plan B: {m.group(1).strip()[:160]}")
        break
    return "\n".join(lines)


def quality_prescriptions_nb(
    planned: list[dict[str, Any]],
    *,
    max_sessions: int = 4,
) -> list[str]:
    """Prefer quality sessions with structure; fall back to any with description."""
    rows = list(planned or [])
    quality = [s for s in rows if _is_quality_session(s)]
    pool = quality if quality else [
        s for s in rows if (s.get("description") or s.get("description_preview"))
    ]
    if not pool:
        pool = rows
    out: list[str] = []
    for s in pool[:max_sessions]:
        block = format_session_prescription_nb(s)
        if block:
            out.append(block)
    return out


def calendar_source_label(
    *,
    intervals_linked: bool,
    used_icu_calendar: bool,
    dont_touch: bool = False,
) -> str:
    if not intervals_linked:
        return "Kilde: app-plan (Intervals ikke koblet)."
    if used_icu_calendar:
        base = "Kilde: Intervals-kalender (WORKOUT) + ICU-aktiviteter — ikke bare repo/app-CSV."
    else:
        base = "Kilde: app-plan (ingen ICU-WORKOUT i vinduet) + aktiviteter hvis hentet."
    if dont_touch:
        base += " Don't-touch: ingen kalender-push."
    else:
        base += " Ingen sync uten at du ber om det (preview → bekreft)."
    return base


def week_risk_and_plan_b(
    planned: list[dict[str, Any]],
    *,
    tb: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Combine session Plan B / ukerisiko with TB-driven recommendation."""
    plan_b_lines = extract_plan_b_lines(planned)
    risk_lines = extract_weekly_risk_lines(planned)
    tb_plan_b = (tb or {}).get("plan_b_nb") if tb else None
    if not risk_lines:
        # Default risk sentence when missing from descriptions
        risk_lines = [
            "Ukerisiko: for høy intensitet hvis søvn/HRV er lav — prioriter kontinuitet."
        ]
    return {
        "plan_b_lines": plan_b_lines,
        "risk_lines": risk_lines,
        "tb_plan_b": tb_plan_b,
    }


def filter_sessions_by_week(
    rows: list[dict[str, Any]],
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in rows or []:
        day_s = str(s.get("session_date") or s.get("date") or s.get("start_date") or "")[
            :10
        ]
        try:
            d = date.fromisoformat(day_s)
        except ValueError:
            continue
        if start <= d <= end:
            out.append(s)
    return out
