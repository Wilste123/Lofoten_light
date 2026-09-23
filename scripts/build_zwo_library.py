#!/usr/bin/env python3
"""Bygg bibliotek: sykkel .zwo, løp/svøm .zwo (norsk), styrke .txt."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZWO = ROOT / "workouts" / "zwo"
PLANNED = ROOT / "workouts" / "planned" / "strength"


def write_strength(
    path: Path,
    name: str,
    description: str,
    steps_text: str,
    duration_min: int,
) -> None:
    lines = [
        f"name: {name}",
        "sport: strength",
        f"description: {description}",
        "tp_intensity: Styrke → TrainingPeaks Strength Builder (ikke ZWO/FIT)",
        f"duration_min: {duration_min}",
        "trainingpeaks: Se docs/trainingpeaks/styrke-import.md og workouts/strength/trainingpeaks/",
        "steps:",
        f"  - {duration_min}:00 | {steps_text}",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ZWO.mkdir(parents=True, exist_ok=True)
    scripts = ROOT / "scripts"
    manifest = ROOT / "workouts" / "bike" / "manifest.json"
    if not manifest.is_file():
        if any((ZWO / "bike").glob("*.zwo")):
            subprocess.run([sys.executable, "compile_bike_manifest.py"], check=True, cwd=scripts)
        else:
            raise SystemExit("Ingen sykkeløkter. Legg til workouts/zwo/bike/*.zwo eller manifest.json.")
    subprocess.run([sys.executable, "export_bike_zwo.py"], check=True, cwd=scripts)

    # Fjern gamle txt for løp/svøm
    for sub in ("swim", "run", "brick"):
        p = ROOT / "workouts" / "planned" / sub
        if p.is_dir():
            shutil.rmtree(p)

    subprocess.run([sys.executable, "run_swim_zwo.py"], check=True, cwd=scripts)

    if PLANNED.parent.exists():
        for f in PLANNED.parent.glob("**/*.txt"):
            if "strength" not in str(f):
                f.unlink()
    PLANNED.mkdir(parents=True, exist_ok=True)
    write_strength(
        PLANNED / "ST01-base.txt",
        "ST01 Styrke A base",
        "Grunnstyrke tri — 35 min.",
        "Goblet squat 3×10, split squat 3×8/side, planke, band-row, calf, dead bug",
        35,
    )
    write_strength(
        PLANNED / "ST02-build.txt",
        "ST02 Styrke B build",
        "Byggfase — 40 min.",
        "Stangmarkløft/hip thrust, step-down, Copenhagen, farmer carry, push-up",
        40,
    )
    write_strength(
        PLANNED / "ST03-recovery.txt",
        "ST03 Styrke recovery",
        "Mobilitet lett — 25 min.",
        "Band walks, glute bridge, bird dog, stretching",
        25,
    )

    brick_zwo = ZWO / "brick"
    brick_zwo.mkdir(parents=True, exist_ok=True)
    bike_out = ZWO / "bike"
    shutil.copy2(bike_out / "endurance-90.zwo", brick_zwo / "BR01-bike-90.zwo")
    shutil.copy2(bike_out / "endurance-180.zwo", brick_zwo / "BR02-bike-180.zwo")
    shutil.copy2(bike_out / "progressive-long-240.zwo", brick_zwo / "BR03-bike-240.zwo")

    print(f"Sykkel ZWO (FTP i TP): {bike_out}")
    print(f"Løp/svøm ZWO (norsk): {ZWO / 'run'}, {ZWO / 'swim'}")
    print(f"Styrke txt: {PLANNED}")


if __name__ == "__main__":
    main()
