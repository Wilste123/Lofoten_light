#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CACHE="${ROOT}/.cache/xtri-repo"
DEST="${ROOT}/docs/xtri/synced"
URL="${XTRI_REPO_URL:-}"

if [[ -z "$URL" ]]; then
  echo "Set XTRI_REPO_URL to your Xtri repository clone URL." >&2
  echo "Example: export XTRI_REPO_URL='https://github.com/you/xtri-pondus.git'" >&2
  exit 1
fi

mkdir -p "${ROOT}/.cache" "${DEST}"

if [[ -d "${CACHE}/.git" ]]; then
  git -C "${CACHE}" fetch --depth 1 origin
  git -C "${CACHE}" reset --hard FETCH_HEAD 2>/dev/null || git -C "${CACHE}" pull --ff-only
else
  rm -rf "${CACHE}"
  git clone --depth 1 "${URL}" "${CACHE}"
fi

rm -rf "${DEST}"
mkdir -p "${DEST}"

# Copy markdown and plain text docs; customize paths with XTRI_DOC_PATHS (space-separated)
PATHS=(${XTRI_DOC_PATHS:-docs README.md README planning})
for rel in "${PATHS[@]}"; do
  if [[ -e "${CACHE}/${rel}" ]]; then
    mkdir -p "${DEST}/$(dirname "${rel}")"
    cp -a "${CACHE}/${rel}" "${DEST}/${rel}"
  fi
done

echo "Synced Xtri docs into ${DEST}"
find "${DEST}" -type f | head -20
