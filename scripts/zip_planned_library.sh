#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/workouts"
zip -r planned-all.zip planned -x "*.DS_Store"
echo "Wrote workouts/planned-all.zip ($(du -h planned-all.zip | cut -f1))"
