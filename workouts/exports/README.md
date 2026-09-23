# Exported bike workouts (generated)

Pre-built files from `workouts/bike/*.yaml`.

| Folder | Format | TrainingPeaks |
|--------|--------|----------------|
| `zwo/` | % FTP | **Import** via Workout Library |
| `fit/` | Absolute watts | Garmin/Wahoo — **not** TP library import |

**FIT files used `FTP=300 W` as placeholder** (your 2026 FTP is not set in profile yet). Re-generate when you know FTP:

```bash
export FTP=YOUR_WATTS
./scripts/export_all_fit.sh
```

Regenerate everything:

```bash
./scripts/export_all_zwo.sh
export FTP=YOUR_WATTS && ./scripts/export_all_fit.sh
```

Generated: repo commit date on these files.
