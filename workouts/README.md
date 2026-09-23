# Treningsbibliotek (kun ZWO)

Alle økter ligger som **`.zwo`** under `workouts/zwo/`. Det er én filtype for sykkel, svøm, løp, styrke og brick.

| Mappe | Innhold |
|-------|---------|
| `zwo/bike/` | Sykkel med **watt** (`<target>` = % FTP) |
| `zwo/swim/` | Svøm — varighet + tekstinstruksjoner (`textevent`) |
| `zwo/run/` | Løp — varighet + pace/soner i tekst |
| `zwo/strength/` | Styrke — blokker som tekst |
| `zwo/brick/` | Brick (sykkel-ZWO + løp-ZWO i samme mappe per økt) |

**Oversikt:** [index.md](index.md)

## TrainingPeaks

1. **Sykkel:** Workout Library → Import → velg `.zwo` fra `zwo/bike/` (strukturert watt).
2. **Svøm / løp / styrke:** Importer tilsvarende `.zwo` fra `zwo/swim/`, `zwo/run/`, `zwo/strength/`. Varighet og steg ligger i filen; sykkel får full watt-struktur i TP, andre idretter ofte som **varighet + notater** avhengig av TP-versjon.
3. **Kalender (4 uker):** [plans/csv/trainingdojo-4uker-2026-09-28.csv](../plans/csv/trainingdojo-4uker-2026-09-28.csv) via TrainingDojo — koble bibliotek-økter manuelt eller erstatt tekst-rader med importerte ZWO.

## Pakke alt

```bash
./scripts/zip_zwo_library.sh
# → workouts/zwo-all.zip
```

## Regenerere (svøm/løp/styrke/brick)

Sykkel-ZWO vedlikeholdes som filer i `zwo/bike/`. Kjør:

```bash
python3 scripts/build_zwo_library.py
```

(Brick kopierer sykkel fra `zwo/bike/`; svøm/løp/styrke genereres fra scriptet.)
