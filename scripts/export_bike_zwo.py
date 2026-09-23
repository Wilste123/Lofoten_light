#!/usr/bin/env python3
"""Regenerate bike .zwo from manifest (% FTP only — follows TP bike FTP on import)."""

from __future__ import annotations

import json
from pathlib import Path

from zwo_common import FTP_NOTE_BIKE, write_zwo_power

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "workouts" / "bike" / "manifest.json"
OUT = ROOT / "workouts" / "zwo" / "bike"


def main() -> None:
    if not MANIFEST.is_file():
        raise SystemExit(f"Missing {MANIFEST}. Run scripts/compile_bike_manifest.py first.")
    workouts = json.loads(MANIFEST.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    for w in workouts:
        steps = [(s["duration_s"], s["message"], s["ftp_fraction"], None) for s in w["steps"]]
        write_zwo_power(
            OUT / f"{w['id']}.zwo",
            "bike",
            w["name"],
            w["description"],
            steps,
            FTP_NOTE_BIKE,
        )
    print(f"Wrote {len(workouts)} bike ZWO to {OUT}")


if __name__ == "__main__":
    main()
