"""Shared ZWO XML writers — intensities as fractions (bike FTP, run/swim threshold pace)."""

from __future__ import annotations

from pathlib import Path

FTP_NOTE_BIKE = (
    "Bike: Power = fraction of FTP. Set bike FTP in TrainingPeaks Settings → Zones; "
    "watts are calculated on import."
)
RUN_NOTE = (
    "Run: Power = fraction of threshold RUN pace (pace=2 ≈ 10k/threshold reference). "
    "Set run threshold pace in TP Zones — not bike FTP. TP Workout Library ZWO import is bike-only; "
    "use Workout Builder for run or sync from calendar."
)
SWIM_NOTE = (
    "Swim: Power = fraction of threshold SWIM pace (T-pace/CSS). Set swim threshold pace in TP Zones — "
    "not bike FTP. Import via Workout Builder (structured swim), not bulk ZWO."
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
) -> None:
    """steps: (duration_sec, message, power_fraction, optional pace attr for run)"""
    desc = f"{description} — {extra_note}"
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<workout_file>",
        "  <author>Xtri training coach</author>",
        f"  <name>{esc(name)}</name>",
        f"  <description>{esc(desc)}</description>",
        f"  <sportType>{sport}</sportType>",
    ]
    if sport == "run":
        lines.append("  <durationType>time</durationType>")
    lines.append("  <tags/>")
    lines.append("  <workout>")
    for dur, msg, power, pace in steps:
        pace_attr = pace if pace is not None else (run_pace_attr if sport == "run" else "0")
        lines.append(f'    <SteadyState Duration="{dur}" Power="{power:.4f}" pace="{pace_attr}">')
        lines.append(f'      <textevent message="{esc(msg)}" timeoffset="0"/>')
        lines.append("    </SteadyState>")
    lines.extend(["  </workout>", "</workout_file>", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
