#!/usr/bin/env python3
"""Export simple bike workouts from YAML to Zwift ZWO format."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


def parse_simple_yaml(path: Path) -> dict:
    if yaml is not None:
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f)
    return parse_minimal_yaml(path.read_text(encoding="utf-8"))


def parse_minimal_yaml(text: str) -> dict:
    """Tiny YAML subset when PyYAML is not installed."""
    data: dict = {"name": "Workout", "steps": []}
    in_steps = False
    step: dict | None = None
    for line in text.splitlines():
        if re.match(r"^\s*-\s+duration_min:", line) or line.strip() == "-":
            if step:
                data["steps"].append(step)
            step = {}
            in_steps = True
            m = re.search(r"duration_min:\s*(\d+)", line)
            if m:
                step["duration_min"] = int(m.group(1))
            continue
        if step is not None:
            m = re.search(r"power_pct_ftp:\s*(\d+)", line)
            if m:
                step["power_pct_ftp"] = int(m.group(1))
            m = re.search(r'note:\s*(.+)', line)
            if m:
                step["note"] = m.group(1).strip()
            continue
        m = re.match(r"^name:\s*(.+)", line)
        if m:
            data["name"] = m.group(1).strip()
        m = re.match(r"^description:\s*(.+)", line)
        if m:
            data["description"] = m.group(1).strip()
    if step:
        data["steps"].append(step)
    return data


def step_to_zwo(step: dict, index: int) -> str:
    duration = int(step.get("duration_min", 10)) * 60
    pct = int(step.get("power_pct_ftp", 50))
    low = max(1, pct - 2)
    high = min(200, pct + 2)
    note = step.get("note", f"Step {index}")
    return f"""    <SteadyState Duration="{duration}" Power="{pct / 100:.4f}" pace="0">
      <textevent message="{_escape(note)}" timeoffset="0"/>
    </SteadyState>"""


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def to_zwo(workout: dict) -> str:
    name = workout.get("name", "Workout")
    desc = workout.get("description", "")
    steps = workout.get("steps") or []
    if not steps:
        raise ValueError("Workout has no steps")
    body = "\n".join(step_to_zwo(s, i + 1) for i, s in enumerate(steps))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<workout_file>
  <author>Xtri training coach</author>
  <name>{_escape(name)}</name>
  <description>{_escape(desc)}</description>
  <sportType>bike</sportType>
  <tags/>
  <workout>
{body}
  </workout>
</workout_file>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Export workout YAML to ZWO")
    parser.add_argument("yaml_path", type=Path, help="Path to workout YAML")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output .zwo path (default: workouts/generated/<name>.zwo)",
    )
    args = parser.parse_args()
    if not args.yaml_path.is_file():
        print(f"File not found: {args.yaml_path}", file=sys.stderr)
        return 1
    workout = parse_simple_yaml(args.yaml_path)
    zwo = to_zwo(workout)
    out = args.output
    if out is None:
        safe = re.sub(r"[^\w\-]+", "-", workout.get("name", "workout")).strip("-").lower()
        out = Path("workouts/generated") / f"{safe}.zwo"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(zwo, encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
