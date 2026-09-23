# ZWO vs FIT (workout files)

| Format | Bruk |
|--------|------|
| **.zwo** | **TrainingPeaks Workout Library** — **kun kraftbasert sykkel** (TP avviser svøm/løp som ZWO) |
| **.fit** (workout) | Garmin / Wahoo **head unit** — ikke TP bibliotek-import |

- **Sykkel:** importer `.zwo` fra `workouts/zwo/bike/` — TP bruker FTP for watt.
- **Svøm / løp / styrke:** `workouts/planned/**/*.txt` + TrainingDojo-kalender — **ikke** ZWO-import. Se [zwo-kun-sykkel.md](zwo-kun-sykkel.md).
- **Fullførte aktiviteter** synkroniseres som aktivitet-FIT til TP — det er ikke det samme som workout-FIT fra biblioteket.

Pakke alt: `./scripts/zip_zwo_library.sh` → `workouts/zwo-all.zip`.
