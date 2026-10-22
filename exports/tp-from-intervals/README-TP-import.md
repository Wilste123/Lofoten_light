# Intervals → TrainingPeaks export

Generated from Intervals.icu calendar **2026-11-01** … **2027-04-30** (planned workouts only).

| Count | |
|-------|---|
| Bike `.zwo` | 24 |
| Run/swim/strength `.txt` | 66 |
| Index | `index.csv` |

## Sykkel (TP Virtual / rulla)

1. TrainingPeaks → **Library** → Import **`.zwo`** from `bike/`.
2. Dra økt til **kalender** på riktig dato (se `index.csv`).
3. FTP **210 W** i TP soner.

## Løp / svøm / styrke

- TP importerer ikke struktur fra `.txt` automatisk.
- Åpne filen → bygg i **Workout Builder** (HR / % threshold pace / CSS), eller lim beskrivelse i kalender-notat.
- `index.csv` har dato, navn og planlagt load fra Intervals.

Kjør på nytt etter endringer i Intervals:

```bash
python3 scripts/export_intervals_plan_to_tp.py --start 2026-11-01 -o exports/tp-from-intervals
```
