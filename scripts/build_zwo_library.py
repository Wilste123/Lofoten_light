#!/usr/bin/env python3
"""Build workout library: bike (+ brick bike) as .zwo; swim/run/strength as planned .txt for TP calendar."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZWO = ROOT / "workouts" / "zwo"
PLANNED = ROOT / "workouts" / "planned"
BIKE_SRC = ROOT / "workouts" / "exports" / "zwo"
BIKE_OUT = ZWO / "bike"


# TrainingPeaks intensity (not watt) — see docs/trainingpeaks/intensitet-svom-lop.md
RUN_TP = "Run → Workout Builder: % Threshold Pace OR % LTHR (not power)"
SWIM_TP = "Swim → Workout Builder: % Threshold swim pace (T-pace/CSS); pool length in Equipment"
ST_TP = "Other → duration + notes; optional RPE"

RUN_Z2 = "% LTHR 80-89% (or RPE 4-5)"
RUN_WU = "% LTHR Z1-Z2"
RUN_TEMPO = "% threshold pace 88-94%"
RUN_TH = "% threshold pace 95-105%"
RUN_VO2 = "% threshold pace 102-115% or RPE 8-9"
RUN_REC = "Recover — % LTHR Z1"
RUN_STRIDE = "Strides — RPE 7-8 for 15s, easy between"

SWIM_WU = "% T-pace 89-92% or RPE 3-4"
SWIM_AEROB = "% T-pace 92-94%"
SWIM_CSS = "% T-pace ~100%"
SWIM_HARD = "% T-pace 99-106%"
SWIM_EASY = "% T-pace 89-90% or RPE 2-4"
SWIM_REST = "Recover (duration), target pace 0"


def write_planned(
    path: Path,
    sport: str,
    name: str,
    description: str,
    tp_intensity: str,
    steps: list[tuple[str, str, str]],
    duration_min: int | None = None,
) -> None:
    """steps: (duration label, instruction, TP target for Workout Builder)"""
    lines = [
        f"name: {name}",
        f"sport: {sport}",
        f"description: {description}",
        f"tp_intensity: {tp_intensity}",
    ]
    if duration_min is not None:
        lines.append(f"duration_min: {duration_min}")
    lines.append(
        "trainingpeaks: Builder or TrainingDojo; mirror ZWO in workouts/zwo/ (pace zones, not bike FTP)"
    )
    lines.append("steps:")
    for dur, msg, tp in steps:
        lines.append(f"  - {dur} | {msg} | tp_target: {tp}")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def steps_from_seconds(
    blocks: list[tuple[int, str] | tuple[int, str, str]],
    default_tp: str = "",
) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    for item in blocks:
        if len(item) == 2:
            sec, msg = item
            tp = default_tp
        else:
            sec, msg, tp = item
        m, s = divmod(sec, 60)
        label = f"{m}:{s:02d}" if s else f"{m}:00"
        out.append((label, msg, tp))
    return out


def total_min(blocks: list[tuple[int, str] | tuple[int, str, str]]) -> int:
    return sum(item[0] for item in blocks) // 60


def main() -> None:
    ZWO.mkdir(parents=True, exist_ok=True)
    scripts = ROOT / "scripts"
    manifest = ROOT / "workouts" / "bike" / "manifest.json"
    if not manifest.is_file():
        if any((ZWO / "bike").glob("*.zwo")):
            subprocess.run(
                [sys.executable, "compile_bike_manifest.py"], check=True, cwd=scripts
            )
        else:
            raise SystemExit("No bike workouts. Add workouts/zwo/bike/*.zwo or manifest.json.")
    subprocess.run([sys.executable, "export_bike_zwo.py"], check=True, cwd=scripts)

    # Remove non-TP ZWO (swim/run/strength/run-off-bike) if present from older builds
    for sub in ("swim", "run", "strength"):
        p = ZWO / sub
        if p.is_dir():
            shutil.rmtree(p)
    brick_zwo = ZWO / "brick"
    if brick_zwo.is_dir():
        for f in brick_zwo.glob("*-run-*.zwo"):
            f.unlink()

    if PLANNED.exists():
        shutil.rmtree(PLANNED)
    PLANNED.mkdir(parents=True)

    def swim(path: str, name: str, desc: str, blocks: list[tuple[int, str] | tuple[int, str, str]]) -> None:
        write_planned(
            PLANNED / "swim" / f"{path}.txt",
            "swim",
            name,
            desc,
            SWIM_TP,
            steps_from_seconds(blocks, SWIM_AEROB),
            total_min(blocks),
        )

    def run(
        path: str,
        name: str,
        desc: str,
        blocks: list[tuple[int, str] | tuple[int, str, str]],
        step_tp_default: str = RUN_Z2,
    ) -> None:
        write_planned(
            PLANNED / "run" / f"{path}.txt",
            "run",
            name,
            desc,
            RUN_TP,
            steps_from_seconds(blocks, step_tp_default),
            total_min(blocks),
        )

    def strength(path: str, name: str, desc: str, blocks: list[tuple[int, str] | tuple[int, str, str]]) -> None:
        write_planned(
            PLANNED / "strength" / f"{path}.txt",
            "strength",
            name,
            desc,
            ST_TP,
            steps_from_seconds(blocks, "RPE 5-6"),
            total_min(blocks),
        )

    swim(
        "S01-teknikk-a",
        "S01 Teknikk A",
        "Drill + aerob. RPE 3-5.",
        [
            (600, "WU 200 mix + 4x50 drill", SWIM_WU),
            (1200, "8x50 drill/swim 15s + 4x100 easy 20s", "RPE 3-5 (rename steps for drills)"),
            (600, "8x25 kick + 100 CD", SWIM_EASY),
        ],
    )
    swim(
        "S02-teknikk-skulder",
        "S02 Teknikk skulder",
        "Skuldervennlig teknikk.",
        [
            (300, "300 easy", SWIM_WU),
            (1500, "6x75 drill + 4x50 non-free", "RPE 3-5"),
            (420, "200 CD", SWIM_EASY),
        ],
    )
    swim(
        "S03-aerob-3x500",
        "S03 Aerob 3x500",
        "3x500 @ RPE 5-6, 25s pause.",
        [(600, "400 WU + 4x50 build"), (2400, "3x500 steady 25s rest"), (300, "200 CD")],
    )
    swim(
        "S04-aerob-1500",
        "S04 Aerob 1500",
        "1500 m kontinuerlig RPE 5-6.",
        [(600, "WU"), (1920, "1500 continuous negative split mindset"), (480, "CD")],
    )
    swim(
        "S05-css-10x100",
        "S05 CSS 10x100",
        "10x100 @ CSS +10s pause.",
        [(720, "400 WU + 8x50"), (2400, "10x100 @ CSS 10s rest"), (480, "300 pull CD")],
    )
    swim(
        "S06-css-pyramid",
        "S06 CSS pyramid",
        "100-200-300-400-300-200-100 @ CSS.",
        [(600, "WU"), (3480, "Pyramid sets 20s rest between"), (420, "CD")],
    )
    swim(
        "S07-race-1900",
        "S07 Race 1900",
        "Race sim 1.9 km — start kontrollert.",
        [(720, "WU + 4x50 race feel"), (2280, "1900 continuous wetsuit"), (300, "CD")],
    )
    swim(
        "S08-ows-sim",
        "S08 OWS sim",
        "Åpent vann sighting 6 tak.",
        [(600, "Shore warm-up"), (2400, "400+800+4x50+400 OWS"), (600, "Easy CD")],
    )
    swim("S09-recovery", "S09 Recovery swim", "Lett bevegelse RPE 2-4.", [(2100, "300 + 6x50 + 4x100 pull + 200 easy", SWIM_EASY)])

    run("R01-easy-40", "R01 Easy 40", "Z2 samtale.", [(2400, "Easy run RPE 4-5")])
    run(
        "R02-easy-55-strides",
        "R02 Easy + strides",
        "50 min + 6x15s strides.",
        [
            (900, "Easy 15", RUN_Z2),
            (1800, "Easy 30", RUN_Z2),
            (180, "6x15s strides / 60s", RUN_STRIDE),
            (300, "CD", RUN_Z2),
        ],
    )
    run("R03-easy-trail-70", "R03 Trail 70", "Trail RPE 5.", [(4200, "Trail/grus easy")])
    run("R04-long-easy-90", "R04 Long 90", "Langløp Z2.", [(5400, "Long easy — fuel after 60 min")])
    run("R05-long-trail-100", "R05 Trail 100", "Terreng + hike.", [(6000, "Trail aerobic + hills")])
    run(
        "R06-tempo-2x15",
        "R06 Tempo 2x15",
        "2x15 min @ RPE 7, 3 min jog.",
        [
            (900, "WU + strides", RUN_WU),
            (900, "Tempo 1", RUN_TEMPO),
            (180, "Jog 3", RUN_REC),
            (900, "Tempo 2", RUN_TEMPO),
            (600, "CD", RUN_Z2),
        ],
    )
    blocks_5x1k: list[tuple[int, str, str]] = [(900, "WU 15", RUN_WU)]
    for i in range(5):
        blocks_5x1k += [(240, f"1k rep {i+1} RPE 8", RUN_VO2), (90, "Jog 90s", RUN_REC)]
    blocks_5x1k.append((600, "CD 10", RUN_Z2))
    run("R07-5x1k", "R07 5x1 km", "5x1 km @ 10k effort.", blocks_5x1k)
    blocks_hill: list[tuple[int, str, str]] = [(900, "WU", RUN_WU)]
    for i in range(8):
        blocks_hill += [(90, f"Hill 90s #{i+1} RPE 7-8", RUN_VO2), (120, "Jog down", RUN_REC)]
    blocks_hill.append((900, "CD", RUN_Z2))
    run("R08-hill-8x90", "R08 Hill 8x90", "Bakke Tjeldbergtind prep.", blocks_hill)
    blocks_fartlek: list[tuple[int, str, str]] = [(600, "Easy 10", RUN_Z2)]
    for i in range(8):
        blocks_fartlek += [(60, f"Hard 1 min #{i+1}", RUN_VO2), (120, "Easy 2 min", RUN_Z2)]
    blocks_fartlek.append((600, "CD 10", RUN_Z2))
    run("R09-fartlek-8x1", "R09 Fartlek", "8x1 min hard / 2 easy.", blocks_fartlek)
    run(
        "R10-progressive-long-90",
        "R10 Progressive 90",
        "30+30+20 min build.",
        [
            (1800, "Z2 30", RUN_Z2),
            (1800, "Mod 30", RUN_TEMPO),
            (1200, "MP-HM 20", RUN_TH),
            (600, "Easy 10", RUN_Z2),
        ],
    )
    blocks_6x8: list[tuple[int, str, str]] = [(900, "WU 15", RUN_WU)]
    for i in range(6):
        blocks_6x8 += [(480, f"Threshold 8 min #{i+1} RPE 7-8", RUN_TH), (120, "Jog 2 min", RUN_REC)]
    blocks_6x8.append((720, "CD 12", RUN_Z2))
    run("R11-6x8-threshold", "R11 6x8 threshold", "Cruise intervals.", blocks_6x8)
    blocks_5x10: list[tuple[int, str, str]] = [(900, "WU", RUN_WU)]
    for i in range(5):
        blocks_5x10 += [(600, f"Threshold 10 min #{i+1}", RUN_TH), (180, "Jog 3 min", RUN_REC)]
    blocks_5x10.append((600, "CD", RUN_Z2))
    run("R12-5x10-threshold", "R12 5x10 threshold", "5x10 min @ LT.", blocks_5x10)
    blocks_4x12: list[tuple[int, str, str]] = [(900, "WU", RUN_WU)]
    for i in range(4):
        blocks_4x12 += [(720, f"Cruise 12 min #{i+1}", RUN_TH), (180, "Jog 3 min", RUN_REC)]
    blocks_4x12.append((720, "CD", RUN_Z2))
    run("R13-4x12-cruise", "R13 4x12 cruise", "Halvmaraton spesifikk.", blocks_4x12)

    strength(
        "ST01-base",
        "ST01 Styrke A base",
        "Goblet squat RDL planke band calf dead bug — 35 min.",
        [(2100, "Strength A: 3x10 squat, 3x8 RDL/side, planks, band, calf, dead bug")],
    )
    strength(
        "ST02-build",
        "ST02 Styrke B build",
        "Trap bar hip thrust step-down carry — 40 min.",
        [(2400, "Strength B: deadlift/hip thrust, step-down, Copenhagen, carry, push-up")],
    )
    strength(
        "ST03-recovery",
        "ST03 Styrke recovery",
        "Mobilitet lett 25 min.",
        [(1500, "Band walks, glute bridge, bird dog, stretch")],
    )

    brick_zwo.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BIKE_OUT / "endurance-90.zwo", brick_zwo / "BR01-bike-90.zwo")
    shutil.copy2(BIKE_OUT / "endurance-180.zwo", brick_zwo / "BR02-bike-180.zwo")
    shutil.copy2(BIKE_OUT / "progressive-long-240.zwo", brick_zwo / "BR03-bike-240.zwo")

    write_planned(
        PLANNED / "brick" / "BR01-run-20.txt",
        "run",
        "BR01 Run off bike 20",
        "Etter 90 min sykkel — første 5 min RPE 4.",
        RUN_TP,
        steps_from_seconds([(300, "Jelly legs easy 5", RUN_Z2), (900, "Easy 15 RPE 5", RUN_Z2)]),
        20,
    )
    write_planned(
        PLANNED / "brick" / "BR02-run-35.txt",
        "run",
        "BR02 Run off bike 35",
        "Etter 3h Z2 sykkel.",
        RUN_TP,
        steps_from_seconds(
            [(600, "Easy 10", RUN_Z2), (900, "Steady 15 RPE 5-6", RUN_Z2), (600, "Easy 10", RUN_Z2)]
        ),
        35,
    )
    write_planned(
        PLANNED / "brick" / "BR03-run-60.txt",
        "run",
        "BR03 Run off bike 60",
        "Etter 4h sykkel — terreng siste 10 min.",
        RUN_TP,
        steps_from_seconds(
            [
                (900, "Easy 15 flat", RUN_Z2),
                (1800, "Trail 30", RUN_Z2),
                (600, "Hills 10", RUN_TEMPO),
                (300, "CD 5", RUN_Z2),
            ]
        ),
        60,
    )

    subprocess.run([sys.executable, "planned_to_zwo.py"], check=True, cwd=scripts)

    print(f"Bike ZWO (TP import, uses bike FTP): {ZWO / 'bike'}")
    print(f"  bike: {len(list((ZWO / 'bike').glob('*.zwo')))}")
    print(f"  brick bike zwo: {len(list(brick_zwo.glob('*.zwo')))}")
    print(f"Run/swim ZWO (threshold pace fractions, not bike FTP): {ZWO / 'run'}, {ZWO / 'swim'}")
    print(f"Planned text + strength TP guide: {PLANNED}, workouts/strength/trainingpeaks/")
    for sub in ("swim", "run", "strength", "brick"):
        d = PLANNED / sub
        print(f"  planned/{sub}: {len(list(d.glob('*.txt'))) if d.is_dir() else 0}")


if __name__ == "__main__":
    main()
