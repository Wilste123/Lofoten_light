#!/usr/bin/env python3
"""One-shot builder: write all workout library .zwo files under workouts/zwo/."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "workouts" / "zwo"
BIKE_SRC = ROOT / "workouts" / "exports" / "zwo"  # legacy one-time copy source; remove after migrate
BIKE_OUT = OUT / "bike"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def write_zwo(
    path: Path,
    sport: str,
    name: str,
    description: str,
    steps: list[tuple[int, str, float | None]],
) -> None:
    """steps: (duration_sec, message, power_fraction or None for non-bike)"""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<workout_file>",
        "  <author>Xtri training coach</author>",
        f"  <name>{esc(name)}</name>",
        f"  <description>{esc(description)}</description>",
        f"  <sportType>{sport}</sportType>",
        "  <tags/>",
        "  <workout>",
    ]
    for dur, msg, power in steps:
        p = f"{power:.4f}" if power is not None else "0"
        lines.append(f'    <SteadyState Duration="{dur}" Power="{p}" pace="0">')
        lines.append(f'      <textevent message="{esc(msg)}" timeoffset="0"/>')
        lines.append("    </SteadyState>")
    lines.extend(["  </workout>", "</workout_file>", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def steady_block(minutes: int, msg: str) -> list[tuple[int, str, float | None]]:
    return [(minutes * 60, msg, None)]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    BIKE_OUT.mkdir(parents=True, exist_ok=True)
    if BIKE_SRC.is_dir():
        for src in sorted(BIKE_SRC.glob("*.zwo")):
            shutil.copy2(src, BIKE_OUT / src.name)
    elif not any(BIKE_OUT.glob("*.zwo")):
        raise SystemExit(
            "No bike .zwo found. Add files under workouts/zwo/bike/ "
            "(or temporarily workouts/exports/zwo/)."
        )

    for sub in ("swim", "run", "strength", "brick"):
        p = OUT / sub
        if p.is_dir():
            shutil.rmtree(p)

    # Swim
    swim = OUT / "swim"
    write_zwo(
        swim / "S01-teknikk-a.zwo",
        "swim",
        "S01 Teknikk A",
        "Drill + aerob. RPE 3-5.",
        [
            (600, "WU 200 mix + 4x50 drill", None),
            (1200, "8x50 drill/swim 15s + 4x100 easy 20s", None),
            (600, "8x25 kick + 100 CD", None),
        ],
    )
    write_zwo(
        swim / "S02-teknikk-skulder.zwo",
        "swim",
        "S02 Teknikk skulder",
        "Skuldervennlig teknikk.",
        [(300, "300 easy", None), (1500, "6x75 drill + 4x50 non-free", None), (420, "200 CD", None)],
    )
    write_zwo(
        swim / "S03-aerob-3x500.zwo",
        "swim",
        "S03 Aerob 3x500",
        "3x500 @ RPE 5-6, 25s pause.",
        [(600, "400 WU + 4x50 build", None), (2400, "3x500 steady 25s rest", None), (300, "200 CD", None)],
    )
    write_zwo(
        swim / "S04-aerob-1500.zwo",
        "swim",
        "S04 Aerob 1500",
        "1500 m kontinuerlig RPE 5-6.",
        [(600, "WU", None), (1920, "1500 continuous negative split mindset", None), (480, "CD", None)],
    )
    write_zwo(
        swim / "S05-css-10x100.zwo",
        "swim",
        "S05 CSS 10x100",
        "10x100 @ CSS +10s pause.",
        [(720, "400 WU + 8x50", None), (2400, "10x100 @ CSS 10s rest", None), (480, "300 pull CD", None)],
    )
    write_zwo(
        swim / "S06-css-pyramid.zwo",
        "swim",
        "S06 CSS pyramid",
        "100-200-300-400-300-200-100 @ CSS.",
        [(600, "WU", None), (3480, "Pyramid sets 20s rest between", None), (420, "CD", None)],
    )
    write_zwo(
        swim / "S07-race-1900.zwo",
        "swim",
        "S07 Race 1900",
        "Race sim 1.9 km — start kontrollert.",
        [(720, "WU + 4x50 race feel", None), (2280, "1900 continuous wetsuit", None), (300, "CD", None)],
    )
    write_zwo(
        swim / "S08-ows-sim.zwo",
        "swim",
        "S08 OWS sim",
        "Åpent vann sighting 6 tak.",
        [(600, "Shore warm-up", None), (2400, "400+800+4x50+400 OWS", None), (600, "Easy CD", None)],
    )
    write_zwo(
        swim / "S09-recovery.zwo",
        "swim",
        "S09 Recovery swim",
        "Lett bevegelse RPE 2-4.",
        [(2100, "300 + 6x50 + 4x100 pull + 200 easy", None)],
    )

    # Run
    run = OUT / "run"
    write_zwo(run / "R01-easy-40.zwo", "run", "R01 Easy 40", "Z2 samtale.", steady_block(40, "Easy run RPE 4-5"))
    write_zwo(
        run / "R02-easy-55-strides.zwo",
        "run",
        "R02 Easy + strides",
        "50 min + 6x15s strides.",
        [(900, "Easy 15", None), (1800, "Easy 30", None), (180, "6x15s strides / 60s", None), (300, "CD", None)],
    )
    write_zwo(run / "R03-easy-trail-70.zwo", "run", "R03 Trail 70", "Trail RPE 5.", steady_block(70, "Trail/grus easy"))
    write_zwo(run / "R04-long-easy-90.zwo", "run", "R04 Long 90", "Langløp Z2.", steady_block(90, "Long easy — fuel after 60 min"))
    write_zwo(run / "R05-long-trail-100.zwo", "run", "R05 Trail 100", "Terreng + hike.", steady_block(100, "Trail aerobic + hills"))
    write_zwo(
        run / "R06-tempo-2x15.zwo",
        "run",
        "R06 Tempo 2x15",
        "2x15 min @ RPE 7, 3 min jog.",
        [(900, "WU + strides", None), (900, "Tempo 1", None), (180, "Jog 3", None), (900, "Tempo 2", None), (600, "CD", None)],
    )
    steps_5x1k = [(900, "WU 15", None)]
    for i in range(5):
        steps_5x1k += [(240, f"1k rep {i+1} RPE 8", None), (90, "Jog 90s", None)]
    steps_5x1k.append((600, "CD 10", None))
    write_zwo(run / "R07-5x1k.zwo", "run", "R07 5x1 km", "5x1 km @ 10k effort.", steps_5x1k)
    steps_hill = [(900, "WU", None)]
    for i in range(8):
        steps_hill += [(90, f"Hill 90s #{i+1} RPE 7-8", None), (120, "Jog down", None)]
    steps_hill.append((900, "CD", None))
    write_zwo(run / "R08-hill-8x90.zwo", "run", "R08 Hill 8x90", "Bakke Tjeldbergtind prep.", steps_hill)
    steps_fartlek = [(600, "Easy 10", None)]
    for i in range(8):
        steps_fartlek += [(60, f"Hard 1 min #{i+1}", None), (120, "Easy 2 min", None)]
    steps_fartlek.append((600, "CD 10", None))
    write_zwo(run / "R09-fartlek-8x1.zwo", "run", "R09 Fartlek", "8x1 min hard / 2 easy.", steps_fartlek)
    write_zwo(
        run / "R10-progressive-long-90.zwo",
        "run",
        "R10 Progressive 90",
        "30+30+20 min build.",
        [(1800, "Z2 30", None), (1800, "Mod 30", None), (1200, "MP-HM 20", None), (600, "Easy 10", None)],
    )
    steps_6x8 = [(900, "WU 15", None)]
    for i in range(6):
        steps_6x8 += [(480, f"Threshold 8 min #{i+1} RPE 7-8", None), (120, "Jog 2 min", None)]
    steps_6x8.append((720, "CD 12", None))
    write_zwo(run / "R11-6x8-threshold.zwo", "run", "R11 6x8 threshold", "Cruise intervals.", steps_6x8)
    steps_5x10 = [(900, "WU", None)]
    for i in range(5):
        steps_5x10 += [(600, f"Threshold 10 min #{i+1}", None), (180, "Jog 3 min", None)]
    steps_5x10.append((600, "CD", None))
    write_zwo(run / "R12-5x10-threshold.zwo", "run", "R12 5x10 threshold", "5x10 min @ LT.", steps_5x10)
    steps_4x12 = [(900, "WU", None)]
    for i in range(4):
        steps_4x12 += [(720, f"Cruise 12 min #{i+1}", None), (180, "Jog 3 min", None)]
    steps_4x12.append((720, "CD", None))
    write_zwo(run / "R13-4x12-cruise.zwo", "run", "R13 4x12 cruise", "Halvmaraton spesifikk.", steps_4x12)

    # Strength (duration blocks + text = follow ST in plan)
    strg = OUT / "strength"
    write_zwo(
        strg / "ST01-base.zwo",
        "other",
        "ST01 Styrke A base",
        "Goblet squat RDL planke band calf dead bug — 35 min.",
        [(2100, "Strength A: 3x10 squat, 3x8 RDL/side, planks, band, calf, dead bug", None)],
    )
    write_zwo(
        strg / "ST02-build.zwo",
        "other",
        "ST02 Styrke B build",
        "Trap bar hip thrust step-down carry — 40 min.",
        [(2400, "Strength B: deadlift/hip thrust, step-down, Copenhagen, carry, push-up", None)],
    )
    write_zwo(
        strg / "ST03-recovery.zwo",
        "other",
        "ST03 Styrke recovery",
        "Mobilitet lett 25 min.",
        [(1500, "Band walks, glute bridge, bird dog, stretch", None)],
    )

    # Brick: bike portion as zwo + text for run (run file separate on calendar)
    brick = OUT / "brick"
    brick.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BIKE_OUT / "endurance-90.zwo", brick / "BR01-bike-90.zwo")
    write_zwo(
        brick / "BR01-run-20.zwo",
        "run",
        "BR01 Run off bike 20",
        "Etter 90 min sykkel — første 5 min RPE 4.",
        [(300, "Jelly legs easy 5", None), (900, "Easy 15 RPE 5", None)],
    )
    shutil.copy2(BIKE_OUT / "endurance-180.zwo", brick / "BR02-bike-180.zwo")
    write_zwo(
        brick / "BR02-run-35.zwo",
        "run",
        "BR02 Run off bike 35",
        "Etter 3h Z2 sykkel.",
        [(600, "Easy 10", None), (900, "Steady 15 RPE 5-6", None), (600, "Easy 10", None)],
    )
    shutil.copy2(BIKE_OUT / "progressive-long-240.zwo", brick / "BR03-bike-240.zwo")
    write_zwo(
        brick / "BR03-run-60.zwo",
        "run",
        "BR03 Run off bike 60",
        "Etter 4h sykkel — terreng siste 10 min.",
        [(900, "Easy 15 flat", None), (1800, "Trail 30", None), (600, "Hills 10", None), (300, "CD 5", None)],
    )

    print(f"Wrote library to {OUT}")
    print(f"  bike: {len(list(BIKE_OUT.glob('*.zwo')))}")
    print(f"  swim: {len(list(swim.glob('*.zwo')))}")
    print(f"  run: {len(list(run.glob('*.zwo')))}")
    print(f"  strength: {len(list(strg.glob('*.zwo')))}")
    print(f"  brick: {len(list(brick.glob('*.zwo')))}")


if __name__ == "__main__":
    main()
