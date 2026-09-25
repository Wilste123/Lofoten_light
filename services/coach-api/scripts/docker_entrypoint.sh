#!/bin/sh
# Keep going even if seed fails — never block uvicorn.
mkdir -p /data/athletes 2>/dev/null || true

echo "boot: DATABASE_PATH=${DATABASE_PATH:-/data/coach.db}"
echo "boot: STATIC_DIR=${STATIC_DIR:-/app/static}"
ls -la /data 2>/dev/null || echo "boot: /data not listed yet"
ls -la /app/static 2>/dev/null | head -5 || echo "boot: no static"

if [ "${SEED_ON_BOOT:-1}" = "1" ]; then
  echo "seed: William from repo docs…"
  if ! python /app/seed_from_repo.py \
    --repo-root /app \
    --db "${DATABASE_PATH:-/data/coach.db}" \
    --athletes-dir "${ATHLETES_DATA_DIR:-/data/athletes}"; then
    echo "seed: advarsel — fortsetter uten seed"
  fi
fi

echo "boot: starting uvicorn on ${PORT:-8080}"
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8080}"
