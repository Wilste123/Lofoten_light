#!/usr/bin/env python3
"""Export bike workout YAML to Garmin FIT workout (.fit) with power targets in watts."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from garmin_fit_sdk import Encoder

from workout_yaml_io import parse_workout_yaml, safe_filename

# FIT enums (Profile)
SPORT_CYCLING = 2
SUB_SPORT_INDOOR = 6
FILE_TYPE_WORKOUT = 5
MANUFACTURER_DEVELOPMENT = 255
DURATION_TIME = 0
TARGET_POWER = 4
INTENSITY_ACTIVE = 0
INTENSITY_WARMUP = 2
INTENSITY_COOLDOWN = 3
INTENSITY_RECOVERY = 4


def _intensity_for_step(step: dict, index: int, total: int) -> int:
    note = (step.get("note") or "").lower()
    if index == 0 or "warm" in note:
        return INTENSITY_WARMUP
    if index == total - 1 or "cool" in note:
        return INTENSITY_COOLDOWN
    pct = int(step.get("power_pct_ftp", 50))
    if pct < 56:
        return INTENSITY_RECOVERY
    return INTENSITY_ACTIVE


def workout_to_fit_bytes(workout: dict, ftp: int) -> bytes:
    steps = workout.get("steps") or []
    if not steps:
        raise ValueError("Workout has no steps")
    if ftp < 50:
        raise ValueError("FTP must be set (e.g. --ftp 280)")

    encoder = Encoder()
    encoder.write_mesg(
        {
            "mesg_num": 0,
            "type": FILE_TYPE_WORKOUT,
            "manufacturer": MANUFACTURER_DEVELOPMENT,
            "time_created": int(time.time()),
        }
    )
    name = workout.get("name", "Workout")[:47]
    desc = (workout.get("description") or "")[:250]
    encoder.write_mesg(
        {
            "mesg_num": 26,
            "sport": SPORT_CYCLING,
            "sub_sport": SUB_SPORT_INDOOR,
            "num_valid_steps": len(steps),
            "wkt_name": name,
            "wkt_description": desc,
        }
    )

    for i, step in enumerate(steps):
        duration_min = int(step.get("duration_min", 10))
        pct = int(step.get("power_pct_ftp", 50))
        watts = max(1, round(ftp * pct / 100))
        margin = max(5, round(watts * 0.02))
        low = max(1, watts - margin)
        high = watts + margin
        note = (step.get("note") or f"Step {i + 1}")[:47]

        encoder.write_mesg(
            {
                "mesg_num": 27,
                "message_index": i,
                "wkt_step_name": note,
                "duration_type": DURATION_TIME,
                "duration_value": duration_min * 60 * 1000,  # milliseconds
                "target_type": TARGET_POWER,
                "custom_target_value_low": low,
                "custom_target_value_high": high,
                "intensity": _intensity_for_step(step, i, len(steps)),
            }
        )

    return encoder.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Export bike workout YAML to FIT")
    parser.add_argument("yaml_path", type=Path)
    parser.add_argument(
        "--ftp",
        type=int,
        required=True,
        help="Your current FTP in watts (FIT uses absolute watts, not YAML alone)",
    )
    parser.add_argument("-o", "--output", type=Path, help="Output .fit path")
    args = parser.parse_args()

    if not args.yaml_path.is_file():
        print(f"File not found: {args.yaml_path}", file=sys.stderr)
        return 1

    workout = parse_workout_yaml(args.yaml_path)
    fit_data = workout_to_fit_bytes(workout, args.ftp)

    out = args.output
    if out is None:
        out = Path("workouts/generated") / f"{safe_filename(workout.get('name', 'workout'))}.fit"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(fit_data)
    print(f"Wrote {out} (FTP={args.ftp} W used for power targets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
