# Sykkel med watt i TrainingPeaks (ZWO)

TrainingDojo-CSV legger sykkel på kalenderen som **tekst + varighet**, ikke watt-trinn. For **% FTP / watt** bruker du **.zwo** fra `workouts/zwo/bike/`.

Offisiell TP-hjelp: [Import Planned Workouts (.zwo)](https://help.trainingpeaks.com/hc/en-us/articles/32432105650573-Import-Planned-Workouts-into-TrainingPeaks)

---

## Steg 0 — FTP i TrainingPeaks

1. TP → **Settings** → **Zones** → **FTP** (sykkel)  
2. Legg inn **nåværende FTP** (ikke historisk 410 W)  
3. Oppdater `docs/athlete/profile.md`  

Sykkel-ZWO i repoet bruker **Power="0.xxxx"** (= andel av FTP).

---

## Steg 1 — Filer i repoet

Biblioteket ligger ferdig bygget under `workouts/zwo/bike/` (f.eks. `endurance-90.zwo`, `threshold-5x10.zwo`).

Svøm/løp/styrke er **ikke** ZWO i TP — se [zwo-kun-sykkel.md](zwo-kun-sykkel.md). Regenerere planned-tekst (sykkel beholdes):

```bash
python3 scripts/build_zwo_library.py
```

Zip for bulk-nedlasting:

```bash
./scripts/zip_zwo_library.sh
```

---

## Steg 2 — Importer til Workout Library

1. TP → **Library** → **Workout Library** (mappe, f.eks. «Lofoten coach»)  
2. **⋮** → **Import Workout**  
3. Velg `.zwo` fra `workouts/zwo/bike/`  
4. Dra økten fra biblioteket til kalenderdagen (eller erstatt tekst-rad fra TrainingDojo)

Kalender-hjelp for første 4 uker: `plans/csv/sykkel-zwo-kalender-4uker.csv`

---

## Hybrid med TrainingDojo

1. Importer `plans/csv/trainingdojo-4uker-2026-09-28.csv` (eller `…-uten-sykkel.csv`)  
2. Importer sykkel-ZWO og legg på onsdag/lørdag  
3. Slett duplikat **tekst-sykkel** på samme dag hvis du brukte full CSV

Se også [fit-vs-zwo.md](fit-vs-zwo.md) og [importere-plan-norsk.md](importere-plan-norsk.md).
