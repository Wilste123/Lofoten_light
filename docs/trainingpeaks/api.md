# TrainingPeaks API (reference only)

Personal projects generally **cannot** get API keys. Documented here for a future partner integration.

- Request access: https://api.trainingpeaks.com/request-access  
- Docs: https://github.com/TrainingPeaks/PartnersAPI/wiki  

Relevant scopes if you ever build an app:

| Scope | Use |
|-------|-----|
| `workouts:read` | Pull planned/completed workouts for analysis |
| `workouts:plan` | Push planned workouts (JSON structure) |
| `file:write` | Upload completed `.fit` / `.tcx` |

Planned workout create endpoint (partners): `POST /v2/workouts/plan` with `Structure` JSON for erg-style steps.

Until then, use CSV **exports** for analysis and **ZWO / builder** for prescription.

**Repo scripts (token in `.env`):** see **[tp-api-setup.md](tp-api-setup.md)** — `fetch_tp_workouts.py`, `tp_push_calendar.py`.
