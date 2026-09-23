#!/usr/bin/env bash
# Export all bike YAML to .fit — requires FTP (watts).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FTP="${FTP:-}"
if [[ -z "$FTP" ]]; then
  echo "Set your cycling FTP in watts, e.g.: export FTP=280" >&2
  echo "Then run: $0" >&2
  exit 1
fi
for f in "${ROOT}"/workouts/bike/*.yaml; do
  [[ -f "$f" ]] && python3 "${ROOT}/scripts/export_fit.py" "$f" --ftp "$FTP"
done
echo "FIT files in workouts/generated/"
