# Workout YAML format

```yaml
name: Tuesday Threshold
description: 2x20 min at FTP
sport: bike
steps:
  - duration_min: 15
    power_pct_ftp: 55
    note: Warm-up
  - duration_min: 20
    power_pct_ftp: 95
    note: Threshold 1
  - duration_min: 10
    power_pct_ftp: 50
    note: Recovery
  - duration_min: 20
    power_pct_ftp: 95
    note: Threshold 2
  - duration_min: 10
    power_pct_ftp: 45
    note: Cool-down
```

Generate ZWO:

```bash
python3 scripts/export_zwo.py workouts/example-threshold.yaml
```

Output: `workouts/generated/<name>.zwo`
