#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
for f in "${ROOT}"/workouts/bike/*.yaml; do
  [[ -f "$f" ]] && python3 "${ROOT}/scripts/export_zwo.py" "$f"
done
echo "ZWO files in workouts/generated/"
