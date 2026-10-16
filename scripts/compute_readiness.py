#!/usr/bin/env python3
"""Compute TB-Score (totalbelastning readiness) from Intervals wellness CSV."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from analyze_tp_export import load_rows  # noqa: E402
from readiness_total_load import (  # noqa: E402
    compute_all,
    format_markdown,
    load_config,
    parse_wellness_rows,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="TB-Score: treningsevne / totalbelastning fra Intervals wellness.csv"
    )
    parser.add_argument("csv_path", type=Path, nargs="?", help="wellness.csv export")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="JSON config (default docs/athlete/readiness-config.json)",
    )
    parser.add_argument(
        "--last",
        type=int,
        default=0,
        help="Only show last N days in history section (0 = all in compact tail)",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON for last day")
    parser.add_argument(
        "--push-readiness",
        action="store_true",
        help="PUT readiness field to Intervals for last day (needs INTERVALS_API)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run built-in checks on sample data",
    )
    args = parser.parse_args()

    if args.self_test:
        return _self_test()

    if not args.csv_path or not args.csv_path.is_file():
        print("Usage: compute_readiness.py <wellness.csv>", file=sys.stderr)
        return 1

    cfg = load_config(args.config)
    rows, fields = load_rows(args.csv_path)
    days = parse_wellness_rows(rows, fields)
    if not days:
        print("No wellness days parsed.", file=sys.stderr)
        return 1

    results = compute_all(days, cfg)
    history_days = args.last if args.last > 0 else 14
    last = results[-1]

    if args.json:
        payload = {
            "date": last.date.date().isoformat(),
            "tb_score": last.score,
            "band": last.band,
            "life_adjustment": last.life_adjustment,
            "tsb": last.tsb,
            "atl_ctl_ratio": last.atl_ctl_ratio,
            "components": [
                {"key": c.key, "label": c.label, "score": c.score, "detail": c.detail}
                for c in last.components
            ],
            "recommendation": last.recommendation,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        md = format_markdown(results, history_days=history_days)
        print(md)

    if args.push_readiness:
        from intervals_lib import api_key, put_wellness  # noqa: E402

        if not api_key():
            print("INTERVALS_API not set — skip push.", file=sys.stderr)
            return 1
        day_id = last.date.date().isoformat()
        note = f"TB-Score {last.score} ({last.band})"
        put_wellness(
            day_id,
            {
                "readiness": last.score,
                "comments": note[:200],
            },
        )
        print(f"Pushed readiness={last.score} for {day_id}", file=sys.stderr)

    return 0


def _self_test() -> int:
    from datetime import datetime, timedelta

    from readiness_total_load import DayInputs, compute_day_readiness, load_config

    base = datetime(2026, 10, 1)
    days: list[DayInputs] = []
    for i in range(25):
        days.append(
            DayInputs(
                date=base + timedelta(days=i),
                ctl=20 + i * 0.5,
                atl=40 + i * 1.5,
                hrv=55 + (i % 5),
                resting_hr=58 + (i % 3),
                sleep_hours=7.2,
                soreness=2,
                fatigue=2,
                stress=2,
            )
        )
    cfg = load_config(None)
    r = compute_day_readiness(days, len(days) - 1, cfg)
    assert 0 <= r.score <= 100, r.score
    assert r.band in ("grønn", "gul", "rød")
    assert r.components, "expected components"
    print("self-test ok", r.score, r.band)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
