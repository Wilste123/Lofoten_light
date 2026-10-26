"""Text coach-rapport from TB-Score — same engine as ``scripts/generate_coach_report.py``.

No PNG plots, no subprocess, no Intervals writes. Soft-fails when data missing.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from tb_score import (
    activity_rows_from_sessions,
    compute_tb_snapshot,
    fetch_tb_for_athlete,
    tb_bits_nb,
)
from week_analysis import load_bits_nb, summarize_week_load


def format_tb_report_markdown(tb: dict[str, Any]) -> str:
    """Markdown block mirroring ``format_snapshot_markdown`` without importing Result."""
    if not tb or not tb.get("available"):
        note = (tb or {}).get("note") or "TB-Score ikke tilgjengelig."
        return f"# Coach-rapport\n\n{note}\n"

    band = (tb.get("band") or "?").capitalize()
    headline = f"**TB-Score {tb.get('tb_score')}/100** · **{band}**"
    if tb.get("as_of"):
        headline = f"**Kl. {tb['as_of']}:** {headline}"
    lines = [
        "# Coach-rapport — TB-Score\n",
        headline,
    ]
    if tb.get("recommendation"):
        lines.append(f"\n{tb['recommendation']}\n")
    if tb.get("plan_b_nb"):
        lines.append(f"\n**Plan B:** {tb['plan_b_nb']}\n")
    if tb.get("wellness_date"):
        lines.append(f"\nWellness-grunnlag: **{tb['wellness_date']}**.\n")
    acute = tb.get("acute") or {}
    if acute.get("hours_since_last") is not None:
        lines.append(
            f"Tid siden siste økt: **{acute['hours_since_last']:.1f} t** "
            f"(24h-load {acute.get('load_24h', 0):.0f}).\n"
        )
    if tb.get("tsb") is not None:
        extra = (
            f", ATL/CTL {tb['atl_ctl_ratio']:.2f}"
            if isinstance(tb.get("atl_ctl_ratio"), (int, float))
            else ""
        )
        lines.append(f"TSB {tb['tsb']:+.0f}{extra}.\n")
    comps = tb.get("components") or []
    if comps:
        lines.append("\n## Komponenter\n")
        lines.append("| Komponent | Poeng | Detalj |")
        lines.append("|-----------|------:|--------|")
        for c in comps:
            if not isinstance(c, dict):
                continue
            sc = c.get("score")
            sc_s = f"{sc:.0f}" if isinstance(sc, (int, float)) else "—"
            lines.append(
                f"| {c.get('label') or c.get('key') or '?'} | {sc_s} | {c.get('detail') or ''} |"
            )
    lines.append(
        "\n---\n*Samme motor som `scripts/generate_coach_report.py` / "
        "`readiness_total_load.py`. TB-trend regenereres på Dashboard "
        "(JSON→SVG, ingen PNG i git).*\n"
    )
    return "\n".join(lines)


def build_coach_report(
    secrets: dict[str, Any] | None,
    *,
    activity_sessions: list[dict[str, Any]] | None = None,
    wellness_days: int = 28,
    week_completed: list[dict[str, Any]] | None = None,
    week_planned: list[dict[str, Any]] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """TB snapshot + load summary + markdown — soft empty when Intervals missing."""
    tb = fetch_tb_for_athlete(
        secrets,
        wellness_days=wellness_days,
        activity_sessions=activity_sessions,
        today=today,
    )
    load = None
    if week_completed is not None or week_planned is not None:
        load = summarize_week_load(week_completed or [], planned=week_planned)
    md = format_tb_report_markdown(tb)
    if load:
        load_lines = load_bits_nb(load)
        if load_lines:
            md += "\n## Uke-belastning\n\n" + "\n".join(f"- {b}" for b in load_lines) + "\n"
    return {
        "available": bool(tb.get("available")),
        "tb": tb,
        "load": load,
        "tb_bits": tb_bits_nb(tb),
        "markdown": md,
        "source": tb.get("source") or "readiness_total_load",
        "written_to_intervals": False,
        "plots": False,
        "note": (
            None
            if tb.get("available")
            else (tb.get("note") or "Mangler data for coach-rapport.")
        ),
    }


def readiness_dashboard_strip(
    secrets: dict[str, Any] | None,
    *,
    activity_sessions: list[dict[str, Any]] | None = None,
    week_start: str | None = None,
    week_end: str | None = None,
    sessions_planned: int | None = None,
    sessions_done: int | None = None,
    compliance_pct: float | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Compact TB + week pointer for Dashboard (no chat required)."""
    tb = fetch_tb_for_athlete(
        secrets,
        wellness_days=28,
        activity_sessions=activity_sessions,
        today=today,
    )
    return {
        "tb": {
            "available": bool(tb.get("available")),
            "tb_score": tb.get("tb_score"),
            "band": tb.get("band"),
            "plan_b_nb": tb.get("plan_b_nb"),
            "recommendation": tb.get("recommendation"),
            "tsb": tb.get("tsb"),
            "note": tb.get("note"),
        },
        "week": {
            "week_start": week_start,
            "week_end": week_end,
            "sessions_planned": sessions_planned,
            "sessions_done": sessions_done,
            "compliance_pct": compliance_pct,
        },
        "cta_nb": (
            "Åpne Coach-rapport (søndagsritual) eller spør «sjekk uka mi» "
            "for load, Plan B og kvalitetsresepter."
        ),
        "written_to_intervals": False,
    }


