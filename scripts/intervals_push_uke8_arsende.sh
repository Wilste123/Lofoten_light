#!/usr/bin/env bash
# Push uke 8 (B1) + uke 9–13 (B2/B3) + bolk-markører to Intervals.icu.
# Requires INTERVALS_API or INTERVALS_API_KEY in env (see docs/integrations/intervals-import.md).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DRY=()
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY=(--dry-run)
  shift || true
fi

echo "=== B1 uke 5–8 (inkl. uke 8 recovery) start 2026-10-26 ==="
python3 scripts/intervals_push_calendar.py --start 2026-10-26 \
  --plan plans/csv/trainingdojo-4uker-2026-10-26.csv \
  --notes plans/csv/trainingdojo-uke-notater-4uker-opv-2026-10-26.csv \
  --bike-calendar plans/csv/sykkel-zwo-kalender-4uker-2026-10-26.csv \
  "${DRY[@]}"

echo "=== B2/B3 uke 9–13 start 2026-11-23 ==="
python3 scripts/intervals_push_calendar.py --start 2026-11-23 \
  --plan plans/csv/trainingdojo-5uker-2026-11-23.csv \
  --notes plans/csv/trainingdojo-uke-notater-5uker-opv-2026-11-23.csv \
  --bike-calendar plans/csv/sykkel-zwo-kalender-5uker-2026-11-23.csv \
  "${DRY[@]}"

echo "=== Bolk-markører (ICS → NOTE) ==="
python3 scripts/intervals_push_bolk.py \
  --ics plans/calendar/2026-bolk-markers.ics \
  --only-block-boundaries \
  "${DRY[@]}"

echo "Done."
