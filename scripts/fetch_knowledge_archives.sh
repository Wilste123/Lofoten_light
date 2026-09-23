#!/usr/bin/env bash
# Download publicly available reference PDFs into knowledge/external/
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${ROOT}/knowledge/external"
mkdir -p "${DEST}"

declare -A URLS=(
  ["ioc-load-injury-consensus-2016.pdf"]="https://www.ostrc.no/globalassets/publications/soligard_2016_bjsm_how-much-is-too-much.-ioc-consensus-statement-on-load-in-sport-and-risk-of-injury.pdf"
  ["mso-open-water-swimming-safety.pdf"]="https://www.mastersswimmingontario.ca/wp-content/uploads/2020/06/CIMS-MSO-MSM-OPEN-WATER-SWIMMING-v2.pdf"
)

for name in "${!URLS[@]}"; do
  url="${URLS[$name]}"
  echo "Fetching ${name} ..."
  curl -fsSL -o "${DEST}/${name}" "${url}"
done

echo "Done. Files in ${DEST}:"
ls -lh "${DEST}"
