#!/bin/sh
mkdir -p /data/athletes 2>/dev/null || true

echo "boot: DATABASE_PATH=${DATABASE_PATH:-/data/coach.db} PORT=${PORT:-8080}"
ls -la /data 2>/dev/null || echo "boot: /data missing"
ls /app/static/index.html 2>/dev/null || echo "boot: missing static index"

# Seed in background so /health comes up immediately (avoids Fly 503 + phone hang)
if [ "${SEED_ON_BOOT:-1}" = "1" ]; then
  (
    sleep 1
    echo "seed: starting…"
    python /app/seed_from_repo.py \
      --repo-root /app \
      --db "${DATABASE_PATH:-/data/coach.db}" \
      --athletes-dir "${ATHLETES_DATA_DIR:-/data/athletes}" \
      && echo "seed: ok" \
      || echo "seed: failed (app still up)"
  ) &
fi

echo "boot: uvicorn on 0.0.0.0:8080 (fly http_service.internal_port)"
# Hardcode 8080 — do not trust injected PORT=3000 from older Fly defaults
exec uvicorn main:app --host 0.0.0.0 --port 8080
