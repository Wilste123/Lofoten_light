# Treningsbibliotek

## ZWO (`workouts/zwo/`)

| Mappe | `Power=` i filen | Sett i TrainingPeaks | TP Library **Import ZWO** |
|-------|------------------|--------------------|---------------------------|
| `zwo/bike/` | **% bike FTP** | Sykkel **FTP** | **Ja** |
| `zwo/run/` | **% run threshold pace** (`pace="2"`) | **Run threshold pace** | Nei → Builder / TrainingDojo |
| `zwo/swim/` | **% swim T-pace (CSS)** | **Swim threshold pace** | Nei → structured swim Builder |
| `zwo/brick/` | Sykkel-ZWO + løp-ZWO | FTP + run pace | Kun sykkel-filer importeres som watt |

**Bike FTP styrer ikke løp/svøm.** Les [docs/trainingpeaks/zwo-og-tp-zoner.md](../docs/trainingpeaks/zwo-og-tp-zoner.md).

## Styrke (ikke ZWO)

- Kalender: TrainingDojo CSV (`sport=strength`)
- Strukturert: [Strength Builder](https://help.trainingpeaks.com/hc/en-us/articles/23361947242381-Strength-Workout-Builder-FAQs) + `workouts/strength/trainingpeaks/`
- Guide: [docs/trainingpeaks/styrke-import.md](../docs/trainingpeaks/styrke-import.md)

## Planned tekst (`workouts/planned/`)

Samme økter som ZWO for løp/svøm, med `tp_target` for manuell Workout Builder.

## Bygg alt

```bash
python3 scripts/build_zwo_library.py
./scripts/zip_zwo_library.sh
```
