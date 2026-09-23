#!/usr/bin/env python3
"""One-time / refresh: snapshot workouts/zwo/bike/*.zwo → workouts/bike/manifest.json"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIKE = ROOT / "workouts" / "zwo" / "bike"
MANIFEST = ROOT / "workouts" / "bike" / "manifest.json"


def main() -> None:
    out = []
    for p in sorted(BIKE.glob("*.zwo")):
        text = p.read_text(encoding="utf-8")
        name = re.search(r"<name>(.*?)</name>", text).group(1)
        desc = re.search(r"<description>(.*?)</description>", text).group(1)
        desc = desc.split(" — Bike:")[0].split(" — ")[0].strip()
        steps = []
        for m in re.finditer(
            r'<SteadyState Duration="(\d+)" Power="([\d.]+)"[^>]*>\s*<textevent message="([^"]*)"',
            text,
        ):
            steps.append(
                {
                    "duration_s": int(m.group(1)),
                    "ftp_fraction": float(m.group(2)),
                    "message": m.group(3),
                }
            )
        out.append({"id": p.stem, "name": name, "description": desc, "steps": steps})
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(out)} workouts to {MANIFEST}")


if __name__ == "__main__":
    main()
