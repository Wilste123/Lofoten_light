"""Shared ZWO XML writers for TrainingPeaks Library import (power-based cycling format)."""

from __future__ import annotations

from pathlib import Path

FTP_NOTE_BIKE = (
    "Power = fraction of bike FTP. Set FTP in TrainingPeaks Settings → Zones."
)
RUN_NOTE = (
    "IMPORT: TP only accepts cycling ZWO — this file is sportType=bike so Library import works. "
    "After import: open workout → Build → set sport to Run → convert intensity to % Threshold Pace "
    "(keep the same % numbers). Power values are already % of run threshold (easy ~78%, threshold 100%)."
)
SWIM_NOTE = (
    "IMPORT: TP only accepts cycling ZWO — this file is sportType=bike so Library import works. "
    "After import: open workout → Build → set sport to Swim → convert intensity to % Threshold Pace "
    "(T-pace/CSS). Power values are % of swim T-pace (easy ~89%, CSS 100%). Set pool length in Equipment."
)


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def write_zwo_power(
    path: Path,
    sport: str,
    name: str,
    description: str,
    steps: list[tuple[int, str, float, str | None]],
    extra_note: str,
    run_pace_attr: str | None = None,
    *,
    tp_library_import: bool = False,
) -> None:
    """If tp_library_import, emit sportType=bike (only format TP Library Import accepts)."""
    desc = f"{description} — {extra_note}"
    xml_sport = "bike" if tp_library_import else sport
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<workout_file>",
        "  <author>Xtri training coach</author>",
        f"  <name>{esc(name)}</name>",
        f"  <description>{esc(desc)}</description>",
        f"  <sportType>{xml_sport}</sportType>",
        "  <tags/>",
        "  <workout>",
    ]
    for dur, msg, power, _pace in steps:
        p = max(power, 0.45) if tp_library_import else power
        lines.append(f'    <SteadyState Duration="{dur}" Power="{p:.4f}" pace="0">')
        lines.append(f'      <textevent message="{esc(msg)}" timeoffset="0"/>')
        lines.append("    </SteadyState>")
    lines.extend(["  </workout>", "</workout_file>", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
