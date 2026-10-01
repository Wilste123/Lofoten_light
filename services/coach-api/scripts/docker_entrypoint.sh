#!/bin/sh
mkdir -p /data/athletes 2>/dev/null || true

# Never echo secrets — only whether Postgres URL is present (Supabase cutover).
if [ -n "${DATABASE_URL:-}${SUPABASE_DB_URL:-}${SUPABASE_DATABASE_URL:-}" ]; then
  DB_HINT="postgres(DATABASE_URL set; sslmode=require auto-added if missing)"
  # Prefer explicit DATABASE_URL for seed; else Supabase aliases; else SQLite path.
  SEED_DB="${DATABASE_URL:-${SUPABASE_DB_URL:-${SUPABASE_DATABASE_URL:-}}}"
else
  DB_HINT="sqlite path=${DATABASE_PATH:-/data/coach.db}"
  SEED_DB="${DATABASE_PATH:-/data/coach.db}"
fi

echo "boot: ${DB_HINT} PORT=${PORT:-8080} PGCONNECT_TIMEOUT=${PGCONNECT_TIMEOUT:-10}"
ls -la /data 2>/dev/null || echo "boot: /data missing"
ls /app/static/index.html 2>/dev/null || echo "boot: missing static index"

# Seed in background so /health comes up immediately (avoids Fly 503 + phone hang).
# When DATABASE_URL is set, seed Postgres (not the leftover SQLite volume).
if [ "${SEED_ON_BOOT:-1}" = "1" ]; then
  (
    sleep 1
    echo "seed: starting against ${DB_HINT}…"
    python /app/seed_from_repo.py \
      --repo-root /app \
      --db "${SEED_DB}" \
      --athletes-dir "${ATHLETES_DATA_DIR:-/data/athletes}" \
      && echo "seed: ok" \
      || echo "seed: failed (app still up — check DATABASE_URL/sslmode)"
  ) &
fi

echo "boot: uvicorn on 0.0.0.0:8080 (fly http_service.internal_port)"
# Hardcode 8080 — do not trust injected PORT=3000 from older Fly defaults
exec uvicorn main:app --host 0.0.0.0 --port 8080
