"""Beta forecasts — CTL/ATL/TSB trajectories, ACWR bands, race-form (experimental).

Past = ICU wellness CTL/ATL (preferred) and/or Banister EWMA from activities.
Future = Banister projection from planned_sessions load — labeled *planlagt*.
Never auto-applies plan changes. Spec: store docs/beta-forecasts.md.
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any

from progress_compliance import (
    API_BASE,
    _ACTIVITY_FIELDS,
    _activity_local_date,
    _http_get_json,
    days_to_goal,
    fetch_intervals_activities,
    parse_duration_hours,
)
from ticker import ACWR_HARD, ACWR_SOFT, acwr_ratio
from wellness import resolve_wellness_bundle

# Banister-family EWMA time constants used in practice (TrainingPeaks PMC /
# Coggan ATL/CTL). Not a full ka/kf performance model.
TAU_CTL_DAYS = 42.0
TAU_ATL_DAYS = 7.0

# Conservative TSS proxy when ICU load field missing (hours × IF²×100 ≈ hours×50 at IF≈0.7)
TSS_PER_HOUR_PROXY = 50.0
STRENGTH_TSS_PER_HOUR = 35.0

# Lookback for seeding Banister when wellness sparse
DEFAULT_LOOKBACK_DAYS = 90
DEFAULT_HORIZON_DAYS = 28

_ACTIVITY_LOAD_FIELDS = (
    _ACTIVITY_FIELDS
    + ",icu_training_load,TrainingLoad,training_load,tss,icu_tss,load"
)

CITATIONS: list[dict[str, str]] = [
    {
        "id": "banister1975",
        "cite": (
            "Banister EW et al. A systems model of training for athletic performance. "
            "Aust J Sports Med 1975 — impulse–response (fitness/fatigue) family."
        ),
        "note": "CTL/ATL/TSB i praksis er en forenklet EWMA-variant, ikke full ka/kf-prediktor.",
    },
    {
        "id": "morton1990",
        "cite": (
            "Morton RH, Fitz-Clarke JR, Banister EW. Modeling human performance in running. "
            "J Appl Physiol 1990;69:1171–1177."
        ),
        "note": "Peer-reviewed IR-modellering; parameterusikkerhet er reell.",
    },
    {
        "id": "hellard2006",
        "cite": (
            "Hellard P et al. Assessing the limitations of the Banister model… "
            "J Sports Sci 2006 — bred CI / ill-conditioning hos elite svømmere."
        ),
        "note": "Derfor confidence-bånd og ærlig «ikke race-fasit».",
    },
    {
        "id": "ioc2016",
        "cite": (
            "Soligard T et al. IOC consensus statement: load in sport and risk of injury. "
            "BJSM 2016."
        ),
        "note": "Load-spike / under-recovery som skaderisiko-kontekst — ikke diagnose.",
    },
    {
        "id": "gabbett2016",
        "cite": (
            "Gabbett TJ. The training–injury prevention paradox. BJSM 2016 — "
            "ACWR-soner ofte sitert ~0.8–1.3 tryggere; >1.5 høyere risiko."
        ),
        "note": "Soft signal; individuell kontekst (søvn, smerte) vinner.",
    },
    {
        "id": "seiler2010",
        "cite": (
            "Seiler S. What is best practice for training intensity distribution…? "
            "Int J Sports Physiol Perform 2010 — ~80/20-retning."
        ),
        "note": "Intensitetsfordeling vs plan — retning, ikke ukentlig lov.",
    },
]


def _k(tau: float) -> float:
    return 1.0 - math.exp(-1.0 / max(tau, 1e-6))


K_CTL = _k(TAU_CTL_DAYS)
K_ATL = _k(TAU_ATL_DAYS)


def ewma_step(prev: float, daily_load: float, k: float) -> float:
    """One-day Banister-family EWMA update."""
    return prev + (float(daily_load) - prev) * k


def run_ewma(
    daily_loads: dict[str, float],
    *,
    start: date,
    end: date,
    ctl0: float = 0.0,
    atl0: float = 0.0,
) -> list[dict[str, Any]]:
    """Iterate inclusive [start, end]; missing days = 0 load."""
    if end < start:
        start, end = end, start
    ctl = float(ctl0)
    atl = float(atl0)
    out: list[dict[str, Any]] = []
    day = start
    while day <= end:
        iso = day.isoformat()
        load = float(daily_loads.get(iso) or 0.0)
        ctl = ewma_step(ctl, load, K_CTL)
        atl = ewma_step(atl, load, K_ATL)
        tsb = ctl - atl
        out.append(
            {
                "date": iso,
                "label": f"{iso[8:10]}.{iso[5:7]}",
                "ctl": round(ctl, 1),
                "atl": round(atl, 1),
                "tsb": round(tsb, 1),
                "load": round(load, 1),
            }
        )
        day += timedelta(days=1)
    return out


def estimate_tss_hours(hours: float, *, sport: str | None = None) -> float:
    """Duration → TSS proxy when ICU load missing. Conservative, documented."""
    h = max(0.0, float(hours or 0.0))
    sp = (sport or "").lower()
    if sp in ("strength", "weighttraining", "workout"):
        return round(h * STRENGTH_TSS_PER_HOUR, 1)
    return round(h * TSS_PER_HOUR_PROXY, 1)


def activity_tss(act: dict[str, Any]) -> float | None:
    """Prefer ICU training load / TSS fields; else duration proxy."""
    for key in (
        "icu_training_load",
        "TrainingLoad",
        "training_load",
        "icu_tss",
        "tss",
        "load",
    ):
        raw = act.get(key)
        if raw is None or raw == "":
            continue
        try:
            v = float(raw)
        except (TypeError, ValueError):
            continue
        if v >= 0:
            return round(v, 1)
    hours = None
    for field in ("moving_time", "elapsed_time", "duration", "icu_coach_time"):
        if act.get(field) is not None and act.get(field) != "":
            hours = parse_duration_hours(act.get(field), field)
            if hours is not None:
                break
    if hours is None:
        return None
    sport = str(act.get("type") or act.get("sport") or "")
    return estimate_tss_hours(hours, sport=sport)


def daily_tss_from_activities(
    activities: list[dict[str, Any]],
    start: date,
    end: date,
) -> dict[str, float]:
    buckets: dict[str, float] = {}
    day = start
    while day <= end:
        buckets[day.isoformat()] = 0.0
        day += timedelta(days=1)
    for act in activities or []:
        d = _activity_local_date(act)
        if d is None or d < start or d > end:
            continue
        tss = activity_tss(act)
        if tss is None:
            continue
        iso = d.isoformat()
        if iso in buckets:
            buckets[iso] = round(buckets[iso] + float(tss), 1)
    return buckets


def planned_session_tss(row: dict[str, Any]) -> float:
    """Projected load from planned_sessions — duration (± optional tss in row)."""
    for key in ("tss", "projected_tss", "load"):
        raw = row.get(key)
        if raw is None or raw == "":
            continue
        try:
            v = float(raw)
            if v >= 0:
                return round(v, 1)
        except (TypeError, ValueError):
            pass
    try:
        dur_m = row.get("duration_minutes")
        hours = float(dur_m) / 60.0 if dur_m is not None else 0.0
    except (TypeError, ValueError):
        hours = 0.0
    sport = str(row.get("sport") or row.get("discipline") or "")
    return estimate_tss_hours(hours, sport=sport)


def daily_tss_from_planned(
    sessions: list[dict[str, Any]] | None,
    start: date,
    end: date,
    *,
    today: date | None = None,
) -> dict[str, float]:
    """Future planned load only (session_date >= today). Past planned ignored."""
    today = today or date.today()
    buckets: dict[str, float] = {}
    day = start
    while day <= end:
        buckets[day.isoformat()] = 0.0
        day += timedelta(days=1)
    for row in sessions or []:
        raw = str(row.get("session_date") or row.get("date") or "")[:10]
        if not raw:
            continue
        try:
            d = date.fromisoformat(raw)
        except ValueError:
            continue
        if d < today or d < start or d > end:
            continue
        iso = d.isoformat()
        if iso not in buckets:
            continue
        buckets[iso] = round(buckets[iso] + planned_session_tss(row), 1)
    return buckets


def fetch_activities_with_load(
    api_key: str,
    athlete_id: str,
    oldest: str,
    newest: str,
    *,
    timeout: int = 12,
) -> list[dict[str, Any]]:
    """Activities including training-load fields (Beta only — does not change shared fetch)."""
    key = (api_key or "").strip()
    aid = (athlete_id or "").strip()
    if not key or not aid:
        return []
    qs = urllib.parse.urlencode(
        {
            "oldest": oldest[:10],
            "newest": newest[:10],
            "limit": "100",
            "fields": _ACTIVITY_LOAD_FIELDS,
        }
    )
    url = f"{API_BASE}/athlete/{aid}/activities?{qs}"
    try:
        data = _http_get_json(url, key, timeout=timeout)
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        ValueError,
        json.JSONDecodeError,
        OSError,
    ):
        # Soft-fail → duration-only via shared fetcher
        try:
            return fetch_intervals_activities(key, aid, oldest[:10], newest[:10])
        except Exception:  # noqa: BLE001
            return []
    if isinstance(data, dict):
        data = data.get("activities") or data.get("data") or []
    if not isinstance(data, list):
        return []
    return [a for a in data if isinstance(a, dict)]


def risk_band_from_acwr(ratio: float | None) -> dict[str, Any]:
    """IOC/Gabbett-ish soft bands — never medical diagnosis."""
    if ratio is None:
        return {
            "band": "unknown",
            "label_nb": "Ukjent",
            "acwr": None,
            "note_nb": "Mangler ATL/CTL for ACWR.",
        }
    if ratio < 0.8:
        band, label = "underload", "Lav akutt load"
    elif ratio < ACWR_SOFT:
        band, label = "ok", "I tryggere sone"
    elif ratio < ACWR_HARD:
        band, label = "elevated", "Forhøyet (myk)"
    else:
        band, label = "high", "Høy (hard)"
    return {
        "band": band,
        "label_nb": label,
        "acwr": ratio,
        "threshold_soft": ACWR_SOFT,
        "threshold_hard": ACWR_HARD,
        "note_nb": (
            f"ATL:CTL ≈ {ratio:.2f}. Soft signal (IOC/Gabbett) — "
            "ikke skadediagnose. Human Coach bekrefter før planendring."
        ),
    }


def race_form_estimate(
    *,
    ctl: float | None,
    atl: float | None,
    tsb: float | None,
    goal_race_date: str | None,
    projected_ctl_at_goal: float | None,
    data_quality: str,
    today: date | None = None,
) -> dict[str, Any]:
    """Honest race-readiness sketch with confidence — not a finish-time predictor."""
    today = today or date.today()
    days = days_to_goal({"goal_race_date": goal_race_date}, today=today)
    ratio = acwr_ratio(atl, ctl)
    freshness = "unknown"
    if tsb is not None:
        if tsb >= 10:
            freshness = "fresh"
        elif tsb >= -10:
            freshness = "neutral"
        else:
            freshness = "fatigued"

    conf = "lav"
    if data_quality == "wellness+planned" and days is not None and days > 0:
        conf = "medium"
    if data_quality == "wellness+planned" and ctl is not None and ctl >= 20:
        conf = "medium" if days and days > 60 else "høy" if days and days <= 60 else "medium"
    if data_quality in ("sparse", "none"):
        conf = "lav"

    summary_parts = []
    if days is None:
        summary_parts.append("Ingen måldato — kan ikke ankre race-form.")
    elif days < 0:
        summary_parts.append("Måldato er passert.")
    else:
        summary_parts.append(f"{days} dager til mål.")
    if ctl is not None:
        summary_parts.append(f"CTL nå ~{ctl:.0f}.")
    if projected_ctl_at_goal is not None and days and days > 0:
        summary_parts.append(
            f"Ved planlagt load: CTL ~{projected_ctl_at_goal:.0f} på måldato "
            "(projeksjon, ikke fasit)."
        )
    if freshness == "fatigued":
        summary_parts.append("TSB negativ — mer fatigue enn fitness akkurat nå.")
    elif freshness == "fresh":
        summary_parts.append("TSB positiv — relativt fersk ift. kronisk load.")

    summary_parts.append(
        "TSB/CTL er ferskhets-/load-indikatorer (Banister-familie), "
        "ikke prediksjon av race-tid. Hellard 2006: bred usikkerhet."
    )

    return {
        "goal_race_date": goal_race_date,
        "days_to_goal": days,
        "ctl_now": ctl,
        "atl_now": atl,
        "tsb_now": tsb,
        "freshness": freshness,
        "acwr": ratio,
        "projected_ctl_at_goal": projected_ctl_at_goal,
        "confidence": conf,
        "confidence_band_nb": {
            "lav": "Lav — tynt datasett eller manglende plan/wellness.",
            "medium": "Medium — wellness + plan, men IR-parametre er usikre.",
            "høy": "Høyere relativ — nær mål med stabil load-historikk (fortsatt ikke fasit).",
        }.get(conf, conf),
        "summary_nb": " ".join(summary_parts),
        "auto_apply": False,
    }


def ease_scenario(
    *,
    planned_loads: dict[str, float],
    today: date,
    horizon_days: int,
    ctl0: float,
    atl0: float,
    fraction: float = 0.8,
) -> dict[str, Any]:
    """«Hvis jeg letter X% neste 2 uker» — proposal only, never applied."""
    end = today + timedelta(days=max(1, horizon_days) - 1)
    eased: dict[str, float] = {}
    for iso, load in planned_loads.items():
        try:
            d = date.fromisoformat(iso)
        except ValueError:
            continue
        if today <= d <= end:
            eased[iso] = round(float(load) * fraction, 1)
        else:
            eased[iso] = float(load)
    base = run_ewma(planned_loads, start=today, end=end, ctl0=ctl0, atl0=atl0)
    alt = run_ewma(eased, start=today, end=end, ctl0=ctl0, atl0=atl0)
    pct = int(round((1.0 - fraction) * 100))
    return {
        "id": f"ease_{pct}pct_{horizon_days}d",
        "title_nb": f"Hvis du letter {pct} % de neste {horizon_days} dagene…",
        "fraction": fraction,
        "horizon_days": horizon_days,
        "baseline_end": base[-1] if base else None,
        "eased_end": alt[-1] if alt else None,
        "series_planlagt": [
            {**p, "series_kind": "planned"} for p in base
        ],
        "series_eased": [{**p, "series_kind": "scenario"} for p in alt],
        "proposal_only": True,
        "auto_apply": False,
        "human_coach_confirm": True,
        "note_nb": (
            "Kun scenario. Ingen plan omskrives her. "
            "Åpne Coach → forslag → bekreft hvis du vil handle."
        ),
    }


def _point_from_wellness(p: dict[str, Any]) -> dict[str, Any]:
    ctl = p.get("ctl")
    atl = p.get("atl")
    tsb = None
    if ctl is not None and atl is not None:
        tsb = round(float(ctl) - float(atl), 1)
    return {
        "date": p.get("date"),
        "label": p.get("label")
        or (
            f"{str(p.get('date'))[8:10]}.{str(p.get('date'))[5:7]}"
            if p.get("date")
            else ""
        ),
        "ctl": ctl,
        "atl": atl,
        "tsb": tsb,
        "series_kind": "executed",
        "source": "intervals_wellness",
    }


def build_beta_forecasts(
    *,
    athlete: dict[str, Any],
    secrets: dict[str, Any] | None,
    planned_sessions: list[dict[str, Any]] | None,
    today: date | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
) -> dict[str, Any]:
    """Assemble Beta payload: trajectories, risk, race form, scenario, citations."""
    today = today or date.today()
    past_start = today - timedelta(days=max(7, lookback_days) - 1)
    future_end = today + timedelta(days=max(1, horizon_days) - 1)
    goal = (athlete or {}).get("goal_race_date")
    # Extend projection to goal when within ~180d
    days_goal = days_to_goal(athlete or {}, today=today)
    proj_end = future_end
    if days_goal is not None and 0 < days_goal <= 180:
        proj_end = max(future_end, today + timedelta(days=days_goal))

    wellness = resolve_wellness_bundle(
        secrets,
        days=lookback_days,
        today=today,
        include_body=False,
        start=past_start,
        end=today,
    )
    load_sum = wellness.get("load_wellness") or {}
    wl_points_raw = (wellness.get("load_series") or {}).get("points") or []
    past_points = [_point_from_wellness(p) for p in wl_points_raw]

    key = ((secrets or {}).get("intervals_api_key") or "").strip()
    aid = ((secrets or {}).get("intervals_athlete_id") or "").strip()
    activities: list[dict[str, Any]] = []
    act_error = None
    if key and aid:
        try:
            activities = fetch_activities_with_load(
                key, aid, past_start.isoformat(), today.isoformat()
            )
        except Exception as exc:  # noqa: BLE001
            act_error = str(exc)[:160]
            activities = []

    past_loads = daily_tss_from_activities(activities, past_start, today)
    planned_loads = daily_tss_from_planned(
        planned_sessions, today, proj_end, today=today
    )

    ctl_now = load_sum.get("ctl")
    atl_now = load_sum.get("atl")
    data_quality = "none"
    computed_past: list[dict[str, Any]] = []

    if past_points and ctl_now is not None and atl_now is not None:
        data_quality = "wellness"
    elif any(v > 0 for v in past_loads.values()):
        # Seed Banister from activities when wellness CTL missing
        computed_past = run_ewma(past_loads, start=past_start, end=today, ctl0=0.0, atl0=0.0)
        for p in computed_past:
            p["series_kind"] = "executed"
            p["source"] = "banister_from_activities"
        if computed_past:
            ctl_now = computed_past[-1]["ctl"]
            atl_now = computed_past[-1]["atl"]
            past_points = [
                {
                    "date": p["date"],
                    "label": p["label"],
                    "ctl": p["ctl"],
                    "atl": p["atl"],
                    "tsb": p["tsb"],
                    "series_kind": "executed",
                    "source": "banister_from_activities",
                }
                for p in computed_past
            ]
            data_quality = "activities"
    else:
        past_points = past_points  # may be empty

    if ctl_now is not None and atl_now is not None and any(
        v > 0 for v in planned_loads.values()
    ):
        if data_quality == "wellness":
            data_quality = "wellness+planned"
        elif data_quality == "activities":
            data_quality = "activities+planned"
    elif data_quality in ("wellness", "activities") and not any(
        v > 0 for v in planned_loads.values()
    ):
        pass
    elif not past_points:
        data_quality = "sparse" if planned_loads else "none"

    tsb_now = None
    if ctl_now is not None and atl_now is not None:
        tsb_now = round(float(ctl_now) - float(atl_now), 1)

    future_points: list[dict[str, Any]] = []
    projected_ctl_goal = None
    if ctl_now is not None and atl_now is not None:
        future_points = run_ewma(
            planned_loads,
            start=today,
            end=proj_end,
            ctl0=float(ctl_now),
            atl0=float(atl_now),
        )
        for p in future_points:
            p["series_kind"] = "planned"
            p["source"] = "planned_sessions"
            p["label_nb"] = "planlagt"
        if goal and days_goal is not None and days_goal >= 0:
            g_iso = str(goal)[:10]
            match = next((p for p in future_points if p["date"] == g_iso), None)
            if match:
                projected_ctl_goal = match["ctl"]
            elif future_points and days_goal > 0:
                # last projected day before goal
                projected_ctl_goal = future_points[-1]["ctl"]

    ratio = acwr_ratio(
        float(atl_now) if atl_now is not None else None,
        float(ctl_now) if ctl_now is not None else None,
    )
    risk = risk_band_from_acwr(ratio)

    # Volume compliance sketch — hours executed vs planned (same window overlap)
    exec_hours = round(sum(past_loads.values()) / TSS_PER_HOUR_PROXY, 1) if past_loads else 0.0
    # Better: sum activity durations when available
    if activities:
        h_sum = 0.0
        for act in activities:
            for field in ("moving_time", "elapsed_time", "duration"):
                if act.get(field) is not None and act.get(field) != "":
                    h = parse_duration_hours(act.get(field), field)
                    if h is not None:
                        h_sum += h
                        break
        exec_hours = round(h_sum, 1)
    plan_hours = 0.0
    for row in planned_sessions or []:
        raw = str(row.get("session_date") or "")[:10]
        try:
            d = date.fromisoformat(raw)
        except ValueError:
            continue
        if d < today or d > future_end:
            continue
        try:
            plan_hours += float(row.get("duration_minutes") or 0) / 60.0
        except (TypeError, ValueError):
            pass
    plan_hours = round(plan_hours, 1)

    scenario = None
    if ctl_now is not None and atl_now is not None:
        scenario = ease_scenario(
            planned_loads=planned_loads,
            today=today,
            horizon_days=min(14, horizon_days),
            ctl0=float(ctl_now),
            atl0=float(atl_now),
            fraction=0.8,
        )

    race = race_form_estimate(
        ctl=float(ctl_now) if ctl_now is not None else None,
        atl=float(atl_now) if atl_now is not None else None,
        tsb=tsb_now,
        goal_race_date=goal,
        projected_ctl_at_goal=projected_ctl_goal,
        data_quality=data_quality if data_quality != "none" else "sparse",
        today=today,
    )

    recovery = wellness.get("recovery_signals") or {}

    return {
        "experimental": True,
        "auto_apply": False,
        "human_coach_confirm_required": True,
        "as_of": today.isoformat(),
        "windows": {
            "past_start": past_start.isoformat(),
            "past_end": today.isoformat(),
            "future_end": proj_end.isoformat(),
            "horizon_days": horizon_days,
            "lookback_days": lookback_days,
        },
        "data_quality": data_quality,
        "truth": {
            "executed": "intervals_activities + intervals_wellness",
            "planned": "planned_sessions",
            "ctl_atl_past": (
                "intervals_wellness"
                if any(p.get("source") == "intervals_wellness" for p in past_points)
                else "banister_from_activities"
                if past_points
                else "none"
            ),
            "ctl_atl_future": "banister_projection_from_planned_sessions",
            "note_nb": (
                "Fortid: ICU-aktiviteter / wellness. Fremtid: planned_sessions (planlagt). "
                "Ingen LLM-inventerte CTL-tall. Beta omskriver ikke planen."
            ),
        },
        "load_now": {
            "ctl": ctl_now,
            "atl": atl_now,
            "tsb": tsb_now,
            "acwr": ratio,
            "available": ctl_now is not None or atl_now is not None,
            "source": load_sum.get("date") and "intervals_wellness" or data_quality,
        },
        "charts": {
            "ctl_atl_tsb": {
                "available": bool(past_points or future_points),
                "past": past_points,
                "future": future_points,
                "label_past_nb": "Gjennomført (ICU)",
                "label_future_nb": "Planlagt (planned_sessions)",
                "note_nb": (
                    "Stiplede / planlagt-serier = projeksjon fra planlagt load "
                    f"(TSS-proxy {TSS_PER_HOUR_PROXY}/t når ICU-load mangler)."
                ),
            },
            "acwr_bands": {
                "soft": ACWR_SOFT,
                "hard": ACWR_HARD,
                "current": risk,
            },
        },
        "overload_risk": risk,
        "race_form": race,
        "volume": {
            "executed_hours_lookback": exec_hours,
            "planned_hours_horizon": plan_hours,
            "series_kind_executed": "executed",
            "series_kind_planned": "planned",
            "note_nb": (
                "Compliance/volum: gjennomført = ICU-aktiviteter; "
                "fremover = planned_sessions."
            ),
        },
        "recovery_signals": {
            "available": bool(recovery.get("available")),
            "sleep_avg_hours": recovery.get("sleep_avg_hours"),
            "hrv_latest": recovery.get("hrv_latest"),
            "hrv_avg_7d": recovery.get("hrv_avg_7d"),
            "rhr_latest": recovery.get("rhr_latest"),
            "as_signals_only": True,
            "note_nb": recovery.get("note")
            or "Wellness = signaler, ikke absolutt sannhet.",
        },
        "scenario_ease": scenario,
        "citations": CITATIONS,
        "coach_notes_nb": (
            "Beta er eksperimentell. ACWR/CTL er load-styringssignaler "
            "(IOC/Gabbett; Banister-familie). Ingen autonom planendring — "
            "Human Coach: forslag → bekreft."
        ),
        "fetch_error": bool(wellness.get("fetch_error") or act_error),
        "fetch_error_detail": wellness.get("fetch_error_detail") or act_error,
        "intervals_linked": bool(key and aid),
    }
