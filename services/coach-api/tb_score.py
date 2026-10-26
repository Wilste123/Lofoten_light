"""TB-Score bridge — reuse repo ``scripts/readiness_total_load.py`` from coach-api.

Same engine as agent-modus ``compute_readiness.py`` / ``generate_coach_report.py``.
Soft-fails when scripts or data are missing. Never writes to Intervals.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
_DEFAULT_CFG = _REPO_ROOT / "docs" / "athlete" / "readiness-config.json"

if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


def _import_rtl():
    """Lazy import so coach-api still boots if scripts tree is incomplete."""
    from readiness_total_load import (  # type: ignore[import-not-found]
        ActivityPoint,
        DayInputs,
        compute_readiness_at,
        load_config,
        parse_activity_points,
        parse_wellness_rows,
        resolve_as_of,
        result_to_dict,
    )

    return {
        "ActivityPoint": ActivityPoint,
        "DayInputs": DayInputs,
        "compute_readiness_at": compute_readiness_at,
        "load_config": load_config,
        "parse_activity_points": parse_activity_points,
        "parse_wellness_rows": parse_wellness_rows,
        "resolve_as_of": resolve_as_of,
        "result_to_dict": result_to_dict,
    }


def config_path() -> Path:
    return _DEFAULT_CFG if _DEFAULT_CFG.is_file() else Path()


def _fields_union(rows: list[dict[str, Any]]) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for r in rows or []:
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                keys.append(str(k))
    return keys


def _float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def activity_rows_from_sessions(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map normalized public sessions / ICU activities → CSV-like rows for TB."""
    out: list[dict[str, Any]] = []
    for s in sessions or []:
        # Only completed volume — skip NOTES and bare planned events
        if s.get("calendar_role") == "note" or s.get("training_status") == "note":
            continue
        if s.get("kind") == "event":
            continue
        start = (
            s.get("start_date_local")
            or s.get("start_date")
            or s.get("date")
            or s.get("session_date")
        )
        if not start:
            continue
        load = (
            _float(s.get("training_load"))
            or _float(s.get("icu_training_load"))
            or _float(s.get("tss"))
            or _float(s.get("load"))
        )
        if load is None:
            continue
        row: dict[str, Any] = {
            "start_date_local": str(start),
            "icu_training_load": load,
            "type": s.get("type") or s.get("sport") or s.get("discipline") or "?",
        }
        intens = _float(s.get("intensity")) or _float(s.get("icu_intensity"))
        if intens is not None:
            row["icu_intensity"] = intens
        dur_h = _float(s.get("duration_hours"))
        if dur_h is not None and dur_h > 0:
            row["moving_time"] = int(round(dur_h * 3600))
        elif s.get("moving_time") is not None:
            row["moving_time"] = s.get("moving_time")
        elif s.get("elapsed_time") is not None:
            row["elapsed_time"] = s.get("elapsed_time")
        out.append(row)
    return out


def compute_tb_snapshot(
    wellness_rows: list[dict[str, Any]] | None,
    activity_rows: list[dict[str, Any]] | None = None,
    *,
    as_of: str = "now",
    include_subjective: bool = False,
    cfg_path: Path | None = None,
) -> dict[str, Any]:
    """Compute TB-Score v2 snapshot. Soft empty payload when data insufficient."""
    empty: dict[str, Any] = {
        "available": False,
        "tb_score": None,
        "band": None,
        "recommendation": None,
        "plan_b_nb": None,
        "source": "readiness_total_load",
        "note": "Mangler wellness-data for TB-Score.",
    }
    try:
        rtl = _import_rtl()
    except Exception as exc:  # noqa: BLE001
        empty["note"] = f"TB-modul utilgjengelig ({exc.__class__.__name__})"
        return empty

    rows = [r for r in (wellness_rows or []) if isinstance(r, dict)]
    if not rows:
        return empty

    try:
        fields = _fields_union(rows)
        days = rtl["parse_wellness_rows"](rows, fields)
        if not days:
            return empty
        acts = None
        a_rows = [r for r in (activity_rows or []) if isinstance(r, dict)]
        if a_rows:
            acts = rtl["parse_activity_points"](a_rows, _fields_union(a_rows))
        cfg = rtl["load_config"](cfg_path or (_DEFAULT_CFG if _DEFAULT_CFG.is_file() else None))
        as_of_dt = rtl["resolve_as_of"](as_of, cfg)
        result = rtl["compute_readiness_at"](
            as_of_dt, days, acts, cfg, include_subjective
        )
        payload = rtl["result_to_dict"](result)
        band = payload.get("band")
        score = payload.get("tb_score")
        rec = payload.get("recommendation") or ""
        plan_b = plan_b_recommendation_nb(band=band, score=score, recommendation=rec)
        return {
            "available": True,
            "tb_score": score,
            "band": band,
            "recommendation": rec,
            "plan_b_nb": plan_b,
            "tsb": payload.get("tsb"),
            "atl_ctl_ratio": payload.get("atl_ctl_ratio"),
            "as_of": payload.get("as_of"),
            "wellness_date": payload.get("wellness_date"),
            "components": payload.get("components") or [],
            "acute": payload.get("acute"),
            "life_adjustment": payload.get("life_adjustment"),
            "source": "readiness_total_load",
            "note": "TB-Score v2 (tidspunkt; subjektiv wellness default av).",
        }
    except Exception as exc:  # noqa: BLE001 — soft-fail for chat
        empty["note"] = f"TB-beregning feilet ({exc.__class__.__name__})"
        return empty


