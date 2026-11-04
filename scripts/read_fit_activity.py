#!/usr/bin/env python3
"""Summarize a Garmin .fit activity (power/HR for bike tests)."""

from __future__ import annotations

import argparse
import sys
from collections import deque
from pathlib import Path

try:
    from fitparse import FitFile
except ImportError as e:
    raise SystemExit("Install fitparse: pip install fitparse") from e


def _rolling_best(records: list[tuple], window: int, min_fill: int) -> float:
    """Max rolling average of second field (power) over `window` samples."""
    q: deque[int] = deque()
    s = 0
    best = 0.0
    for row in records:
        p = row[1]
        q.append(p)
        s += p
        while len(q) > window:
            s -= q.popleft()
        if len(q) >= min_fill:
            best = max(best, s / len(q))
    return best


def summarize_fit(path: Path) -> dict:
    fit = FitFile(str(path))
    session: dict = {}
    for msg in fit.get_messages("session"):
        for f in msg:
            if f.value is not None:
                session[f.name] = f.value

    records: list[tuple] = []
    for msg in fit.get_messages("record"):
        d = {f.name: f.value for f in msg}
        if d.get("power") is not None:
            records.append(
                (d.get("timestamp"), int(d["power"]), d.get("heart_rate"))
            )
    records.sort(key=lambda x: x[0])

    powers = [r[1] for r in records]
    hrs = [r[2] for r in records if r[2]]
    out: dict = {
        "file": str(path),
        "sport": session.get("sport"),
        "elapsed_s": session.get("total_elapsed_time"),
        "distance_m": session.get("total_distance"),
        "n_power_records": len(records),
    }
    if not powers:
        return out

    best_60 = _rolling_best(records, 60, 55)
    best_20 = _rolling_best(records, 1200, 1140)
    out.update(
        {
            "avg_power": round(sum(powers) / len(powers)),
            "max_power": max(powers),
            "best_60s_w": round(best_60),
            "best_20min_w": round(best_20),
            "ftp_95pct_20min": round(best_20 * 0.95),
            "hr_avg": round(sum(hrs) / len(hrs)) if hrs else None,
            "hr_max": max(hrs) if hrs else None,
        }
    )
    if len(records) > 1200:
        test_phase = [(t, p, h) for t, p, h in records[1200:]]
        out["best_60s_after_20min_w"] = round(_rolling_best(test_phase, 60, 55))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fit_file", type=Path)
    args = parser.parse_args()
    if not args.fit_file.is_file():
        print(f"Not found: {args.fit_file}", file=sys.stderr)
        return 1
    info = summarize_fit(args.fit_file)
    for k, v in info.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
