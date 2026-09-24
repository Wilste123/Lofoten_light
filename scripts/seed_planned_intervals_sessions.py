#!/usr/bin/env python3
"""Generator for workouts/planned/{run,swim,bike} Intervals session files."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLANNED = ROOT / "workouts" / "planned"

SESSIONS: dict[str, str] = {}


def add(path: str, body: str) -> None:
    SESSIONS[path] = body.strip() + "\n"


# --- RUN (Intervals syntax: every % → LTHR; repeats = "Main Set Nx" + blank lines) ---

add(
    "run/R01-easy-40.txt",
    """
name: Løp easy 40
sport: run
intervals_target: HR
---
William, rolig løp i dag. Puls er boss — ikke pace på klokka. Terskelpuls ca. 165: hold deg på 134–147 slag i minuttet (easy). Pace kan være 6:35–7:00 per km på flatt underlag; i motvind eller myr, ignorer pace.

Rygg og isjas: hvis nerven bråker, gå 1 min og fortsett rolig. Plan B: 30 min + tøying hjemme.

---intervals---
- Warmup 10m 81-89% LTHR

- 25m 81-89% LTHR

- Cooldown 5m 75-80% LTHR
""",
)

add(
    "run/R01-recovery-35.txt",
    """
name: Løp recovery 35
sport: run
intervals_target: HR
---
Recovery-uke. Kort og lett — under 134 puls hvis du kan.

---intervals---
- 35m 75-80% LTHR
""",
)

add(
    "run/R01-recovery-30.txt",
    """
name: Løp recovery 30
sport: run
intervals_target: HR
---
Søndag lett + ukesopp. 30 min maks. Snakketest hele veien.

---intervals---
- 30m 75-80% LTHR
""",
)

add(
    "run/R02-easy-55-strides.txt",
    """
name: Løp easy med strides
sport: run
intervals_target: HR
---
Easy med seks korte steg på slutten. Strides = 15 sekunder raskere steg, ikke sprint. Hoveddelen skal være 134–147.

Plan B: dropp strides, behold 40 min rolig.

---intervals---
- Warmup 10m 81-89% LTHR

- 30m 81-89% LTHR

Strides 6x
- 15s 95% LTHR
- 60s 81-89% LTHR

- Cooldown 5m 75-80% LTHR
""",
)

add(
    "run/R03-easy-trail-70.txt",
    """
name: Løp terreng / myr lett
sport: run
intervals_target: HR
---
Terreng eller myr — staver om du har. Puls 134–147; bakker tillatt å gå.

Plan B: 45 min flatt samme puls.

---intervals---
- Warmup 10m 81-89% LTHR

- 50m 81-89% LTHR

- Cooldown 5m 75-80% LTHR
""",
)

add(
    "run/R03-trail-55.txt",
    """
name: Løp terreng lett 55
sport: run
intervals_target: HR
---
Kortere trail før FTP-uke. Rolig puls som vanlig.

---intervals---
- Warmup 8m 81-89% LTHR

- 42m 81-89% LTHR

- Cooldown 5m 75-80% LTHR
""",
)

add(
    "run/R04-long-easy-75.txt",
    """
name: Langløp easy 75
sport: run
intervals_target: HR
---
Lang dag, ikke lang hard dag. Puls snitt under 147. Plan B: 60 min.

---intervals---
- Warmup 10m 81-89% LTHR

- 60m 81-89% LTHR

- Cooldown 5m 75-80% LTHR
""",
)

add(
    "run/R04-long-easy-80.txt",
    """
name: Langløp easy 80
sport: run
intervals_target: HR
---
Litt lengre — fortsatt easy. Test fuel etter ca. 60 min hvis du vil.

---intervals---
- Warmup 10m 81-89% LTHR

- 65m 81-89% LTHR

- Cooldown 5m 75-80% LTHR
""",
)

add(
    "run/R-OPV-elghufs-4x3.txt",
    """
name: Elghufs 4×3 min
sport: run
intervals_target: HR
---
OPV elghufs: bratt bakke, staver, lange steg — ikke vanlig motbakkesprint. I drag: puls rundt 155–163. Plan B: 3 drag. Stopp hvis rygg eller isjasnerven sier fra.

---intervals---
- Warmup 15m 75-85% LTHR