def plan_b_recommendation_nb(
    *,
    band: str | None,
    score: int | float | None = None,
    recommendation: str | None = None,
) -> str:
    """Coach Plan B line from TB band — mirrors agent-modus voice."""
    b = (band or "").lower()
    if b.startswith("grønn") or b == "green":
        return (
            "Plan A: hold avtalt kvalitet. Ikke legg på ekstra bare fordi TB er grønn."
        )
    if b.startswith("gul") or b == "yellow":
        return (
            "Plan B: bytt terskel/VO2 → Z2 eller kutt sett; maks én hard økt denne uka. "
            + (recommendation or "")
        ).strip()
    if b.startswith("rød") or b == "red":
        return (
            "Plan B (recovery): rolig bevegelse / lett styrke; ingen VO2/FTP/CSS-test. "
            + (recommendation or "")
        ).strip()
    if score is not None:
        try:
            s = float(score)
        except (TypeError, ValueError):
            s = None
        if s is not None:
            if s >= 78:
                return plan_b_recommendation_nb(band="grønn", recommendation=recommendation)
            if s >= 58:
                return plan_b_recommendation_nb(band="gul", recommendation=recommendation)
            return plan_b_recommendation_nb(band="rød", recommendation=recommendation)
    return recommendation or "Ingen TB-basert Plan B — bruk subjektiv form + avtaler."


def tb_bits_nb(tb: dict[str, Any] | None) -> list[str]:
    """Compact Norwegian lines for week-check / chat."""
    if not tb or not tb.get("available"):
        note = (tb or {}).get("note") if isinstance(tb, dict) else None
        return [str(note)] if note else ["TB-Score ikke tilgjengelig."]
    bits: list[str] = []
    score = tb.get("tb_score")
    band = tb.get("band") or "?"
    bits.append(f"TB-Score {score}/100 · {band}")
    if tb.get("tsb") is not None:
        tsb = tb["tsb"]
        ratio = tb.get("atl_ctl_ratio")
        extra = f", ATL/CTL {ratio:.2f}" if isinstance(ratio, (int, float)) else ""
        bits.append(f"TSB {tsb:+.0f}{extra}")
    acute = tb.get("acute") or {}
    if acute.get("hours_since_last") is not None:
        bits.append(
            f"Tid siden siste økt: {acute['hours_since_last']:.1f} t "
            f"(24h-load {acute.get('load_24h', 0):.0f})"
        )
    if tb.get("recommendation"):
        bits.append(str(tb["recommendation"]))
    if tb.get("plan_b_nb"):
        bits.append(str(tb["plan_b_nb"]))
    return bits


def fetch_tb_for_athlete(
    secrets: dict[str, Any] | None,
    *,
    wellness_days: int = 28,
    activity_sessions: list[dict[str, Any]] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Fetch wellness (+ optional activity sessions) and compute TB. Soft-fail."""
    today = today or date.today()
    key = ((secrets or {}).get("intervals_api_key") or "").strip()
    aid = ((secrets or {}).get("intervals_athlete_id") or "").strip()
    if not key or not aid:
        return {
            "available": False,
            "tb_score": None,
            "band": None,
            "recommendation": None,
            "plan_b_nb": None,
            "source": "none",
            "note": "Intervals ikke koblet — TB-Score krever wellness.",
        }
    try:
        from wellness import fetch_wellness

        oldest = (today - timedelta(days=max(7, wellness_days - 1))).isoformat()
        newest = today.isoformat()
        rows = fetch_wellness(key, aid, oldest, newest)
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "tb_score": None,
            "band": None,
            "recommendation": None,
            "plan_b_nb": None,
            "source": "intervals",
            "note": f"Wellness-henting feilet ({exc.__class__.__name__})",
            "fetch_error": True,
        }
    a_rows = activity_rows_from_sessions(activity_sessions or [])
    return compute_tb_snapshot(rows, a_rows)
