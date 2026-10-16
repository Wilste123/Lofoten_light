#!/usr/bin/env python3
"""TB-Score: time-aware totalbelastning / readiness from Intervals wellness + activities."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

from analyze_tp_export import find_column, parse_date, parse_float

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "docs/athlete/readiness-config.json"


@dataclass
class DayInputs:
    date: datetime
    ctl: float | None = None
    atl: float | None = None
    hrv: float | None = None
    resting_hr: float | None = None
    sleep_hours: float | None = None
    sleep_score: float | None = None
    soreness: float | None = None
    fatigue: float | None = None
    stress: float | None = None
    injury: float | None = None


@dataclass
class ActivityPoint:
    start: datetime
    end: datetime
    load: float
    sport: str
    intensity: float | None = None


@dataclass
class AcuteTrainingContext:
    hours_since_last: float | None
    last_load: float | None
    last_sport: str | None
    last_end: datetime | None
    load_24h: float
    load_48h: float
    sessions_24h: int


@dataclass
class ComponentScore:
    key: str
    label: str
    score: float | None
    detail: str


@dataclass
class ReadinessResult:
    score: int
    band: str
    emoji: str
    recommendation: str
    components: list[ComponentScore] = field(default_factory=list)
    life_adjustment: int = 0
    tsb: float | None = None
    atl_ctl_ratio: float | None = None
    as_of: datetime | None = None
    wellness_date: date | None = None
    acute: AcuteTrainingContext | None = None


def load_config(path: Path | None) -> dict[str, Any]:
    p = path or DEFAULT_CONFIG
    if not p.is_file():
        return {
            "timezone": "Europe/Oslo",
            "sleep_target_hours": 7.5,
            "baseline_window_days": 21,
            "weights": {
                "load_chronic": 0.3,
                "recovery_time": 0.25,
                "acute_window": 0.1,
                "hrv": 0.22,
                "rhr": 0.13,
                "sleep": 0.1,
                "subjective": 0.0,
            },
            "life_adjustments": {},
            "bands": {"green_min": 78, "yellow_min": 58},
        }
    return json.loads(p.read_text(encoding="utf-8"))


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def parse_datetime_flexible(raw: str) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    if "T" in raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    return parse_date(raw)


def score_load_balance(ctl: float, atl: float) -> float:
    ratio = atl / ctl
    if ratio <= 1.15:
        return 92.0
    if ratio <= 1.35:
        return 82.0
    if ratio <= 1.6:
        return 70.0
    if ratio <= 2.0:
        return 55.0
    if ratio <= 2.5:
        return 40.0
    if ratio <= 3.0:
        return 28.0
    return max(12.0, 35.0 - (ratio - 3.0) * 8.0)


def score_tsb(tsb: float) -> float:
    if tsb <= -55:
        return clamp(18.0 + (tsb + 55) * 0.35)
    if tsb <= -30:
        return 18.0 + (tsb + 55) * 0.9
    if tsb <= -10:
        return 40.0 + (tsb + 30) * 1.1
    if tsb <= 5:
        return 62.0 + (tsb + 10) * 1.4
    if tsb <= 20:
        return 83.0 + (tsb - 5) * 0.6
    return clamp(92.0 + (tsb - 20) * 0.25)


def score_hrv_ratio(ratio: float) -> float:
    if ratio >= 1.08:
        return clamp(88.0 + (ratio - 1.08) * 40.0)
    if ratio >= 0.98:
        return 78.0 + (ratio - 0.98) * 100.0
    if ratio >= 0.90:
        return 58.0 + (ratio - 0.90) * 250.0
    if ratio >= 0.80:
        return 35.0 + (ratio - 0.80) * 230.0
    return clamp(20.0 + ratio * 18.0)


def score_rhr_delta(delta: float) -> float:
    if delta <= -2:
        return 90.0
    if delta <= 0:
        return 82.0 - delta * 2.0
    if delta <= 3:
        return 82.0 - delta * 8.0
    if delta <= 6:
        return 58.0 - (delta - 3) * 10.0
    return clamp(25.0 - (delta - 6) * 5.0)


def score_sleep_hours(hours: float, target: float) -> float:
    ratio = hours / target
    if ratio >= 1.0:
        return clamp(80.0 + (ratio - 1.0) * 40.0)
    if ratio >= 0.93:
        return 70.0 + (ratio - 0.93) * 140.0
    if ratio >= 0.80:
        return 45.0 + (ratio - 0.80) * 192.0
    return clamp(25.0 + ratio * 25.0)


def score_sleep_garmin(score: float) -> float:
    return clamp(float(score))


def score_subjective(values: list[float]) -> float:
    if not values:
        return 70.0
    avg = sum(values) / len(values)
    return clamp(100.0 - (avg - 1.0) * 22.0)


def hours_needed_after_load(load: float, cfg: dict[str, Any]) -> float:
    rh = cfg.get("recovery_hours") or {}
    easy = float(rh.get("load_tier_easy", 35))
    mod = float(rh.get("load_tier_moderate", 70))
    hard = float(rh.get("load_tier_hard", 120))
    if load < easy:
        return float(rh.get("hours_after_easy", 8))
    if load < mod:
        return float(rh.get("hours_after_moderate", 18))
    if load < hard:
        return float(rh.get("hours_after_hard", 30))
    base = float(rh.get("hours_after_very_hard_base", 42))
    extra = float(rh.get("very_hard_extra_per_tss", 0.08))
    return base + max(0.0, load - hard) * extra


def score_recovery_time(hours_since: float, last_load: float, cfg: dict[str, Any]) -> float:
    need = hours_needed_after_load(last_load, cfg)
    if need <= 0:
        return 85.0
    frac = hours_since / need
    if frac >= 1.2:
        return 95.0
    if frac >= 1.0:
        return 82.0 + (frac - 1.0) * 65.0
    if frac >= 0.5:
        return 45.0 + (frac - 0.5) * 74.0
    return clamp(20.0 + frac * 50.0)


def score_acute_window(ctx: AcuteTrainingContext, cfg: dict[str, Any]) -> float:
    acute = cfg.get("acute_load") or {}
    green = float(acute.get("load_24h_green", 80))
    red = float(acute.get("load_24h_red", 180))
    l24 = ctx.load_24h
    if l24 <= green:
        base = 92.0
    elif l24 >= red:
        base = 22.0
    else:
        base = 92.0 - (l24 - green) / (red - green) * 70.0
    min_h = float(acute.get("min_hours_after_hard_session", 14))
    hard_tss = float(acute.get("hard_session_tss", 90))
    if (
        ctx.hours_since_last is not None
        and ctx.last_load is not None
        and ctx.last_load >= hard_tss
        and ctx.hours_since_last < min_h
    ):
        gap = ctx.hours_since_last / min_h
        base -= (1.0 - gap) * 25.0
    return clamp(base)


def rolling_median(
    series: list[float | None], end_index: int, window: int
) -> float | None:
    start = max(0, end_index - window)
    chunk = [v for v in series[start:end_index] if v is not None]
    if len(chunk) < 5:
        return None
    return float(median(chunk))


def band_for_score(score: int, cfg: dict[str, Any]) -> tuple[str, str, str]:
    bands = cfg.get("bands") or {}
    green = int(bands.get("green_min", 78))
    yellow = int(bands.get("yellow_min", 58))
    if score >= green:
        return (
            "grønn",
            "🟢",
            "Planlagt kvalitet ok; ikke legg på ekstra «fordi klokken er grønn».",
        )
    if score >= yellow:
        return (
            "gul",
            "🟡",
            "Plan B på intervall/threshold; ellers Z1–Z2. Én hard økt denne uken.",
        )
    return (
        "rød",
        "🔴",
        "Recovery: søvn, rolig bevegelse, styrke lett. Ingen VO2/FTP/CSS-test.",
    )


def parse_wellness_rows(
    rows: list[dict[str, str]], fields: list[str]
) -> list[DayInputs]:
    cols = {
        "date": find_column(fields, ["date", "id", "day"]),
        "ctl": find_column(fields, ["ctl"]),
        "atl": find_column(fields, ["atl"]),
        "hrv": find_column(fields, ["hrv"]),
        "restingHR": find_column(fields, ["restingHR", "restinghr"]),
        "sleepSecs": find_column(fields, ["sleepSecs", "sleepsecs"]),
        "sleepScore": find_column(fields, ["sleepScore", "sleepscore"]),
        "soreness": find_column(fields, ["soreness"]),
        "fatigue": find_column(fields, ["fatigue"]),
        "stress": find_column(fields, ["stress"]),
        "injury": find_column(fields, ["injury"]),
    }
    if not cols["date"]:
        raise ValueError("Missing date column in wellness CSV")

    out: list[DayInputs] = []
    for r in rows:
        d = parse_date(r.get(cols["date"], ""))
        if not d:
            continue
        sleep_h = None
        if cols["sleepSecs"]:
            sec = parse_float(r.get(cols["sleepSecs"], ""))
            if sec is not None:
                sleep_h = sec / 3600.0
        out.append(
            DayInputs(
                date=d,
                ctl=parse_float(r.get(cols["ctl"], "")) if cols["ctl"] else None,
                atl=parse_float(r.get(cols["atl"], "")) if cols["atl"] else None,
                hrv=parse_float(r.get(cols["hrv"], "")) if cols["hrv"] else None,
                resting_hr=(
                    parse_float(r.get(cols["restingHR"], ""))
                    if cols["restingHR"]
                    else None
                ),
                sleep_hours=sleep_h,
                sleep_score=(
                    parse_float(r.get(cols["sleepScore"], ""))
                    if cols["sleepScore"]
                    else None
                ),
                soreness=(
                    parse_float(r.get(cols["soreness"], ""))
                    if cols["soreness"]
                    else None
                ),
                fatigue=(
                    parse_float(r.get(cols["fatigue"], ""))
                    if cols["fatigue"]
                    else None
                ),
                stress=(
                    parse_float(r.get(cols["stress"], ""))
                    if cols["stress"]
                    else None
                ),
                injury=(
                    parse_float(r.get(cols["injury"], ""))
                    if cols["injury"]
                    else None
                ),
            )
        )
    out.sort(key=lambda x: x.date)
    return out


def parse_activity_points(
    rows: list[dict[str, str]], fields: list[str]
) -> list[ActivityPoint]:
    start_col = find_column(
        fields,
        ["start_date_local", "start_date", "date", "start_time"],
    )
    load_col = find_column(
        fields,
        ["icu_training_load", "training_load", "load", "tss"],
    )
    elapsed_col = find_column(
        fields,
        ["elapsed_time", "moving_time", "duration", "icu_recording_time"],
    )
    type_col = find_column(fields, ["type", "sport"])
    if_col = find_column(fields, ["icu_intensity", "intensity", "if"])
    if not start_col:
        raise ValueError("Missing activity start column")

    points: list[ActivityPoint] = []
    for r in rows:
        start = parse_datetime_flexible(r.get(start_col, ""))
        if not start:
            continue
        if start.tzinfo is not None:
            start = start.replace(tzinfo=None)
        load = parse_float(r.get(load_col, "")) if load_col else None
        if load is None:
            continue
        elapsed = parse_float(r.get(elapsed_col, "")) if elapsed_col else None
        if elapsed is None or elapsed <= 0:
            elapsed = 3600.0
        end = start + timedelta(seconds=elapsed)
        sport = (r.get(type_col, "") if type_col else "") or "?"
        intensity = parse_float(r.get(if_col, "")) if if_col else None
        points.append(
            ActivityPoint(
                start=start,
                end=end,
                load=load,
                sport=sport.strip(),
                intensity=intensity,
            )
        )
    points.sort(key=lambda p: p.end)
    return points


def acute_context_at(
    activities: list[ActivityPoint], as_of: datetime
) -> AcuteTrainingContext:
    if as_of.tzinfo is not None:
        as_of = as_of.replace(tzinfo=None)
    done = [a for a in activities if a.end <= as_of]
    load_24h = 0.0
    load_48h = 0.0
    sessions_24h = 0
    t24 = as_of - timedelta(hours=24)
    t48 = as_of - timedelta(hours=48)
    for a in done:
        if a.end > t48:
            load_48h += a.load
        if a.end > t24:
            load_24h += a.load
            sessions_24h += 1
    last = done[-1] if done else None
    hours_since = None
    if last:
        hours_since = (as_of - last.end).total_seconds() / 3600.0
    return AcuteTrainingContext(
        hours_since_last=hours_since,
        last_load=last.load if last else None,
        last_sport=last.sport if last else None,
        last_end=last.end if last else None,
        load_24h=load_24h,
        load_48h=load_48h,
        sessions_24h=sessions_24h,
    )


def wellness_index_for(days: list[DayInputs], as_of: datetime) -> int:
    target = as_of.date()
    idx = 0
    for i, d in enumerate(days):
        if d.date.date() <= target:
            idx = i
    return idx


def _add_weighted(
    components: list[ComponentScore],
    weighted_sum: float,
    weight_total: float,
    key: str,
    label: str,
    score: float | None,
    detail: str,
    weight: float,
) -> tuple[float, float]:
    if score is None or weight <= 0:
        return weighted_sum, weight_total
    components.append(
        ComponentScore(key, label, round(score, 1), detail),
    )
    return weighted_sum + score * weight, weight_total + weight


def compute_readiness_core(
    day: DayInputs,
    day_index: int,
    days: list[DayInputs],
    cfg: dict[str, Any],
    acute: AcuteTrainingContext | None,
    include_subjective: bool,
) -> ReadinessResult:
    window = int(cfg.get("baseline_window_days", 21))
    weights = cfg.get("weights") or {}
    target_sleep = float(cfg.get("sleep_target_hours", 7.5))
    hrv_series = [d.hrv for d in days]
    rhr_series = [d.resting_hr for d in days]

    components: list[ComponentScore] = []
    weighted_sum = 0.0
    weight_total = 0.0
    tsb: float | None = None
    ratio: float | None = None

    load_score: float | None = None
    if day.ctl is not None and day.atl is not None and day.ctl >= 1:
        tsb = day.ctl - day.atl
        ratio = day.atl / day.ctl
        s_tsb = score_tsb(tsb)
        s_ratio = score_load_balance(day.ctl, day.atl)
        load_score = 0.45 * s_tsb + 0.55 * s_ratio
        weighted_sum, weight_total = _add_weighted(
            components,
            weighted_sum,
            weight_total,
            "load_chronic",
            "Kronisk form (CTL/ATL)",
            load_score,
            f"CTL {day.ctl:.0f}, ATL {day.atl:.0f}, TSB {tsb:+.0f}, ATL/CTL {ratio:.2f}",
            float(weights.get("load_chronic", weights.get("load", 0.3))),
        )
    elif day.atl is not None and (day.ctl is None or day.ctl < 1):
        load_score = score_tsb(-day.atl * 0.5)
        weighted_sum, weight_total = _add_weighted(
            components,
            weighted_sum,
            weight_total,
            "load_chronic",
            "Kronisk form (kun ATL)",
            load_score,
            f"ATL {day.atl:.0f} (lav CTL)",
            float(weights.get("load_chronic", weights.get("load", 0.3))),
        )

    if acute and acute.last_load is not None and acute.hours_since_last is not None:
        rec_s = score_recovery_time(acute.hours_since_last, acute.last_load, cfg)
        need = hours_needed_after_load(acute.last_load, cfg)
        last_end = acute.last_end.strftime("%Y-%m-%d %H:%M") if acute.last_end else "?"
        weighted_sum, weight_total = _add_weighted(
            components,
            weighted_sum,
            weight_total,
            "recovery_time",
            "Tid siden siste økt",
            rec_s,
            f"{acute.hours_since_last:.1f} t siden {acute.last_sport} "
            f"(load {acute.last_load:.0f}, ~{need:.0f} t til full restitusjon)",
            float(weights.get("recovery_time", 0.25)),
        )
        aw_s = score_acute_window(acute, cfg)
        weighted_sum, weight_total = _add_weighted(
            components,
            weighted_sum,
            weight_total,
            "acute_window",
            "Akutt vindu (24/48 t)",
            aw_s,
            f"load 24h {acute.load_24h:.0f}, 48h {acute.load_48h:.0f}, "
            f"{acute.sessions_24h} økt(er) siste 24t",
            float(weights.get("acute_window", 0.1)),
        )

    base_hrv = rolling_median(hrv_series, day_index, window)
    if day.hrv is not None and base_hrv and base_hrv > 0:
        hrv_s = score_hrv_ratio(day.hrv / base_hrv)
        weighted_sum, weight_total = _add_weighted(
            components,
            weighted_sum,
            weight_total,
            "hrv",
            "HRV vs baseline",
            hrv_s,
            f"HRV {day.hrv:.0f} vs median {base_hrv:.0f} ({day.hrv / base_hrv:.2f}×)",
            float(weights.get("hrv", 0.22)),
        )

    base_rhr = rolling_median(rhr_series, day_index, window)
    if day.resting_hr is not None and base_rhr is not None:
        delta = day.resting_hr - base_rhr
        rhr_s = score_rhr_delta(delta)
        weighted_sum, weight_total = _add_weighted(
            components,
            weighted_sum,
            weight_total,
            "rhr",
            "Hvilepuls vs baseline",
            rhr_s,
            f"RHR {day.resting_hr:.0f} vs median {base_rhr:.0f} (Δ{delta:+.0f})",
            float(weights.get("rhr", 0.13)),
        )

    sleep_s: float | None = None
    if day.sleep_hours is not None:
        sleep_s = score_sleep_hours(day.sleep_hours, target_sleep)
        detail = f"{day.sleep_hours:.1f} h (mål {target_sleep:.1f} h)"
    elif day.sleep_score is not None:
        sleep_s = score_sleep_garmin(day.sleep_score)
        detail = f"score {day.sleep_score:.0f}"
    if sleep_s is not None:
        weighted_sum, weight_total = _add_weighted(
            components,
            weighted_sum,
            weight_total,
            "sleep",
            "Søvn (natt til wellness-dato)",
            sleep_s,
            detail,
            float(weights.get("sleep", 0.1)),
        )

    subj_w = float(weights.get("subjective", 0.0))
    if include_subjective and subj_w > 0:
        subj_vals = [
            v
            for v in (day.soreness, day.fatigue, day.stress, day.injury)
            if v is not None
        ]
        if subj_vals:
            subj_s = score_subjective(subj_vals)
            weighted_sum, weight_total = _add_weighted(
                components,
                weighted_sum,
                weight_total,
                "subjective",
                "Subjektivt (valgfritt)",
                subj_s,
                f"snitt {sum(subj_vals) / len(subj_vals):.1f}",
                subj_w,
            )

    raw = 50.0 if weight_total <= 0 else weighted_sum / weight_total
    life_adj = sum(
        int(v) for v in (cfg.get("life_adjustments") or {}).values() if isinstance(v, (int, float))
    )
    final = int(round(clamp(raw + life_adj)))
    band, emoji, rec = band_for_score(final, cfg)
    return ReadinessResult(
        score=final,
        band=band,
        emoji=emoji,
        recommendation=rec,
        components=components,
        life_adjustment=life_adj,
        tsb=tsb,
        atl_ctl_ratio=ratio,
        wellness_date=day.date.date(),
        acute=acute,
    )


def compute_readiness_at(
    as_of: datetime,
    days: list[DayInputs],
    activities: list[ActivityPoint] | None,
    cfg: dict[str, Any],
    include_subjective: bool = False,
) -> ReadinessResult:
    idx = wellness_index_for(days, as_of)
    acute = acute_context_at(activities, as_of) if activities else None
    result = compute_readiness_core(
        days[idx], idx, days, cfg, acute, include_subjective
    )
    result.as_of = as_of
    return result


def compute_day_readiness(
    days: list[DayInputs],
    index: int,
    cfg: dict[str, Any],
    include_subjective: bool = False,
) -> ReadinessResult:
    """End-of-day score without activity timestamps (legacy / --daily)."""
    noon = days[index].date.replace(hour=12, minute=0, second=0, microsecond=0)
    return compute_readiness_at(noon, days, None, cfg, include_subjective)


def compute_all(
    days: list[DayInputs],
    cfg: dict[str, Any],
    include_subjective: bool = False,
) -> list[ReadinessResult]:
    return [
        compute_day_readiness(days, i, cfg, include_subjective) for i in range(len(days))
    ]


def resolve_as_of(raw: str | None, cfg: dict[str, Any]) -> datetime:
    tz_name = str(cfg.get("timezone", "Europe/Oslo"))
    tz = ZoneInfo(tz_name)
    if raw is None or raw.lower() in ("now", ""):
        return datetime.now(tz).replace(tzinfo=None)
    if raw.lower() == "noon":
        now = datetime.now(tz)
        return now.replace(hour=12, minute=0, second=0, microsecond=0, tzinfo=None)
    dt = parse_datetime_flexible(raw)
    if not dt:
        raise ValueError(f"Could not parse --at: {raw}")
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def result_to_dict(r: ReadinessResult) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "tb_score": r.score,
        "band": r.band,
        "life_adjustment": r.life_adjustment,
        "tsb": r.tsb,
        "atl_ctl_ratio": r.atl_ctl_ratio,
        "wellness_date": r.wellness_date.isoformat() if r.wellness_date else None,
        "as_of": r.as_of.isoformat(sep=" ") if r.as_of else None,
        "components": [
            {"key": c.key, "label": c.label, "score": c.score, "detail": c.detail}
            for c in r.components
        ],
        "recommendation": r.recommendation,
    }
    if r.acute:
        payload["acute"] = {
            "hours_since_last": r.acute.hours_since_last,
            "last_load": r.acute.last_load,
            "last_sport": r.acute.last_sport,
            "last_end": r.acute.last_end.isoformat(sep=" ") if r.acute.last_end else None,
            "load_24h": r.acute.load_24h,
            "load_48h": r.acute.load_48h,
            "sessions_24h": r.acute.sessions_24h,
        }
    return payload


def format_snapshot_markdown(r: ReadinessResult) -> str:
    as_of_s = r.as_of.strftime("%Y-%m-%d %H:%M") if r.as_of else "?"
    lines = [
        "# TB-Score — snapshot (tidspunkt)\n",
        f"**Kl. {as_of_s}:** **{r.score}/100** {r.emoji} **{r.band.capitalize()}**",
    ]
    if r.life_adjustment:
        lines[1] += f" (livsjustering {r.life_adjustment:+d})"
    lines.append(f"\n{r.recommendation}\n")
    if r.wellness_date:
        lines.append(
            f"\nWellness-grunnlag (morgen/HRV): **{r.wellness_date.isoformat()}**.\n"
        )
    if r.acute and r.acute.last_end:
        lines.append(
            f"Siste økt slutt **{r.acute.last_end.strftime('%Y-%m-%d %H:%M')}** "
            f"({r.acute.hours_since_last:.1f} t siden).\n"
        )
    if r.tsb is not None:
        lines.append(
            f"TSB {r.tsb:+.0f}"
            + (f", ATL/CTL {r.atl_ctl_ratio:.2f}" if r.atl_ctl_ratio else "")
            + ".\n"
        )
    lines.append("\n## Komponenter\n")
    lines.append("| Komponent | Poeng | Detalj |")
    lines.append("|-----------|------:|--------|")
    for c in r.components:
        sc = f"{c.score:.0f}" if c.score is not None else "—"
        lines.append(f"| {c.label} | {sc} | {c.detail} |")
    lines.append(
        "\n---\n*Subjektiv wellness er default **av** (vekt 0). "
        "Bruk `--include-subjective` kun om du vil — ikke stol på det til gaming.*\n"
    )
    return "\n".join(lines)


def format_markdown(
    results: list[ReadinessResult],
    title: str = "TB-Score (daglig, uten klokkeslett)",
    history_days: int = 14,
) -> str:
    if not results:
        return f"# {title}\n\nIngen dager.\n"
    lines = [f"# {title}\n"]
    last = results[-1]
    d = last.wellness_date or (last.as_of.date() if last.as_of else None)
    lines.append(
        f"**Siste ({d}): {last.score}/100** {last.emoji} **{last.band.capitalize()}**"
    )
    if last.life_adjustment:
        lines.append(f" (livsjustering {last.life_adjustment:+d})")
    lines.append(f"\n{last.recommendation}\n")
    lines.append("\n## Historikk (kompakt)\n")
    tail = results[-history_days:] if history_days > 0 else results
    for r in tail:
        d2 = r.wellness_date or (r.as_of.date() if r.as_of else None)
        lines.append(f"- {d2}: **{r.score}** {r.emoji} {r.band}")
    lines.append(
        "\n*For beslutning «nå»: bruk snapshot med `--activities` og `--at now`.*\n"
    )
    return "\n".join(lines)
