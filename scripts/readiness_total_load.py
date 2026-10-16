#!/usr/bin/env python3
"""TB-Score: treningsevne / totalbelastning readiness from Intervals wellness CSV."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

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
class ComponentScore:
    key: str
    label: str
    score: float | None
    detail: str


@dataclass
class ReadinessResult:
    date: datetime
    score: int
    band: str
    emoji: str
    recommendation: str
    components: list[ComponentScore] = field(default_factory=list)
    life_adjustment: int = 0
    tsb: float | None = None
    atl_ctl_ratio: float | None = None
    garmin_readiness: float | None = None


def load_config(path: Path | None) -> dict[str, Any]:
    p = path or DEFAULT_CONFIG
    if not p.is_file():
        return {
            "sleep_target_hours": 7.5,
            "baseline_window_days": 21,
            "weights": {
                "load": 0.35,
                "hrv": 0.25,
                "rhr": 0.15,
                "sleep": 0.15,
                "subjective": 0.1,
            },
            "life_adjustments": {},
            "bands": {"green_min": 78, "yellow_min": 58},
        }
    return json.loads(p.read_text(encoding="utf-8"))


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


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
    # Intervals wellness: 1 = bra, 5 = dårlig (typisk skala)
    return clamp(100.0 - (avg - 1.0) * 22.0)


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
            "Planlagt kvalitet ok; ikke legg på ekstra «fordi du føler deg bra».",
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
        "readiness": find_column(fields, ["readiness"]),
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


def compute_day_readiness(
    days: list[DayInputs],
    index: int,
    cfg: dict[str, Any],
    garmin_readiness: float | None = None,
) -> ReadinessResult:
    day = days[index]
    window = int(cfg.get("baseline_window_days", 21))
    weights = cfg.get("weights") or {}
    target_sleep = float(cfg.get("sleep_target_hours", 7.5))

    hrv_series = [d.hrv for d in days]
    rhr_series = [d.resting_hr for d in days]

    components: list[ComponentScore] = []
    weighted_sum = 0.0
    weight_total = 0.0

    # --- Load (TSB + ATL/CTL) ---
    load_score: float | None = None
    tsb: float | None = None
    ratio: float | None = None
    if day.ctl is not None and day.atl is not None and day.ctl >= 1:
        tsb = day.ctl - day.atl
        ratio = day.atl / day.ctl
        s_tsb = score_tsb(tsb)
        s_ratio = score_load_balance(day.ctl, day.atl)
        load_score = 0.45 * s_tsb + 0.55 * s_ratio
        components.append(
            ComponentScore(
                "load",
                "Trening (form + ratio)",
                round(load_score, 1),
                f"CTL {day.ctl:.0f}, ATL {day.atl:.0f}, TSB {tsb:+.0f}, ATL/CTL {ratio:.2f}",
            )
        )
    elif day.atl is not None and (day.ctl is None or day.ctl < 1):
        load_score = score_tsb(-day.atl * 0.5)
        components.append(
            ComponentScore(
                "load",
                "Trening (kun ATL)",
                round(load_score, 1),
                f"ATL {day.atl:.0f} (lav CTL — forsiktig)",
            )
        )

    if load_score is not None:
        w = float(weights.get("load", 0.35))
        weighted_sum += load_score * w
        weight_total += w

    # --- HRV ---
    base_hrv = rolling_median(hrv_series, index, window)
    if day.hrv is not None and base_hrv and base_hrv > 0:
        hrv_s = score_hrv_ratio(day.hrv / base_hrv)
        components.append(
            ComponentScore(
                "hrv",
                "HRV vs baseline",
                round(hrv_s, 1),
                f"HRV {day.hrv:.0f} vs median {base_hrv:.0f} ({day.hrv / base_hrv:.2f}×)",
            )
        )
        w = float(weights.get("hrv", 0.25))
        weighted_sum += hrv_s * w
        weight_total += w

    # --- RHR ---
    base_rhr = rolling_median(rhr_series, index, window)
    if day.resting_hr is not None and base_rhr is not None:
        delta = day.resting_hr - base_rhr
        rhr_s = score_rhr_delta(delta)
        components.append(
            ComponentScore(
                "rhr",
                "Hvilepuls vs baseline",
                round(rhr_s, 1),
                f"RHR {day.resting_hr:.0f} vs median {base_rhr:.0f} (Δ{delta:+.0f})",
            )
        )
        w = float(weights.get("rhr", 0.15))
        weighted_sum += rhr_s * w
        weight_total += w

    # --- Sleep ---
    sleep_s: float | None = None
    if day.sleep_hours is not None:
        sleep_s = score_sleep_hours(day.sleep_hours, target_sleep)
        components.append(
            ComponentScore(
                "sleep",
                "Søvn",
                round(sleep_s, 1),
                f"{day.sleep_hours:.1f} h (mål {target_sleep:.1f} h)",
            )
        )
    elif day.sleep_score is not None:
        sleep_s = score_sleep_garmin(day.sleep_score)
        components.append(
            ComponentScore(
                "sleep",
                "Søvnscore (Garmin)",
                round(sleep_s, 1),
                f"score {day.sleep_score:.0f}",
            )
        )
    if sleep_s is not None:
        w = float(weights.get("sleep", 0.15))
        weighted_sum += sleep_s * w
        weight_total += w

    # --- Subjective ---
    subj_vals = [
        v
        for v in (day.soreness, day.fatigue, day.stress, day.injury)
        if v is not None
    ]
    if subj_vals:
        subj_s = score_subjective(subj_vals)
        components.append(
            ComponentScore(
                "subjective",
                "Subjektivt",
                round(subj_s, 1),
                f"snitt {sum(subj_vals) / len(subj_vals):.1f} (stølhet/utm/stress/skade)",
            )
        )
        w = float(weights.get("subjective", 0.10))
        weighted_sum += subj_s * w
        weight_total += w

    if weight_total <= 0:
        raw = 50.0
    else:
        raw = weighted_sum / weight_total

    life_adj = 0
    for _key, penalty in (cfg.get("life_adjustments") or {}).items():
        if isinstance(penalty, (int, float)):
            life_adj += int(penalty)

    final = int(round(clamp(raw + life_adj)))
    band, emoji, rec = band_for_score(final, cfg)

    return ReadinessResult(
        date=day.date,
        score=final,
        band=band,
        emoji=emoji,
        recommendation=rec,
        components=components,
        life_adjustment=life_adj,
        tsb=tsb,
        atl_ctl_ratio=ratio,
        garmin_readiness=garmin_readiness,
    )


def compute_all(
    days: list[DayInputs], cfg: dict[str, Any]
) -> list[ReadinessResult]:
    return [compute_day_readiness(days, i, cfg) for i in range(len(days))]


def format_markdown(
    results: list[ReadinessResult],
    title: str = "TB-Score",
    history_days: int = 14,
) -> str:
    if not results:
        return f"# {title}\n\nIngen dager.\n"
    lines = [f"# {title} — totalbelastning / treningsevne\n"]
    last = results[-1]
    lines.append(
        f"**Siste dag ({last.date.date()}): {last.score}/100** {last.emoji} **{last.band.capitalize()}**"
    )
    if last.life_adjustment:
        lines.append(f" (livsjustering {last.life_adjustment:+d} poeng)")
    lines.append(f"\n{last.recommendation}\n")
    if last.tsb is not None:
        lines.append(
            f"\nTrainingPeaks-form: TSB {last.tsb:+.0f}"
            + (
                f", ATL/CTL {last.atl_ctl_ratio:.2f}"
                if last.atl_ctl_ratio
                else ""
            )
            + ".\n"
        )
    lines.append("\n## Komponenter (siste dag)\n")
    lines.append("| Komponent | Poeng | Detalj |")
    lines.append("|-----------|------:|--------|")
    for c in last.components:
        sc = f"{c.score:.0f}" if c.score is not None else "—"
        lines.append(f"| {c.label} | {sc} | {c.detail} |")

    lines.append("\n## Historikk (kompakt)\n")
    tail = results[-history_days:] if history_days > 0 else results
    for r in tail:
        lines.append(f"- {r.date.date()}: **{r.score}** {r.emoji} {r.band}")
    lines.append(
        "\n---\n*TB-Score er repoets totalbelastningsindeks (trening + recovery + livsjustering). "
        "Garmin Training Readiness kan synke til `readiness` i Intervals — sammenlign, ikke erstatt blindt.*\n"
    )
    return "\n".join(lines)
