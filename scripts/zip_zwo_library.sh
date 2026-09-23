#!/usr/bin/env bash
# Power-cycling ZWO only (TrainingPeaks Workout Library import).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/workouts"
rm -f zwo-bike.zip
zip -r zwo-bike.zip zwo/bike zwo/brick -x "*.DS_Store" "zwo/brick/*-run-*"
# legacy name for scripts that still expect zwo-all.zip
cp -f zwo-bike.zip zwo-all.zip
echo "Wrote workouts/zwo-bike.zip and zwo-all.zip ($(du -h zwo-bike.zip | cut -f1))"
