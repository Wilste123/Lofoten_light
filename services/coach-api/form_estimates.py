"""Deterministic form estimates: 5-session gate + MMP FTP (+ optional VO2 stub)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


MIN_QUALIFYING_SESSIONS = 5
MIN_SESSION_MINUTES = 20

# Conservative MMP → FTP factors (see docs/product/form-estimates.md)
MMP_FACTORS: dict[int, float] = {
    20: 0.95,
    12: 0.90,
    8: 0.88,
    5: 0.85,
}


@dataclass
class ActivityPower:
    """Minimal activity for gate / MMP.

    duration_min: total duration with power
    mean_power: average power for whole activity (optional)
    mmp: optional dict of window_minutes → mean maximal power (W)
    """

    duration_min: float
    mean_power: float | None = None
    mmp: dict[int, float] | None = None
    has_power: bool = True


def is_qualifying_session(act: ActivityPower) -> bool:
    if not act.has_power:
        return False
    if act.mean_power is None and not act.mmp:
        return False
    return act.duration_min >= MIN_SESSION_MINUTES


def count_qualifying_sessions(activities: Sequence[ActivityPower]) -> int:
    return sum(1 for a in activities if is_qualifying_session(a))


def gate_open(activities: Sequence[ActivityPower]) -> bool:
    """True when ≥ 5 qualifying bike sessions with power."""
    return count_qualifying_sessions(activities) >= MIN_QUALIFYING_SESSIONS


def _candidates_from_mmp(mmp: dict[int, float]) -> list[tuple[int, float]]:
    out: list[tuple[int, float]] = []
    for window, factor in MMP_FACTORS.items():
        p = mmp.get(window)
        if p is not None and p > 0:
            out.append((window, p * factor))
    return out


def estimate_ftp_from_mmp(
    mmp: dict[int, float],
    ftp_tested: float | None = None,
) -> dict[str, Any]:
    """Return ftp_estimated, confidence, capped flag.

    Selection: min of candidates from windows ≥ 8 min if any; else min of all.
    Cap vs tested FTP per product rules.
    """
    candidates = _candidates_from_mmp(mmp)
    if not candidates:
        return {
            "ftp_estimated": None,
            "confidence": None,
            "capped": False,
            "source": "local_mmp",
        }

    long = [(w, v) for w, v in candidates if w >= 8]
    pool = long if long else candidates
    best_window, raw = min(pool, key=lambda x: x[1])

    if best_window >= 20:
        confidence = "høy"
    elif best_window >= 8:
        confidence = "medium"
    else:
        confidence = "lav"

    capped = False
    estimated = raw
    if ftp_tested is not None and ftp_tested > 0:
        cap = ftp_tested * 1.05
        if estimated > ftp_tested * 1.08:
            estimated = cap
            capped = True
            confidence = "lav"
        elif estimated > cap:
            estimated = cap
            capped = True

    return {
        "ftp_estimated": round(estimated, 1),
        "confidence": confidence,
        "capped": capped,
        "source": "local_mmp",
        "best_window_min": best_window,
    }


def aggregate_mmp(activities: Sequence[ActivityPower]) -> dict[int, float]:
    """Max MMP across activities for each window."""
    agg: dict[int, float] = {}
    for act in activities:
        if not act.mmp:
            continue
        for w, p in act.mmp.items():
            if p is None or p <= 0:
                continue
            agg[w] = max(agg.get(w, 0.0), float(p))
    return agg


def compute_form_estimates(
    activities: Sequence[ActivityPower],
    *,
    ftp_tested: float | None = None,
    weight_kg: float | None = None,
    age_years: int | None = None,
) -> dict[str, Any]:
    """Full estimate pipeline with gate.

    VO₂ requires weight + age + steady segment — stub returns None until HR segments exist.
    """
    n = count_qualifying_sessions(activities)
    open_ = gate_open(activities)
    result: dict[str, Any] = {
        "gate_open": open_,
        "qualifying_sessions": n,
        "required_sessions": MIN_QUALIFYING_SESSIONS,
        "ftp_estimated": None,
        "vo2_estimate": None,
        "estimate_confidence": None,
        "estimate_source": None,
        "disclaimer": None,
    }
    if not open_:
        result["disclaimer"] = (
            "Estimat etter 5 sykkeløkter med watt "
            "(eller koble Intervals med historikk)."
        )
        return result

    mmp = aggregate_mmp(activities)
    ftp = estimate_ftp_from_mmp(mmp, ftp_tested=ftp_tested)
    result["ftp_estimated"] = ftp["ftp_estimated"]
    result["estimate_confidence"] = ftp["confidence"]
    result["estimate_source"] = ftp.get("source")
    if ftp.get("capped"):
        result["disclaimer"] = (
            "Estimat capset mot testet FTP — vurder en 20-min test."
        )
    elif ftp["confidence"] == "lav":
        result["disclaimer"] = "Lav confidence — tynt datasett eller korte maksdrag."

    # VO2: stricter gate — needs weight + age; HR segments not in MVP stub data
    if weight_kg and age_years and result["ftp_estimated"]:
        # Without steady HR segment, do not invent VO2
        result["vo2_estimate"] = None
    return result
