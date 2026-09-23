#!/usr/bin/env python3
"""Convert workouts/planned/{run,swim,brick}/*.txt → workouts/zwo/ using threshold-pace fractions."""

from __future__ import annotations

import re
from pathlib import Path

from zwo_common import RUN_NOTE, SWIM_NOTE, write_zwo_power

ROOT = Path(__file__).resolve().parents[1]
PLANNED = ROOT / "workouts" / "planned"
ZWO = ROOT / "workouts" / "zwo"

# Map tp_target text (from planned files) → power fraction of threshold pace (run or swim)
FRAC: dict[str, float] = {
    "% LTHR 80-89% (or RPE 4-5)": 0.78,
    "% LTHR Z1-Z2": 0.72,
    "% threshold pace 88-94%": 0.91,
    "% threshold pace 95-105%": 1.0,
    "% threshold pace 102-115% or RPE 8-9": 1.08,
    "Recover — % LTHR Z1": 0.65,
    "Strides — RPE 7-8 for 15s, easy between": 1.12,
    "% T-pace 89-92% or RPE 3-4": 0.90,
    "% T-pace 92-94%": 0.93,
    "% T-pace ~100%": 1.0,
    "% T-pace 99-106%": 1.03,
    "% T-pace 89-90% or RPE 2-4": 0.89,
    "RPE 3-5 (rename steps for drills)": 0.88,
    "RPE 3-5": 0.88,
    "Recover (duration), target pace 0": 0.50,
}


def parse_planned(path: Path) -> tuple[str, str, str, list[tuple[int, str, str]]]:
    text = path.read_text(encoding="utf-8")
    name = re.search(r"^name: (.+)$", text, re.M).group(1)
    sport = re.search(r"^sport: (.+)$", text, re.M).group(1)
    desc = re.search(r"^description: (.+)$", text, re.M).group(1)
    steps: list[tuple[int, str, str]] = []
    for line in text.splitlines():
        m = re.match(r"  - (\d+:\d+) \| (.+) \| tp_target: (.+)$", line)
        if not m:
            continue
        t = m.group(1)
        parts = t.split(":")
        sec = int(parts[0]) * 60 + int(parts[1])
        steps.append((sec, m.group(2).strip(), m.group(3).strip()))
    return name, sport, desc, steps


def frac_for(tp_target: str) -> float:
    if tp_target in FRAC:
        return FRAC[tp_target]
    for key, val in FRAC.items():
        if key in tp_target or tp_target in key:
            return val
    return 0.85


def convert_file(src: Path, dest: Path, sport: str, note: str) -> None:
    name, _file_sport, desc, steps = parse_planned(src)
    prefix = "RUN " if sport == "run" else "SWIM "
    if not name.upper().startswith(("RUN ", "SWIM ")):
        name = prefix + name
    zwo_steps = []
    for sec, msg, tp in steps:
        zwo_steps.append((sec, msg, frac_for(tp), None))
    write_zwo_power(
        dest,
        sport,
        name,
        desc,
        zwo_steps,
        note,
        tp_library_import=True,
    )


def main() -> None:
    for sub, sport, note in (
        ("run", "run", RUN_NOTE),
        ("swim", "swim", SWIM_NOTE),
    ):
        src_dir = PLANNED / sub
        dst_dir = ZWO / sub
        if dst_dir.exists():
            for f in dst_dir.glob("*.zwo"):
                f.unlink()
        dst_dir.mkdir(parents=True, exist_ok=True)
        if not src_dir.is_dir():
            continue
        for txt in sorted(src_dir.glob("*.txt")):
            convert_file(txt, dst_dir / f"{txt.stem}.zwo", sport, note)
        print(f"{sub}: {len(list(dst_dir.glob('*.zwo')))} zwo")

    brick_run = PLANNED / "brick"
    brick_zwo = ZWO / "brick"
    brick_zwo.mkdir(parents=True, exist_ok=True)
    for f in brick_zwo.glob("*-run-*.zwo"):
        f.unlink()
    if brick_run.is_dir():
        for txt in sorted(brick_run.glob("*.txt")):
            convert_file(txt, brick_zwo / f"{txt.stem}.zwo", "run", RUN_NOTE)
        print(f"brick run: {len(list(brick_zwo.glob('*-run-*.zwo')))} zwo")


if __name__ == "__main__":
    main()
