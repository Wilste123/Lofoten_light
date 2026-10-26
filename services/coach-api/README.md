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
| `OPENAI_API_KEY` / `OPENAI_MODEL` | `services/coach-api/.env` (kopier fra `.env.example`) | Chat / LLM — default **`gpt-4o`** (bedre coach-chat; dyrere enn mini). Sett `OPENAI_MODEL=gpt-4o-mini` for billigere, eller `gpt-4.1`. Cursor Composer finnes ikke som API her — bruk Fly-secret. |
| Intervals athlete ID + API-nøkkel | App **Du**-fane → `PUT /v1/athlete/me/intervals` → SQLite `athlete_secrets` | Per utøver; aldri i git / `localStorage` |
| `INTERVALS_API` (CLI) | Repo-root `.env` for `scripts/intervals_*.py` | Kun lokale scripts — ikke coach-web |

Aldri commit `.env` eller fulle Intervals-nøkler. GET på secrets returnerer bare `connected`, `intervals_athlete_id` og maskert `api_key_hint`.

## Endepunkter

| Metode | Sti | Auth |
|--------|-----|------|
| POST | `/v1/session/bootstrap` | body `athlete_id` |
| POST | `/v1/session/login` | body `username` **eller** `athlete_id` + valgfri `invite_token` (oppretter ikke) |
| POST | `/v1/onboarding` | — |
| GET/PATCH | `/v1/athlete/me` | header `X-Athlete-Id` |
| GET/PUT | `/v1/athlete/me/intervals` | header `X-Athlete-Id` |
| POST | `/v1/chat` | header `X-Athlete-Id` — inkluderer Intervals sessions-snapshot; valgfri `workout_proposal` |
| POST | `/v1/athlete/me/intervals/workouts/preview` | header `X-Athlete-Id` — forhåndsvis WORKOUT → pending |
| POST | `/v1/athlete/me/intervals/calendar/confirm` | header `X-Athlete-Id` — bekreft plan-noter eller workout_push |
| GET | `/v1/overview` | header `X-Athlete-Id` |

Onboarding og PATCH skriver `data/athletes/{id}/profile.md`. Login: se `docs/product/returning-login.md`.

Chat leser on-disk `profile.md` (inkl. seedet rik profil) via `load_profile_md`.

## Seed William fra repo

```bash
python3 services/coach-api/scripts/seed_william_from_repo.py
python3 services/coach-api/scripts/seed_william_from_repo.py --dry-run
```

Se `docs/product/import-from-repo.md`. Valgfri `POST /v1/admin/seed-from-repo` krever `ADMIN_SEED_TOKEN`.

`PUT /v1/athlete/me/intervals` body: `{ "intervals_athlete_id", "intervals_api_key", "verify": true }`.  
Ved `verify: true` gjøres en soft smoke-test mot Intervals; nøkkel lagres uansett. Svar inkluderer `verified` / `verify_error`.

## Tester

```bash
cd services/coach-api
source .venv/bin/activate
python -m pytest tests/ -q
```
