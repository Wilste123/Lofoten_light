# Sykkel — kvalitetsøkter (presets)

Erstatt watt med % **gjeldende FTP** fra profile. Oppvarming standard: **15 min** progresjon + 3×30 s fast pedal.

## Forskningsforankring (kort)

- **Lav intensitet** utgjør bulk av volum hos elite utholdenhet (~80 % Z1–Z2; Seiler & Tønnessen 2009).
- **Threshold / MLSS:** arbeid ved eller rett under FTP forbedrer tid ved steady state (Laursen & Jenkins 2002).
- **Fraksjonert terskel** (f.eks. **5×10 min @ ~98 % FTP**): flere kortere boutar vs. 2×20 — høy tid nær MLSS med kortere recovery enn én 50 min blokk (Billat et al. — kort vs lang intervall; anvendt i sykkelcoaching som «5×10 FTP»).
- **VO2max:** 3–5 min reps @ 106–120 % FTP (Midgley et al. 2006 — interval duration and intensity).

Roter **én** hard sykkeløkt/uke i re-etablering, **1–2** i build. Se `workouts/index.md` B06–B11, **B15–B16**.

---

## Øktbibliotek (repo)

| ID | Økt | Fil |
|----|------|-----|
| B08 | 2×20 threshold | `bike/threshold-2x20.yaml` |
| **B15** | **5×10 threshold** | `bike/threshold-5x10.yaml` |
| **B16** | **4×12 threshold** | `bike/threshold-4x12.yaml` |
| B06 | Sweet spot 2×20 | `bike/sweet-spot-2x20.yaml` |
| B10 | VO2 5×3 | `bike/vo2-5x3.yaml` |

---

## Økt 1 — Sweet spot (tidseffektiv base/build)

**Total ~75 min | TSS ~70–85** — se `bike/sweet-spot-2x20.yaml`

## Økt 2 — Threshold 2×20

Se `bike/threshold-2x20.yaml`

## Økt 3 — Threshold 5×10 (lang fraksjonert terskel)

**~95 min | TSS ~95** — `bike/threshold-5x10.yaml`

**Når:** build, når 2×20 er gjennomført 2–3 ganger uten overreaching.  
**Ikke:** recovery-uke eller uke med R11/R12 hard løp.

## Økt 4 — Over-unders

Se `bike/threshold-over-under.yaml`

## Økt 5 — VO2 5×3

Se `bike/vo2-5x3.yaml`

## Plassering i uke

| Økt | Ikke dagen etter … |
|-----|---------------------|
| 5×10 / 4×12 threshold | Hard løp (6×8) |
| VO2 | Brick |
| Lang Z2 | VO2 (heller 2 dager mellom) |

## HR-fallback

Hvis ingen FTP: threshold ≈ **Z4 HR** hold; 5×10 = 10 min @ Z4 med 5 min Z1 mellom.

## ZWO

`./scripts/export_all_zwo.sh`
