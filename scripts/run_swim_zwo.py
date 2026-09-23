#!/usr/bin/env python3
"""Generer norske løp/svøm/brick-løp .zwo (TP Library-import, sportType=bike)."""

from __future__ import annotations

from pathlib import Path

from zwo_common import RUN_NOTE, SWIM_NOTE, write_zwo_power

ROOT = Path(__file__).resolve().parents[1]
ZWO = ROOT / "workouts" / "zwo"

# Brøk av terskel-pace (løp/svøm) — etter sport-bytte i TP Workout Builder
FRAC = {
    "run_z2": 0.78,
    "run_wu": 0.72,
    "run_tempo": 0.91,
    "run_th": 1.0,
    "run_vo2": 1.08,
    "run_rec": 0.65,
    "run_stride": 1.12,
    "swim_wu": 0.90,
    "swim_aerob": 0.93,
    "swim_css": 1.0,
    "swim_hard": 1.03,
    "swim_easy": 0.89,
    "swim_drill": 0.88,
}


def _steps(blocks: list[tuple[int, str, str]]) -> list[tuple[int, str, float, None]]:
    return [(sec, msg, FRAC[key], None) for sec, msg, key in blocks]


def _write(path: Path, name: str, desc: str, note: str, blocks: list[tuple[int, str, str]]) -> None:
    write_zwo_power(path, "bike", name, desc, _steps(blocks), note, tp_library_import=True)


