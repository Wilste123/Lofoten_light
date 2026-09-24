#!/usr/bin/env python3
"""One-off generator for workouts/planned/{run,swim,bike} Intervals session files."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLANNED = ROOT / "workouts" / "planned"

SESSIONS: dict[str, str] = {}

def add(path: str, body: str) -> None:
    SESSIONS[path] = body.strip() + "\n"


# --- RUN ---
add(
    "run/R01-easy-40.txt",
    """
name: Løp easy 40
sport: run
---
William, rolig løp i dag. Puls er boss — ikke pace på klokka. Terskelpuls ca. 165: hold deg på 134–147 slag i minuttet (easy). Pace kan være 6:35–7:00 per km hvis underlaget er flatt; i motvind eller myr, ignorer pace.

Rygg og isjas: hvis nerven bråker, gå 1 min og fortsett rolig. Plan B: 30 min + tøying hjemme.

---intervals---
Warmup
- 10m 81-89% LTHR
Main
- 25m 81-89% LTHR
Cooldown
- 5m 75-80% LTHR
""",
)

add(
    "run/R01-recovery-35.txt",
    """
name: Løp recovery 35
sport: run
---
Recovery-uke. Kort og lett — under 134 puls hvis du kan. Dette er for å få beina i bevegelse, ikke for å «telle timer».

---intervals---
- 35m 75-80% LTHR
""",
)

add(
    "run/R01-recovery-30.txt",
    """
name: Løp recovery 30
sport: run
---
Søndag lett + ukesopp etterpå. 30 min maks. Snakketest hele veien.

---intervals---
- 30m 75-80% LTHR
""",
)

add(
    "run/R02-easy-55-strides.txt",
    """
name: Løp easy med strides
sport: run
---
Easy med seks korte steg på slutten. Strides = 15 sekunder raskere steg, ikke sprint. Puls kan hoppe litt i stride, men hoveddelen skal være 134–147.

Plan B: dropp strides, behold 40 min rolig.

---intervals---
Warmup
- 10m 81-89% LTHR
Main
- 30m 81-89% LTHR
- 6x 15s 95% LTHR 60s 81-89% LTHR
Cooldown
- 5m 75-80% LTHR
""",
)

add(
    "run/R03-easy-trail-70.txt",
    """
name: Løp terreng / myr lett
sport: run
---
Terreng eller myr — OPV-stil med staver om du har. Puls 134–147; bakker tillatt å gå. Ingen intervaller. Staver er for rytme og overkropp, ikke for å jage fart.

Plan B: 45 min flatt asfalt samme puls.

---intervals---
Warmup
- 10m 81-89% LTHR
Main
- 50m 81-89% LTHR
Cooldown
- 5m 75-80% LTHR
""",
)

add(
    "run/R03-trail-55.txt",
    """
name: Løp terreng lett 55
sport: run
---
Kortere trail-økt før FTP-test uka. Rolig. Samme pulsregel som ellers.

---intervals---
Warmup
- 8m 81-89% LTHR
Main
- 42m 81-89% LTHR
Cooldown
- 5m 75-80% LTHR
""",
)

add(
    "run/R04-long-easy-75.txt",
    """
name: Langløp easy 75
sport: run
---
Lang dag, men ikke lang hard dag. Puls snitt under 147 — cap deg selv i bakker. Ta med væske hvis over 60 min.

Plan B: 60 min og inn, uten skam.

---intervals---
Warmup
- 10m 81-89% LTHR
Main
- 60m 81-89% LTHR
Cooldown
- 5m 75-80% LTHR
""",
)

add(
    "run/R04-long-easy-80.txt",
    """
name: Langløp easy 80
sport: run
---
Litt lengre enn uke 3 — fortsatt easy. Fuel: test noe du tåler (gel eller sportsdrikk) etter ca. 60 min hvis du vil trene mage.

---intervals---
Warmup
- 10m 81-89% LTHR
Main
- 65m 81-89% LTHR
Cooldown
- 5m 75-80% LTHR
""",
)

add(
    "run/R-OPV-elghufs-4x3.txt",
    """
name: Elghufs 4×3 min
sport: run
---
OPV elghufs på løp: bratt bakke, staver, lange steg — ikke vanlig motbakkesprint. I drag: puls rundt 155–163 (terskel-følelse). Plan B: 3×3 min. Stopp hvis rygg eller isjasnerven sier fra.

