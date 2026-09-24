#!/usr/bin/env python3
"""Intervals.icu run workout text — Garmin-safe HR syntax."""

from __future__ import annotations

import re


def lint_run_intervals_block(text: str) -> list[str]:
    """Return human-readable problems (empty if ok)."""
    issues: list[str] = []
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("---"):
            continue
        if s.endswith("x") and re.match(r"^.+ \d+x$", s):
            continue  # Main Set 4x
        if re.match(r"^\d+x$", s):
            continue
        if not s.startswith("- "):
            if s in ("Warmup", "Main", "Cooldown", "Main Set"):
                issues.append(f"Linje {i}: '{s}' alene — bruk 'Main Set Nx' + tom linje, eller '- Warmup 10m … LTHR'")
            continue
        step = s[2:]
        if re.search(r"\d+-\d+%(?!\s*(?:LTHR|HR|Pace|bpm))", step):
            issues.append(f"Linje {i}: prosent uten LTHR/HR — tolkes som watt: {s}")
        if "4x (" in step or re.search(r"\d+x\s*\(", step):
            issues.append(f"Linje {i}: bruk 'Main Set Nx' med egne linjer, ikke '4x (...)'")
    return issues


def normalize_run_intervals_block(text: str) -> str:
    """Best-effort cleanup (prefer fixing source files)."""
    return text.strip() + "\n"