def export_run_swim_zwo() -> None:
    swim_dir = ZWO / "swim"
    run_dir = ZWO / "run"
    brick_dir = ZWO / "brick"
    for d in (swim_dir, run_dir):
        if d.exists():
            for f in d.glob("*.zwo"):
                f.unlink()
    for f in brick_dir.glob("*-run-*.zwo") if brick_dir.exists() else []:
        f.unlink()
    swim_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    brick_dir.mkdir(parents=True, exist_ok=True)

    swims = [
        (
            "S01-teknikk-a",
            "SVØM S01 Teknikk A",
            "Drill og aerob. RPE 3–5.",
            [
                (600, "Oppvarming 200 mix + 4×50 drill", "swim_wu"),
                (1200, "8×50 drill/svøm 15 s + 4×100 lett 20 s", "swim_drill"),
                (600, "8×25 spark + 100 avslutning", "swim_easy"),
            ],
        ),
        (
            "S02-teknikk-skulder",
            "SVØM S02 Teknikk skulder",
            "Skuldervennlig teknikk.",
            [
                (300, "300 lett", "swim_wu"),
                (1500, "6×75 drill + 4×50 uten crawl", "swim_drill"),
                (420, "200 avslutning", "swim_easy"),
            ],
        ),
        (
            "S03-aerob-3x500",
            "SVØM S03 Aerob 3×500",
            "3×500 m @ RPE 5–6, 25 s pause.",
            [
                (600, "400 oppvarming + 4×50 oppbygging", "swim_wu"),
                (2400, "3×500 jevn 25 s hvile", "swim_aerob"),
                (300, "200 avslutning", "swim_easy"),
            ],
        ),
        (
            "S04-aerob-1500",
            "SVØM S04 Aerob 1500",
            "1500 m kontinuerlig RPE 5–6.",
            [
                (600, "Oppvarming", "swim_wu"),
                (1920, "1500 kontinuerlig — tenk negativ split", "swim_aerob"),
                (480, "Avslutning", "swim_easy"),
            ],
        ),
        (
            "S05-css-10x100",
            "SVØM S05 CSS 10×100",
            "10×100 @ CSS + 10 s pause.",
            [
                (720, "400 oppvarming + 8×50", "swim_wu"),
                (2400, "10×100 @ CSS 10 s hvile", "swim_css"),
                (480, "300 pull avslutning", "swim_easy"),
            ],
        ),
        (
            "S06-css-pyramid",
            "SVØM S06 CSS pyramide",
            "100–200–300–400–300–200–100 @ CSS.",
            [
                (600, "Oppvarming", "swim_wu"),
                (3480, "Pyramidesett 20 s pause mellom", "swim_css"),
                (420, "Avslutning", "swim_easy"),
            ],
        ),
        (
            "S07-race-1900",
            "SVØM S07 Race 1900",
            "Racesim 1,9 km — start kontrollert.",
            [
                (720, "Oppvarming + 4×50 race-følelse", "swim_wu"),
                (2280, "1900 kontinuerlig i våtdrakt", "swim_hard"),
                (300, "Avslutning", "swim_easy"),
            ],
        ),
        (
            "S08-ows-sim",
            "SVØM S08 Åpent vann",
            "Åpent vann — siktning ca. hvert 6. tak.",
            [
                (600, "Oppvarming på land/brygge", "swim_wu"),
                (2400, "400+800+4×50+400 OWS", "swim_aerob"),
                (600, "Lett avslutning", "swim_easy"),
            ],
        ),
        (
            "S09-recovery",
            "SVØM S09 Recovery",
            "Lett bevegelse RPE 2–4.",
            [(2100, "300 + 6×50 + 4×100 pull + 200 lett", "swim_easy")],
        ),
        (
            "S03b-aerob-3x400",
            "SVØM S03b Aerob 3×400",
            "Plan B for S03 — RPE 5–6.",
            [
                (600, "400 oppvarming + 4×50", "swim_wu"),
                (1920, "3×400 jevn 20 s hvile", "swim_aerob"),
                (300, "200 avslutning", "swim_easy"),
            ],
        ),
        (
            "S10-breath-control",
            "SVØM S10 Pust/frekvens",
            "Teknikk — ikke meter-hero.",
            [
                (300, "300 lett", "swim_wu"),
                (1200, "6×50 pust 3/5/7 + 4×100 rolig", "swim_drill"),
                (600, "6×25 avslappet + 100 CD", "swim_easy"),
            ],
        ),
    ]
    for stem, name, desc, blocks in swims:
        _write(swim_dir / f"{stem}.zwo", name, desc, SWIM_NOTE, blocks)

    runs = [
        ("R01-easy-40", "LØP R01 Lett 40", "Sone 2, samtaletempo.", [(2400, "Lett løp RPE 4–5", "run_z2")]),
        ("R14-recovery-30", "LØP R14 Recovery 30", "Recovery — RPE 3–4.", [(1800, "Lett 30 min eller powerwalk", "run_z2")]),
        (
            "R02-easy-55-strides",
            "LØP R02 Lett + strides",
            "50 min + 6×15 s strides.",
            [
                (900, "Lett 15 min", "run_z2"),
                (1800, "Lett 30 min", "run_z2"),
                (180, "6×15 s strides / 60 s", "run_stride"),
                (300, "Avslutning", "run_z2"),
            ],
        ),
        ("R03-easy-trail-70", "LØP R03 Terreng 70", "Terreng RPE 5.", [(4200, "Terreng/grus lett", "run_z2")]),
        (
            "R04-long-easy-90",
            "LØP R04 Lang lett 90",
            "Langløp sone 2.",
            [(5400, "Lang lett — få i deg karbo etter 60 min", "run_z2")],
        ),
        (
            "R05-long-trail-100",
            "LØP R05 Lang terreng 100",
            "Terreng + bakker.",
            [(6000, "Terreng aerob + bakker", "run_z2")],
        ),
        (
            "R06-tempo-2x15",
            "LØP R06 Tempo 2×15",
            "2×15 min @ RPE 7, 3 min jogg.",
            [
                (900, "Oppvarming + strides", "run_wu"),
                (900, "Tempo 1", "run_tempo"),
                (180, "Jogg 3 min", "run_rec"),
                (900, "Tempo 2", "run_tempo"),
                (600, "Avslutning", "run_z2"),
            ],
        ),
    ]
    blocks_5x1k: list[tuple[int, str, str]] = [(900, "Oppvarming 15 min", "run_wu")]
    for i in range(5):
        blocks_5x1k += [(240, f"1 km rep {i + 1} RPE 8", "run_vo2"), (90, "Jogg 90 s", "run_rec")]
    blocks_5x1k.append((600, "Avslutning 10 min", "run_z2"))
    runs.append(("R07-5x1k", "LØP R07 5×1 km", "5×1 km @ 10 km-innsats.", blocks_5x1k))

    blocks_hill: list[tuple[int, str, str]] = [(900, "Oppvarming", "run_wu")]
    for i in range(8):
        blocks_hill += [(90, f"Bakke 90 s #{i + 1} RPE 7–8", "run_vo2"), (120, "Jogg ned", "run_rec")]
    blocks_hill.append((900, "Avslutning", "run_z2"))
    runs.append(("R08-hill-8x90", "LØP R08 Bakke 8×90", "Forberedelse Tjeldbergtind.", blocks_hill))

    blocks_fartlek: list[tuple[int, str, str]] = [(600, "Lett 10 min", "run_z2")]
    for i in range(8):
        blocks_fartlek += [(60, f"Hard 1 min #{i + 1}", "run_vo2"), (120, "Lett 2 min", "run_z2")]
    blocks_fartlek.append((600, "Avslutning 10 min", "run_z2"))
    runs.append(("R09-fartlek-8x1", "LØP R09 Fartlek", "8×1 min hard / 2 lett.", blocks_fartlek))

    runs.append(
        (
            "R10-progressive-long-90",
            "LØP R10 Progressiv 90",
            "30+30+20 min oppbygging.",
            [
                (1800, "S2 30 min", "run_z2"),
                (1800, "Moderat 30 min", "run_tempo"),
                (1200, "HM-tempo 20 min", "run_th"),
                (600, "Lett 10 min", "run_z2"),
            ],
        )
    )

    blocks_6x8: list[tuple[int, str, str]] = [(900, "Oppvarming 15 min", "run_wu")]
    for i in range(6):
        blocks_6x8 += [(480, f"Terskel 8 min #{i + 1} RPE 7–8", "run_th"), (120, "Jogg 2 min", "run_rec")]
    blocks_6x8.append((720, "Avslutning 12 min", "run_z2"))
    runs.append(("R11-6x8-threshold", "LØP R11 6×8 terskel", "Cruise-intervaller.", blocks_6x8))

    blocks_5x10: list[tuple[int, str, str]] = [(900, "Oppvarming", "run_wu")]
    for i in range(5):
        blocks_5x10 += [(600, f"Terskel 10 min #{i + 1}", "run_th"), (180, "Jogg 3 min", "run_rec")]
    blocks_5x10.append((600, "Avslutning", "run_z2"))
    runs.append(("R12-5x10-threshold", "LØP R12 5×10 terskel", "5×10 min @ LT.", blocks_5x10))

    blocks_4x12: list[tuple[int, str, str]] = [(900, "Oppvarming", "run_wu")]
    for i in range(4):
        blocks_4x12 += [(720, f"Cruise 12 min #{i + 1}", "run_th"), (180, "Jogg 3 min", "run_rec")]
    blocks_4x12.append((720, "Avslutning", "run_z2"))
    runs.append(("R13-4x12-cruise", "LØP R13 4×12 cruise", "Halvmaraton-spesifikk.", blocks_4x12))

    for stem, name, desc, blocks in runs:
        _write(run_dir / f"{stem}.zwo", name, desc, RUN_NOTE, blocks)

    bricks = [
        (
            "BR01-run-20",
            "LØP BR01 Løp etter sykkel 20",
            "Etter 90 min sykkel — første 5 min RPE 4.",
            [(300, "Jelly-bein lett 5 min", "run_z2"), (900, "Lett 15 min RPE 5", "run_z2")],
        ),
        (
            "BR02-run-35",
            "LØP BR02 Løp etter sykkel 35",
            "Etter 3 t sone 2 sykkel.",
            [
                (600, "Lett 10 min", "run_z2"),
                (900, "Steady 15 min RPE 5–6", "run_z2"),
                (600, "Lett 10 min", "run_z2"),
            ],
        ),
        (
            "BR03-run-60",
            "LØP BR03 Løp etter sykkel 60",
            "Etter 4 t sykkel — terreng siste 10 min.",
            [
                (900, "Lett 15 min flatt", "run_z2"),
                (1800, "Terreng 30 min", "run_z2"),
                (600, "Bakker 10 min", "run_tempo"),
                (300, "Avslutning 5 min", "run_z2"),
            ],
        ),
    ]
    for stem, name, desc, blocks in bricks:
        _write(brick_dir / f"{stem}.zwo", name, desc, RUN_NOTE, blocks)

    print(f"svøm zwo: {len(swims)}")
    print(f"løp zwo: {len(runs)}")
    print(f"brick løp zwo: {len(bricks)}")


if __name__ == "__main__":
    export_run_swim_zwo()
