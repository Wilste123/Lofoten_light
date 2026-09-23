# ZWO vs FIT (workout files)

| Format | Bruk |
|--------|------|
| **.zwo** | **TrainingPeaks Workout Library** — planlagte økter (sykkel med watt; svøm/løp/styrke som varighet + tekststeg) |
| **.fit** (workout) | Garmin / Wahoo **head unit** — ikke TP bibliotek-import |

Dette repoet har **kun `.zwo`** under `workouts/zwo/`.

- **Sykkel:** importer `.zwo` fra `workouts/zwo/bike/` — TP bruker FTP for watt.
- **Svøm / løp / styrke / brick:** importer fra `workouts/zwo/swim|run|strength|brick/`. Struktur i TP varierer; filene har `sportType` og `textevent` per blokk.
- **Fullførte aktiviteter** synkroniseres som aktivitet-FIT til TP — det er ikke det samme som workout-FIT fra biblioteket.

Pakke alt: `./scripts/zip_zwo_library.sh` → `workouts/zwo-all.zip`.
