# Intervals.icu — planlagt Fitness / Fatigue (grå strek)

**Grå vertikal linje** = i dag. Kurve **til høyre** = **planlagt** (ikke gjennomført).

## Hva styrer planlagt kurve

1. **WORKOUT** på kalenderen med `icu_training_load` (TSS fra agent-push / `trainingdojo-*.csv` kolonne `tss`).
2. **TARGET**-uker (Ride/Run/Swim load_target) — brukes i ukesammendrag; **sjekk at WORKOUT-sum ≈ TARGET** ellers blir planlagt PMC lav.

Intervals summerer typisk **planlagte økter** fremover. Hvis WORKOUT-TSS per uke er **380** men TARGET står **520**, ser grafen **for lav** ut.

## William (okt 2026)

- **Faktisk** uke 40–41: ~**530–570** load (tung løp).
- Plan **uke 26. okt** var ~**373** WORKOUT-sum → planlagt linje **under** historikk — rettet ved å **skalere TSS** på WORKOUTs til TARGET (~520+) fra 26. okt.
- **Deload 19.–25. okt** (fryst) gir **bevisst** dip i planlagt kurve neste uke — ikke en feil.

## Vedlikehold

Etter CSV-endring:

```bash
python3 scripts/intervals_push_calendar.py --start 2026-10-26 --plan plans/csv/trainingdojo-2026-10-26-des31.csv ...
python3 scripts/push_intervals_targets.py --csv plans/csv/intervals-weekly-targets-2026-10-12-12-31.csv
```

Verifiser: sum `tss` per uke i CSV ≈ `intervals-weekly-targets` rad for `week_start`.
