#!/usr/bin/env python3
"""Compute TB-Score (totalbelastning readiness) — snapshot by default (--at now)."""

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
    compute_readiness_at,
    format_markdown,
    format_snapshot_markdown,
    load_config,
    parse_activity_points,
    parse_wellness_rows,
    resolve_as_of,
    result_to_dict,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="TB-Score: tidspunkt-basert totalbelastning (wellness + aktiviteter)"
    )
    parser.add_argument("csv_path", type=Path, nargs="?", help="wellness.csv export")
    parser.add_argument(
        "--activities",
        type=Path,
        help="Intervals activities.csv (anbefalt for tid siden load)",
    )
    parser.add_argument(
        "--at",
        type=str,
        default="now",
        help="Snapshot-tidspunkt: now | ISO datetime | noon",
    )
    parser.add_argument(
        "--daily",
        action="store_true",
        help="Daglig historikk uten klokkeslett (legacy)",
    )
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
        help="Daglig modus: antall dager i historikk (default 14)",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument(
        "--include-subjective",
        action="store_true",
        help="Inkluder soreness/stress (default av — kan styres av bruker)",
    )
    parser.add_argument(
        "--push-readiness",
        action="store_true",
        help="PUT readiness til Intervals for wellness-dato (needs INTERVALS_API)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run built-in checks",
    )
    args = parser.parse_args()

    if args.self_test:
        return _self_test()

    if not args.csv_path or not args.csv_path.is_file():
        print(
            "Usage: compute_readiness.py <wellness.csv> [--activities activities.csv]",
            file=sys.stderr,
        )
        return 1

    cfg = load_config(args.config)
    rows, fields = load_rows(args.csv_path)
    days = parse_wellness_rows(rows, fields)
    if not days:
        print("No wellness days parsed.", file=sys.stderr)
        return 1

    activities = None
    if args.activities:
        if not args.activities.is_file():
            print(f"Activities file not found: {args.activities}", file=sys.stderr)
            return 1
        a_rows, a_fields = load_rows(args.activities)
        activities = parse_activity_points(a_rows, a_fields)
    elif not args.daily:
        print(
            "Note: uten --activities mangler «tid siden siste økt» / 24h-load.",
            file=sys.stderr,
        )

    include_subj = args.include_subjective

    if args.daily:
        results = compute_all(days, cfg, include_subj)
        history_days = args.last if args.last > 0 else 14
        last = results[-1]
        if args.json:
            print(json.dumps(result_to_dict(last), indent=2, ensure_ascii=False))
        else:
            print(format_markdown(results, history_days=history_days))
        push_result = last
    else:
        as_of = resolve_as_of(args.at, cfg)
        result = compute_readiness_at(
            as_of, days, activities, cfg, include_subj
        )
        if args.json:
            print(json.dumps(result_to_dict(result), indent=2, ensure_ascii=False))
        else:
            print(format_snapshot_markdown(result))
        push_result = result

    if args.push_readiness:
        from intervals_lib import api_key, put_wellness  # noqa: E402

        if not api_key():
            print("INTERVALS_API not set — skip push.", file=sys.stderr)
            return 1
        day_id = (
            push_result.wellness_date.isoformat()
            if push_result.wellness_date
            else push_result.as_of.date().isoformat()
        )
        note = f"TB-Score {push_result.score} ({push_result.band})"
        put_wellness(day_id, {"readiness": push_result.score, "comments": note[:200]})
        print(f"Pushed readiness={push_result.score} for {day_id}", file=sys.stderr)

    return 0


def _self_test() -> int:
    from datetime import datetime, timedelta

    from readiness_total_load import (
        ActivityPoint,
        DayInputs,
        acute_context_at,
        compute_readiness_at,
        load_config,
        score_recovery_time,
    )

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
            )
        )
    cfg = load_config(None)
    acts = [
        ActivityPoint(
            start=datetime(2026, 10, 15, 17, 0),
            end=datetime(2026, 10, 15, 18, 30),
            load=120,
            sport="Run",
        )
    ]
    at_morning = datetime(2026, 10, 16, 7, 0)
    at_evening = datetime(2026, 10, 16, 19, 0)
    r_am = compute_readiness_at(at_morning, days, acts, cfg, False)
    r_pm = compute_readiness_at(at_evening, days, acts, cfg, False)
    assert r_pm.score >= r_am.score, (r_am.score, r_pm.score)
    ctx = acute_context_at(acts, at_evening)
    assert ctx.hours_since_last is not None and ctx.hours_since_last > 20
    rec = score_recovery_time(10, 120, cfg)
    rec2 = score_recovery_time(30, 120, cfg)
    assert rec2 > rec
    assert 0 <= r_pm.score <= 100
    print("self-test ok", "am", r_am.score, "pm", r_pm.score)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
