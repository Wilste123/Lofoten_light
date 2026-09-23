"""Shared YAML workout parser for bike export scripts."""

from __future__ import annotations

import re
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


def parse_workout_yaml(path: Path) -> dict:
    if yaml is not None:
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f)
    return parse_minimal_yaml(path.read_text(encoding="utf-8"))


def parse_minimal_yaml(text: str) -> dict:
    data: dict = {"name": "Workout", "steps": []}
    step: dict | None = None
    for line in text.splitlines():
        if re.match(r"^\s*-\s+duration_min:", line) or line.strip() == "-":
            if step:
                data["steps"].append(step)
            step = {}
            m = re.search(r"duration_min:\s*(\d+)", line)
            if m:
                step["duration_min"] = int(m.group(1))
            continue
        if step is not None:
            m = re.search(r"power_pct_ftp:\s*(\d+)", line)
            if m:
                step["power_pct_ftp"] = int(m.group(1))
            m = re.search(r"note:\s*(.+)", line)
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


def safe_filename(name: str) -> str:
    return re.sub(r"[^\w\-]+", "-", name).strip("-").lower()
