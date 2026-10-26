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


def session_plan_b_and_risk(s: dict[str, Any]) -> dict[str, list[str]]:
    """Per-session Plan B / risk lines for Økter detail."""
    text = str(s.get("description") or "")
    plan_b: list[str] = []
    risk: list[str] = []
    for m in re.finditer(r"Plan\s*B\s*:\s*([^\n]+)", text, re.IGNORECASE):
        plan_b.append(m.group(0).strip()[:240])
    for m in re.finditer(
        r"(?:Ukerisiko|Weekly\s*risk|Risiko)\s*:\s*([^\n]+)",
        text,
        re.IGNORECASE,
    ):
        risk.append(m.group(0).strip()[:240])
    return {"plan_b": plan_b[:3], "risk": risk[:2]}


def partition_merged_calendar(
    merged: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Split merged app∪ICU rows by sync_status for coach compare."""
    from plan_calendar_merge import (
        SYNC_INTERVALS_ONLY,
        SYNC_PLANNED_NOT_SYNCED,
        SYNC_SYNCED,
    )

    buckets: dict[str, list[dict[str, Any]]] = {
        SYNC_SYNCED: [],
        SYNC_PLANNED_NOT_SYNCED: [],
        SYNC_INTERVALS_ONLY: [],
    }
    for s in merged or []:
        st = str(s.get("sync_status") or SYNC_PLANNED_NOT_SYNCED)
        buckets.setdefault(st, []).append(s)
    return buckets


def compare_icu_vs_app_nb(
    merged: list[dict[str, Any]],
    *,
    week_start: str,
    week_end: str,
    intervals_linked: bool,
    app_only_planned: list[dict[str, Any]] | None = None,
    max_lines: int = 8,
) -> dict[str, Any]:
    """Deep calendar truth: app SoT vs ICU WORKOUT — read-only coach payload.

    Returns Norwegian reply bits + structured buckets. Never implies a write.
    """
    from plan_calendar_merge import (
        SYNC_INTERVALS_ONLY,
        SYNC_PLANNED_NOT_SYNCED,
        SYNC_SYNCED,
    )

    parts = partition_merged_calendar(merged)
    synced = parts.get(SYNC_SYNCED) or []
    app_only = parts.get(SYNC_PLANNED_NOT_SYNCED) or []
    icu_only = parts.get(SYNC_INTERVALS_ONLY) or []

    def _line(s: dict[str, Any]) -> str:
        day = str(s.get("session_date") or s.get("date") or "")[:10]
        name = (s.get("name") or s.get("intervals_name") or "Økt").strip()
        sport = (s.get("sport") or s.get("discipline") or "").strip()
        src = s.get("source_kind_nb") or s.get("source_kind") or ""
        bits = [day, name]
        if sport:
            bits.append(f"({sport})")
        if src:
            bits.append(f"[{src}]")
        return " · ".join(bits)

    sections: list[str] = []
    if not intervals_linked:
        sections.append(
            "Intervals ikke koblet — sammenligning begrenset til app-plan (SoT)."
        )
        rows = list(app_only_planned or merged or [])
        if rows:
            sections.append("App-plan:")
            for s in rows[:max_lines]:
                sections.append(f"  - {_line(s)}")
        else:
            sections.append("Ingen økter i app-planen for vinduet.")
    else:
        sections.append(
            f"Kalender-sannhet {week_start}–{week_end} "
            "(app SoT vs Intervals WORKOUT — kun lesing):"
        )
        sections.append(
            f"Matched app↔ICU: {len(synced)} · "
            f"kun app: {len(app_only)} · "
            f"kun Intervals: {len(icu_only)}"
        )
        if synced:
            sections.append("Matched:")
            for s in synced[:max_lines]:
                sections.append(f"  - {_line(s)}")
        if app_only:
            sections.append("Kun i app (ikke synket):")
            for s in app_only[:max_lines]:
                sections.append(f"  - {_line(s)}")
        if icu_only:
            sections.append(
                "Kun på Intervals (ofte ditt utkast — endres ikke uten at du ber):"
            )
            for s in icu_only[:max_lines]:
                sections.append(f"  - {_line(s)}")
        if not synced and not app_only and not icu_only:
            sections.append("Ingen WORKOUT i vinduet.")

    # Name/date mismatches between app-only and ICU-only same day
    drift: list[str] = []
    icu_by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in icu_only:
        day = str(s.get("session_date") or s.get("date") or "")[:10]
        if day:
            icu_by_day[day].append(s)
    for s in app_only:
        day = str(s.get("session_date") or s.get("date") or "")[:10]
        peers = icu_by_day.get(day) or []
        if not peers:
            continue
        app_name = (s.get("name") or "").strip().lower()
        for p in peers:
            icu_name = (p.get("name") or p.get("intervals_name") or "").strip().lower()
            if app_name and icu_name and app_name != icu_name:
                drift.append(
                    f"{day}: app «{s.get('name')}» vs ICU «{p.get('name') or p.get('intervals_name')}»"
                )
                break
    if drift:
        sections.append("Avvik samme dag (navn/innhold — sjekk manuelt):")
        for d in drift[:5]:
            sections.append(f"  - {d}")

    presc_pool = list(synced) + list(icu_only) + list(app_only)
    prescriptions = quality_prescriptions_nb(presc_pool, max_sessions=3)
    plan_b = extract_plan_b_lines(presc_pool)
    risk = extract_weekly_risk_lines(presc_pool)

    return {
        "synced": synced,
        "app_only": app_only,
        "icu_only": icu_only,
        "counts": {
            "synced": len(synced),
            "app_only": len(app_only),
            "icu_only": len(icu_only),
        },
        "drift_lines": drift[:5],
        "reply_lines": sections,
        "prescriptions": prescriptions,
        "plan_b": plan_b,
        "risk": risk,
    }


def _session_line(s: dict[str, Any]) -> str:
    day = str(s.get("session_date") or s.get("date") or "")[:10]
    name = str(s.get("name") or "Økt")
    sport = str(
        s.get("discipline_label") or s.get("discipline") or s.get("sport") or s.get("type") or ""
    )
    status = str(s.get("training_status") or "")
    bit = f"{day} · {name}"
    if sport:
        bit += f" ({sport})"
    if status and status not in ("planned", "completed", "matched_activity"):
        bit += f" [{status}]"
    return bit


def build_week_compliance(
    sessions_bundle: dict[str, Any] | None,
    *,
    week_start: date,
    week_end: date,
    rolling_4w: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calendar WORKOUT vs ICU-logged activities for one week — Dashboard home.

    Uses the same matching rules as ``list_sessions`` / week-check (NOTE ≠ done).
    """
    bundle = sessions_bundle or {}
    planned = filter_sessions_by_week(list(bundle.get("planned") or []), week_start, week_end)
    completed = filter_sessions_by_week(
        list(bundle.get("completed") or bundle.get("recent") or []),
        week_start,
        week_end,
    )
    missed = filter_sessions_by_week(
        list(bundle.get("planned_not_done") or []), week_start, week_end
    )
    sessions_planned = len(planned)
    missed_n = len(missed)
    if sessions_planned > 0 and (missed_n or completed):
        sessions_done = (
            max(0, sessions_planned - missed_n)
            if missed_n
            else min(len(completed), sessions_planned)
        )
        compliance_pct: float | None = round(
            min(100.0, 100.0 * float(sessions_done) / float(sessions_planned)), 1
        )
    else:
        sessions_done = len(completed)
        compliance_pct = None

    planned_lines = [_session_line(s) for s in planned[:14]]
    done_lines = [_session_line(s) for s in completed[:14]]
    missed_lines = [_session_line(s) for s in missed[:14]]

    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "sessions_planned": sessions_planned,
        "sessions_done": sessions_done,
        "sessions_missed": missed_n,
        "compliance_pct": compliance_pct,
        "planned_lines": planned_lines,
        "done_lines": done_lines,
        "missed_lines": missed_lines,
        "rolling_compliance_4w": rolling_4w,
        "note_nb": (
            "Gjennomført = ICU-aktivitet matchet til planlagt WORKOUT. "
            "NOTE og planlagt uten aktivitet = ikke gjennomført."
        ),
        "written_to_intervals": False,
    }
