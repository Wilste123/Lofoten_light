# Sykkel — kvalitetsøkter (presets)

Erstatt watt med % **gjeldende FTP** fra profile. Oppvarming standard: **15 min** progresjon + 3×30 s fast pedal.

---

## Økt 1 — Sweet spot (tidseffektiv base/build)

**Total ~75 min | TSS ~70–85**

- 15 min oppvarming
- **2×20 min @ 88–93 % FTP** (5 min recovery mellom)
- 10 min nedkjøling

*Plan B:* 2×15 min hvis trött.

---

## Økt 2 — Threshold «over-unders»

**~80 min | TSS ~85–95**

- 15 min oppvarming
- **3×12 min:** 2 min @ 95 %, 2 min @ 105 %, repeat ×3 innen blokken (3 min easy mellom blokker)
- 10 min cooldown

*William:* ikke mer enn 1×/uke i re-etablering.

---

## Økt 3 — VO2 (build)

**~70 min | TSS ~75–90**

- 15 min oppvarming
- **5×3 min @ 115–120 % FTP**, 3 min easy
- 10 min cooldown

---

## Økt 4 — Endurance med «race surges»

**3–4 h | TSS ~180–240**

- 2 h @ 68–72 % FTP
- Hver 30 min: **5 min @ 80 % FTP**
- Resten Z2

---

## Økt 5 — Recovery

**45–60 min | TSS ~25–40**

- Kun 55–65 % FTP; høy kadanse

---

## Plassering i uke

| Økt | Ikke dagen etter … |
|-----|---------------------|
| VO2 | Hard løp |
| Threshold | Brick |
| Lang Z2 | VO2 (heller dag før eller 2 dager mellom) |

## ZWO

Lag YAML i `workouts/` → `scripts/export_zwo.py`.

## HR-fallback

Hvis ingen FTP: threshold ≈ **Z4 HR** hold 2×20 med 5 min pause — RPE 7–8.
