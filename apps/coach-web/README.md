# Coach web (Vite)

```bash
# Terminal 1 — API
cd services/coach-api && source .venv/bin/activate
uvicorn main:app --reload --port 8000

# Terminal 2 — Web
cd apps/coach-web
npm install
npm run dev
```

Åpne http://127.0.0.1:5173 — Vite proxyer `/v1` til API.

Faner: **Coach** (chat), **Overblikk**, **Du**. Onboarding skriver `data/athletes/{id}/profile.md`.

Under **Du → Intervals** limer du inn Intervals athlete ID + API-nøkkel (fra Intervals → Settings → Developer). Lagres kun på server (`athlete_secrets`). Chat bruker `OPENAI_API_KEY` fra `services/coach-api/.env`.
