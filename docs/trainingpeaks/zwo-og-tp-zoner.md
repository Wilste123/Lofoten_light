# ZWO og TrainingPeaks-zoner (FTP vs terskel-pace)

## Kort svar

| Idrett | ZWO `Power=` betyr | Du setter i TP | TP **Library → Import ZWO** |
|--------|-------------------|---------------|-------------------------------|
| **Sykkel** | **% av bike FTP** | Settings → Zones → **FTP** | **Ja** |
| **Løp** | **% av run threshold pace** (med `pace="2"`) | **Threshold run pace** (eller LTHR i Builder) | **Nei** (bruk Builder / kalender) |
| **Svøm** | **% av swim T-pace (CSS)** | **Threshold swim pace** per 100 m | **Nei** (bruk structured swim Builder) |
| **Styrke** | — | Strength Builder | **Nei** — se [styrke-import.md](styrke-import.md) |

**Bike FTP i TP styrer bare sykkel-ZWO.** Løp og svøm bruker **terskel-pace** i egne soner — ikke FTP.

## Repo

```bash
python3 scripts/compile_bike_manifest.py   # første gang / etter manuell bike-redigering
python3 scripts/build_zwo_library.py       # planned txt + bike + run/swim zwo
# eller:
python3 scripts/export_bike_zwo.py
python3 scripts/planned_to_zwo.py
```

| Mappe | Innhold |
|-------|---------|
| `workouts/zwo/bike/` | Importer til TP — watt fra **din FTP** |
| `workouts/zwo/run/` | ZWO for arkiv/Zwift/Intervals; TP: Builder med **% threshold pace** |
| `workouts/zwo/swim/` | ZWO med T-pace-brøk; TP: **structured swim** i Builder |
| `workouts/planned/` | Menneskelesbar + `tp_target` for Builder |

## Sykkel: sånn får du riktig watt

1. TP → **Settings** → **Zones** → sykkel **FTP** (nåværende test, ikke 410 W historisk).
2. Workout Library → Import → `workouts/zwo/bike/*.zwo`.
3. TP regner watt = `Power` × FTP (f.eks. 0.68 × 280 W = 190 W).

## Løp / svøm: tilsvarende idé, annen sone

- **Løp:** sett **threshold pace** i TP. I repo-ZWO er `Power=1.0` ≈ terskeltempo, `0.78` ≈ easy.
- **Svøm:** sett **T-pace** etter 1000 m-test. `Power=1.0` ≈ CSS-sett, `0.93` ≈ aerob.

For **TrainingPeaks import** av strukturert løp/svøm: bruk **Workout Builder** (eller TrainingDojo-tekst), ikke bulk ZWO — se [zwo-kun-sykkel.md](zwo-kun-sykkel.md) og [intensitet-svom-lop.md](intensitet-svom-lop.md).