Main Set 4x
- 3m 94-99% LTHR
- 3m 70-75% LTHR

- Cooldown 10m 75-85% LTHR
""",
)

add(
    "run/OPV-myr-loping-staver.txt",
    """
name: Myr-løp med staver
sport: run
intervals_target: HR
---
Myr-løp med staver. Puls 134–147. Staver for rytme og overkropp, ikke hero-TSS. Plan B: tredemølle 40 min samme puls.

---intervals---
- Warmup 10m 81-89% LTHR

- 50m 81-89% LTHR

- Cooldown 5m 75-80% LTHR
""",
)

# --- SWIM (unchanged structure, ensure Pace on every step) ---
add(
    "swim/S01-teknikk-a.txt",
    """
name: Svøm teknikk A
sport: swim
---
William, teknikkøkt. RPE 3–5. Basseng 25 m. CSS ca. 2:20 / 100 m i Intervals.

---intervals---
- Warmup 200m 90% Pace

- 8x 50m 88% Pace 15s rest

- 4x 100m 92% Pace 20s rest

- Cooldown 200m 89% Pace
""",
)

add(
    "swim/S02-teknikk-skulder.txt",
    """
name: Svøm teknikk skulder
sport: swim
---
Skuldervennlig. Bytt til rygg ved øm skulder.

---intervals---
- Warmup 300m 90% Pace

- 6x 75m 88% Pace 15s rest

- 4x 50m 90% Pace 20s rest

- Cooldown 200m 89% Pace
""",
)

add(
    "swim/S03-aerob-3x500.txt",
    """
name: Svøm aerob 3×500
sport: swim
---
Aerob svøm. Jevn innsats RPE 5–6.

---intervals---
- Warmup 400m 90% Pace

Main Set 3x
- 500m 94% Pace 25s rest

- Cooldown 200m 89% Pace
""",
)

add(
    "swim/S04-aerob-1500.txt",
    """
name: Svøm aerob 1500
sport: swim
---
1500 kontinuerlig etter oppvarming.

---intervals---
- Warmup 400m 90% Pace

- 1500m 94% Pace

- Cooldown 200m 89% Pace
""",
)

add(
    "swim/S09-recovery.txt",
    """
name: Svøm recovery
sport: swim
---
Recovery. Kort og lett.

---intervals---
- 35m 88-90% Pace
""",
)

# --- BIKE ---
add(
    "bike/endurance-90.txt",
    """
name: Sykkel Z2 90
sport: bike
zwo: workouts/zwo/bike/endurance-90.zwo
---
William, kjedelig og rolig. Ca. 137–151 watt (65–72 % FTP). Plan B: 60 min.

---intervals---
- Warmup 10m 55-60% FTP

- 70m 65-72% FTP

- Cooldown 10m 55% FTP
""",
)

add(
    "bike/endurance-120.txt",
    """
name: Sykkel Z2 120
sport: bike
zwo: workouts/zwo/bike/endurance-120.zwo
---
Lang Z2. Øv drikke siste 30 min.

---intervals---
- Warmup 15m 55-60% FTP

- 90m 65-72% FTP

- Cooldown 15m 55% FTP
""",
)

add(
    "bike/recovery-spin-45.txt",
    """
name: Sykkel recovery 45
sport: bike
zwo: workouts/zwo/bike/recovery-spin-45.zwo
---
Recovery spin. Under 116 W.

---intervals---
- 45m 50-55% FTP
""",
)

add(
    "bike/ftp-ramp-test.txt",
    """
name: FTP ramp test
sport: bike
zwo: workouts/zwo/bike/ftp-ramp-test.zwo
---
Ramp-test. Oppdater FTP etterpå i Intervals og profile.md.

---intervals---
- Følg ramp-test ZWO på sykkel
""",
)

add(
    "bike/sykkel-rest-teknikk-75.txt",
    """
name: Sykkel lett + ettbens teknikk
sport: bike
zwo: workouts/zwo/bike/endurance-90.zwo
---
Rolig Z2 + 4×1,5 min ettbeins lett watt.

---intervals---
- Warmup 20m 60-70% FTP

- 35m 65-72% FTP

Main Set 4x
- 90s 75% FTP
- 90s 60% FTP

- Cooldown 10m 55% FTP
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