def sunday_ritual_payload(
    secrets: dict[str, Any] | None,
    *,
    activity_sessions: list[dict[str, Any]] | None = None,
    week_completed: list[dict[str, Any]] | None = None,
    week_planned: list[dict[str, Any]] | None = None,
    week_compliance: dict[str, Any] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Agent-style Sunday ritual: TB markdown + uke-compliance + ukesopp CTA.

    No PNG. No Intervals write. Soft empty when wellness missing.
    """
    report = build_coach_report(
        secrets,
        activity_sessions=activity_sessions,
        week_completed=week_completed,
        week_planned=week_planned,
        today=today,
    )
    wc = week_compliance or {}
    md = report.get("markdown") or ""
    if wc.get("sessions_planned") is not None:
        pct = wc.get("compliance_pct")
        pct_s = f" ({pct} %)" if pct is not None else ""
        md += (
            "\n## Planlagt vs gjennomført (denne uka)\n\n"
            f"- Økter: **{wc.get('sessions_done', 0)} / {wc.get('sessions_planned', 0)}**"
            f"{pct_s}\n"
        )
        missed = wc.get("missed_lines") or []
        if missed:
            md += "- Ikke gjennomført:\n"
            for ln in missed[:8]:
                md += f"  - {ln}\n"
        done = wc.get("done_lines") or []
        if done:
            md += "- Logget:\n"
            for ln in done[:8]:
                md += f"  - {ln}\n"
        md += f"\n_{(wc.get('note_nb') or '').strip()}_\n"
    md += (
        "\n## Neste steg (søndagsritual)\n\n"
        "1. Les TB / Plan B over — se også TB-trend-grafen på Dashboard.\n"
        "2. Spør Coach **ukesopp** — fire korte spørsmål (lagres i appen, ikke Intervals).\n"
        "3. Ev. **sjekk uka mi** for full resept + load, eller **analyser dagens økt** "
        "for watt/puls + intervall-feedback.\n"
        "4. Intervals → TP: last ned zip under Dashboard (ingen auto-write til TP).\n"
    )
    return {
        **report,
        "markdown": md,
        "week_compliance": wc or None,
        "ritual": True,
        "cta": {
            "ukesopp_nb": "ukesopp",
            "week_check_nb": "sjekk uka mi",
            "session_analysis_nb": "analyser dagens økt",
            "tp_export_nb": "eksporter intervals til TP",
        },
        "plots": False,
        "written_to_intervals": False,
    }


def recomputable_from_rows(
    wellness_rows: list[dict[str, Any]],
    activity_sessions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Unit-test / offline path — no Intervals fetch."""
    a_rows = activity_rows_from_sessions(activity_sessions or [])
    tb = compute_tb_snapshot(wellness_rows, a_rows)
    return {
        "available": bool(tb.get("available")),
        "tb": tb,
        "markdown": format_tb_report_markdown(tb),
        "written_to_intervals": False,
        "plots": False,
    }
