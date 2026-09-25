# Coach API — lokal kjøring

```bash
cd services/coach-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # sett OPENAI_API_KEY (valgfritt — stub uten nøkkel)
uvicorn main:app --reload --port 8000
```

Health: `GET http://127.0.0.1:8000/health`

## Hvor ligger nøkler?

| Hemmelighet | Hvor | Bruk |
|-------------|------|------|
| `OPENAI_API_KEY` / `OPENAI_MODEL` | `services/coach-api/.env` (kopier fra `.env.example`) | Chat / LLM — server-wide |
| Intervals athlete ID + API-nøkkel | App **Du**-fane → `PUT /v1/athlete/me/intervals` → SQLite `athlete_secrets` | Per utøver; aldri i git / `localStorage` |
| `INTERVALS_API` (CLI) | Repo-root `.env` for `scripts/intervals_*.py` | Kun lokale scripts — ikke coach-web |

Aldri commit `.env` eller fulle Intervals-nøkler. GET på secrets returnerer bare `connected`, `intervals_athlete_id` og maskert `api_key_hint`.

## Endepunkter

| Metode | Sti | Auth |
|--------|-----|------|
| POST | `/v1/session/bootstrap` | body `athlete_id` |
| POST | `/v1/onboarding` | — |
| GET/PATCH | `/v1/athlete/me` | header `X-Athlete-Id` |
| GET/PUT | `/v1/athlete/me/intervals` | header `X-Athlete-Id` |
| POST | `/v1/chat` | header `X-Athlete-Id` |
| GET | `/v1/overview` | header `X-Athlete-Id` |

Onboarding og PATCH skriver `data/athletes/{id}/profile.md`.

`PUT /v1/athlete/me/intervals` body: `{ "intervals_athlete_id", "intervals_api_key", "verify": true }`.  
Ved `verify: true` gjøres en soft smoke-test mot Intervals; nøkkel lagres uansett. Svar inkluderer `verified` / `verify_error`.

## Tester

```bash
cd services/coach-api
source .venv/bin/activate
python -m pytest tests/ -q
```
