# Intervals → TrainingPeaks export

Kalender **2026-10-22** … **2026-10-31** (planlagte økter fra Intervals.icu).

| | Antall |
|---|--:|
| `.zwo` (sykkel + løp + svøm) | 11 |
| Styrke (TrainingDojo CSV) | 3 |
| Tekst-fallback (mangler struktur) | 0 |

## Hvorfor bare ZWO i TP?

TrainingPeaks **Library → Import** godtar kun **kraftbasert sykkel** `.zwo` ([TP Help](https://help.trainingpeaks.com/hc/en-us/articles/32432105650573-Import-Planned-Workouts-into-TrainingPeaks)). Ingen filimport for planlagt løp/svøm/styrke.

**Løsning i denne pakken**

1. **Sykkel** — `bike/*.zwo` → importer → dra på kalender (FTP i TP).
2. **Løp/svøm** — `run/` og `swim/` er **sykkel-format ZWO** med prefiks LØP/SVØM (samme triks som i repo: `docs/trainingpeaks/importer-lop-svom-zwo.md`):
   - Importer `.zwo` som sykkel
   - Åpne økt → **Build** → sport **Run** / **Swim** → intensitet **% threshold pace**
   - Lagre → dra på kalender
3. **Styrke** — ingen ZWO. Bruk **`trainingdojo-import.csv`** på [trainingdojo.app/import](https://trainingdojo.app/import), plan start **`2026-10-22`**.

## Kjør på nytt

```bash
python3 scripts/export_intervals_plan_to_tp.py --start 2026-10-22 --end 2026-10-31 -o exports/tp-from-intervals
```
