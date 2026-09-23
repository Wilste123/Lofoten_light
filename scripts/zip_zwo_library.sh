#!/usr/bin/env bash
# Pack workouts/zwo/ for download (TrainingPeaks import, backup).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/workouts"
zip -r zwo-all.zip zwo -x "*.DS_Store"
echo "Wrote workouts/zwo-all.zip ($(du -h zwo-all.zip | cut -f1))"
