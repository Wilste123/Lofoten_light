#!/usr/bin/env python3
"""Regenerate plan CSV from markdown week files (optional maintenance)."""
from __future__ import annotations

import csv
from pathlib import Path

# Static export already in plans/csv/ — this script documents column schema for future weeks.
SCHEMA = [
    "week",
    "day_number",
    "date",
    "weekday",
    "sport",
    "subtype",
    "title",
    "duration_minutes",
    "tss_estimate",
    "phase",
    "workout_id",
    "description",
]

if __name__ == "__main__":
    print("Week plans CSV: plans/csv/ukeplan-2026-09-28-4uker.csv")
    print("Columns:", ", ".join(SCHEMA))
