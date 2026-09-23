"""Felles ZWO-skriving for TrainingPeaks Library-import (kraft-sykkel-format)."""

from __future__ import annotations

from pathlib import Path

FTP_NOTE_BIKE = (
    "Power = andel av sykkel-FTP. Sett FTP under TrainingPeaks Innstillinger → Soner."
)
RUN_NOTE = (
    "IMPORT: TP godtar kun sykkel-ZWO — filen er sportType=bike for import. "
    "Etter import: åpne økt → Bygg → sett sport til Løp → intensitet % terskel-pace "
    "(samme %-tall). Power ≈ % av løpsterskel (lett ~78 %, terskel 100 %). Ikke sykkel-FTP på kalender."
)
SWIM_NOTE = (
    "IMPORT: TP godtar kun sykkel-ZWO — filen er sportType=bike for import. "
    "Etter import: åpne økt → Bygg → sett sport til Svøm → intensitet % T-pace (CSS). "
    "Power ≈ % av svøm-T-pace (lett ~89 %, CSS 100 %). Sett bassenglengde under Utstyr."
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
