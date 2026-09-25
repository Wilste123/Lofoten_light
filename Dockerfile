# Multi-stage: Vite UI + FastAPI (same origin for phone / Fly)

FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY apps/coach-web/package.json apps/coach-web/package-lock.json ./
RUN npm ci
COPY apps/coach-web/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS api
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/data/coach.db \
    ATHLETES_DATA_DIR=/data/athletes \
    KNOWLEDGE_DIR=/app/knowledge \
    STATIC_DIR=/app/static \
    CORS_ORIGINS=* \
    PORT=8080

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY services/coach-api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services/coach-api/ /app/
COPY knowledge/ /app/knowledge/
COPY docs/athlete/ /app/docs/athlete/
COPY plans/ /app/plans/
COPY --from=web /web/dist /app/static

RUN chmod +x /app/scripts/docker_entrypoint.sh

EXPOSE 8080
VOLUME ["/data"]

ENTRYPOINT ["/app/scripts/docker_entrypoint.sh"]
