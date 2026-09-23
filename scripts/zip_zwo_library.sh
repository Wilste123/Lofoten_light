#!/usr/bin/env bash
# All .zwo (bike = TP FTP; run/swim = threshold pace — see docs/trainingpeaks/zwo-og-tp-zoner.md)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/workouts"
rm -f zwo-all.zip zwo-bike.zip
zip -r zwo-all.zip zwo -x "*.DS_Store"
cp -f zwo-all.zip zwo-bike.zip
echo "Wrote workouts/zwo-all.zip ($(du -h zwo-all.zip | cut -f1))"