---intervals---
Warmup
- 15m 75-85% LTHR
Main
- 4x (3m 94-99% LTHR 3m 70-75% LTHR)
Cooldown
- 10m 75-85% LTHR
""",
)

# --- SWIM ---
add(
    "swim/S01-teknikk-a.txt",
    """
name: Svøm teknikk A
sport: swim
---
William, teknikkøkt. RPE 3–5. Fokus: vannfølelse og drill — ikke hero-meter. Basseng 25 m. CSS ca. 2:20 / 100 m i Intervals.

Plan B: kutt 4×100, behold drill.

---intervals---
Warmup
- 200m 90% Pace
Main
- 8x 50m 88% Pace 15s rest
- 4x 100m 92% Pace 20s rest
Cooldown
- 200m 89% Pace
""",
)

add(
    "swim/S02-teknikk-skulder.txt",
    """
name: Svøm teknikk skulder
sport: swim
---
Skuldervennlig. Bytt til rygg på øm skulder. Ingen vond smerte.

---intervals---
Warmup
- 300m 90% Pace
Main
- 6x 75m 88% Pace 15s rest
- 4x 50m 90% Pace 20s rest
Cooldown
- 200m 89% Pace
""",
)

add(
    "swim/S03-aerob-3x500.txt",
    """
name: Svøm aerob 3×500
sport: swim
---
Aerob svøm. Jevn innsats RPE 5–6. 25 s pause mellom 500-ene er ok.

Plan B: 3×400 samme følelse.

---intervals---
Warmup
- 400m 90% Pace
Main
- 3x 500m 94% Pace 25s rest
Cooldown
- 200m 89% Pace
""",
)

add(
    "swim/S04-aerob-1500.txt",
    """
name: Svøm aerob 1500
sport: swim
---
Kontinuerlig 1500 etter oppvarming. Negativ split i hodet — start rolig.

---intervals---
Warmup
- 400m 90% Pace
Main
- 1500m 94% Pace
Cooldown
- 200m 89% Pace
""",
)

add(
    "swim/S09-recovery.txt",
    """
name: Svøm recovery
sport: swim
---
Recovery. Kort og lett i vannet.

---intervals---
- 35m 88-90% Pace
""",
)

# --- BIKE (prose + FTP structure; ZWO still attached on push) ---
add(
    "bike/endurance-90.txt",
    """
name: Sykkel Z2 90
sport: bike
---
William, denne skal være kjedelig. FTP 210 W: sikt på ca. 137–151 watt (65–72 %). Film er ok, watt er viktigere enn underholdning. Drikke hver 20. min.

Plan B: 60 min samme sone.

---intervals---
Warmup
- 10m 55-60% FTP
Main
- 70m 65-72% FTP
Cooldown
- 10m 55% FTP
""",
)

add(
    "bike/endurance-120.txt",
    """
name: Sykkel Z2 120
sport: bike
---
Lang Z2. Siste 30 min: øv med det du skal drikke på sykkel i Lofoten. Rolig watt — ikke «ta igjen» etter en rolig uke.

---intervals---
Warmup
- 15m 55-60% FTP
Main
- 90m 65-72% FTP
Cooldown
- 15m 55% FTP
""",
)

add(
    "bike/recovery-spin-45.txt",
    """
name: Sykkel recovery 45
sport: bike
---
Recovery spin. Under 116 W (ca. 55 % FTP). Høy kadanse, lav watt.

---intervals---
- 45m 50-55% FTP
""",
)

add(
    "bike/ftp-ramp-test.txt",
    """
name: FTP ramp test
sport: bike
---
Ramp-test. Følg ZWO-strukturen på sykkel. Etterpå: oppdater FTP i Intervals og i docs/athlete/profile.md. Ærlig tall — ikke 2019-FTP.

---intervals---
- Se strukturert fil (ramp) — kjør ftp-ramp-test.zwo på sykkel
""",
)

add(
    "bike/sykkel-rest-teknikk-75.txt",
    """
name: Sykkel lett + ettbens teknikk
sport: bike
---
OPV-inspirert: mesteparten rolig Z2, deretter 4×1,5 min ettbeins på lett watt. Fokus runde bevegelse, ikke TSS.

---intervals---
Warmup
- 20m 60-70% FTP
Main
- 35m 65-72% FTP
- 4x 90s 75% FTP 90s 60% FTP
Cooldown
- 10m 55% FTP
""",
)


def main() -> None:
    for rel, body in SESSIONS.items():
        path = PLANNED / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body.strip() + "\n", encoding="utf-8")
        print("wrote", path.relative_to(ROOT))


if __name__ == "__main__":
    main()
