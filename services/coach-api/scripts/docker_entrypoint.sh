#!/bin/sh
set -e
mkdir -p /data/athletes

if [ "${SEED_ON_BOOT:-1}" = "1" ]; then
  echo "seed: William from repo docs…"
  python /app/seed_from_repo.py \
    --repo-root /app \
    --db "${DATABASE_PATH:-/data/coach.db}" \
    --athletes-dir "${ATHLETES_DATA_DIR:-/data/athletes}" \
    || echo "seed: advarsel — fortsetter uten seed"
fi

exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8080}"
