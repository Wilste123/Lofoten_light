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

## Endepunkter

| Metode | Sti | Auth |
|--------|-----|------|
| POST | `/v1/session/bootstrap` | body `athlete_id` |
| POST | `/v1/onboarding` | — |
| GET/PATCH | `/v1/athlete/me` | header `X-Athlete-Id` |
| POST | `/v1/chat` | header `X-Athlete-Id` |
| GET | `/v1/overview` | header `X-Athlete-Id` |

Onboarding og PATCH skriver `data/athletes/{id}/profile.md`.

## Tester

```bash
cd services/coach-api
source .venv/bin/activate
python -m pytest tests/ -q
```
