# FIT vs ZWO vs YAML (TrainingPeaks)

| Format | What it is | TrainingPeaks Workout Library |
|--------|------------|-------------------------------|
| **YAML** in repo | Source for coach/agent | **Not supported** — edit/export only |
| **.zwo** | Zwift structured workout (% FTP) | **Yes** — ⋮ → Import Workout ([TP help](https://help.trainingpeaks.com/hc/en-us/articles/32432105650573-Import-Planned-Workouts-into-TrainingPeaks)) |
| **.fit** | Garmin structured **workout** file | **Not for library import** — use for **Garmin / Wahoo / head unit** |

## What you should do

### TrainingPeaks calendar with power steps
1. Generate **ZWO** (uses % FTP — TP applies **your** FTP from settings):
   ```bash
   ./scripts/export_all_zwo.sh
   ```
2. Import `.zwo` into TP Workout Library → drag to calendar.

### Garmin / Wahoo / ERG on device
1. Generate **FIT** with **your** FTP in watts (FIT stores absolute watts):
   ```bash
   export FTP=280   # your 2026 test, not 2019
   ./scripts/export_all_fit.sh
   ```
   Or one file:
   ```bash
   python3 scripts/export_fit.py workouts/bike/endurance-90.yaml --ftp 280
   ```
2. **Garmin Connect:** upload workout or copy to `GARMIN/NewFiles/` on device (model-dependent).
3. **Wahoo:** sync structured workouts from TP **after** you built them in TP, or import via Wahoo app if supported.

Completed rides still sync **activity** `.fit` back to TP — that is different from **workout** `.fit`.

## After you change FTP

- **ZWO:** regenerate optional (% stays same; TP recalculates watts).
- **FIT:** regenerate required (`--ftp` baked into watt targets).
