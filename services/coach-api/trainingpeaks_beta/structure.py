"""Map Intervals-style step text → TrainingPeaks workout structure JSON."""

from __future__ import annotations

import json
import re
from typing import Any

_STEP_LINE = re.compile(
    r"^\s*-\s*"
    r"(?:(\d+)mtr|(\d+)m|(\d+)s)\s+"
    r"(?:(\d+)(?:-(\d+))?%|(\d+)(?:-(\d+))?\s*LTHR|(\d+)(?:-(\d+))?\s*FTP)?"
    r"(.*)$",
    re.IGNORECASE,
)
_MAIN_SET = re.compile(r"^Main\s+Set\s+(\d+)x\s*$", re.IGNORECASE)


def _intensity_metric(sport: str, line: str, ev: dict[str, Any]) -> str:
    low = (line or "").lower()
    if "lthr" in low or (ev.get("target") or "").upper() == "HR":
        return "percentOfThresholdHr"
    if sport in ("run", "swim") and ("pace" in low or (ev.get("target") or "").upper() == "PACE"):
        return "percentOfThresholdPace"
    return "percentOfFtp"


def _parse_step_line(line: str, sport: str, ev: dict[str, Any]) -> dict[str, Any] | None:
    m = _STEP_LINE.match(line.strip())
    if not m:
        return None
    meters = m.group(1)
    minutes = m.group(2)
    seconds = m.group(3)
    if meters:
        length = {"value": int(meters), "unit": "meter"}
    elif minutes:
        length = {"value": int(minutes) * 60, "unit": "second"}
    elif seconds:
        length = {"value": int(seconds), "unit": "second"}
    else:
        return None
    p1, p2 = m.group(4), m.group(5)
    h1, h2 = m.group(6), m.group(7)
    f1, f2 = m.group(8), m.group(9)
    lo, hi = None, None
    if p1:
        lo, hi = int(p1), int(p2 or p1)
    elif h1:
        lo, hi = int(h1), int(h2 or h1)
    elif f1:
        lo, hi = int(f1), int(f2 or f1)
    targets: list[dict[str, Any]] = []
    if lo is not None:
        if hi is not None and hi != lo:
            targets.append({"minValue": lo, "maxValue": hi, "unit": None})
        else:
            targets.append({"minValue": lo, "maxValue": None, "unit": None})
    name = (m.group(10) or "").strip() or "Step"
    return {
        "type": "step",
        "length": {"value": 1, "unit": "repetition"},
        "steps": [
            {
                "name": name[:80],
                "length": length,
                "targets": targets,
            }
        ],
    }


def structure_from_icu_event(ev: dict[str, Any]) -> str | None:
    """Return TP structure JSON string or None (steady / description-only)."""
    sport = str(ev.get("_sport") or ev.get("type") or "").lower()
    desc = str(ev.get("description") or "")
    steps: list[dict[str, Any]] = []
    rep_buffer: list[dict[str, Any]] = []
    rep_count: int | None = None
    for raw in desc.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line == "---":
            continue
        ms = _MAIN_SET.match(line)
        if ms:
            if rep_buffer and rep_count:
                steps.append(
                    {
                        "type": "repetition",
                        "length": {"value": rep_count, "unit": "repetition"},
                        "steps": rep_buffer,
                    }
                )
            rep_buffer = []
            rep_count = int(ms.group(1))
            continue
        parsed = _parse_step_line(line, sport, ev)
        if parsed:
            if rep_count:
                rep_buffer.extend(parsed["steps"])
            else:
                steps.append(parsed)
    if rep_buffer and rep_count:
        steps.append(
            {
                "type": "repetition",
                "length": {"value": rep_count, "unit": "repetition"},
                "steps": rep_buffer,
            }
        )
    if not steps:
        mins = ev.get("_duration_minutes") or ev.get("moving_time")
        if mins and int(mins) > 0:
            dur_s = int(mins) * 60 if isinstance(mins, int) and mins < 600 else int(mins)
            metric = _intensity_metric(sport, desc, ev)
            steps.append(
                {
                    "type": "step",
                    "length": {"value": 1, "unit": "repetition"},
                    "steps": [
                        {
                            "name": "Steady",
                            "length": {"value": dur_s, "unit": "second"},
                            "targets": [{"minValue": 65, "maxValue": 75, "unit": None}],
                        }
                    ],
                }
            )
        else:
            return None
    metric = _intensity_metric(sport, desc, ev)
    primary = "duration"
    if any(
        s.get("steps")
        and s["steps"][0].get("length", {}).get("unit") == "meter"
        for s in steps
    ):
        primary = "distance"
    wrapper = {
        "structure": steps,
        "primaryLengthMetric": primary,
        "primaryIntensityMetric": metric,
        "visualizationDistanceUnit": "meter" if primary == "distance" else None,
    }
    return json.dumps(wrapper, separators=(",", ":"))
