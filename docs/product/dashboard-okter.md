# Dashboard & Økter

**Branch:** `cursor/web-coach-mvp-42ac` · **PR:** #13

## Faner

| Fane | Innhold |
|------|---------|
| **Coach** | Chat (kan seedes fra en økt) |
| **Dashboard** | Timer/belastning, søvn, valgfri kropp, **compliance** |
| **Plan** | Grovplan / sync til Intervals |
| **Økter** | Siste + kommende fra Intervals; logg + spør coach |
| **Du** | Profil, sesongmål, Intervals, `show_body_metrics` |

Compliance-fanen er fjernet — compliance bor på Dashboard.

## Compliance (app-beregnet)

- Samme formel som [progress-compliance.md](progress-compliance.md): `completed / season_target`.
- **Skrives aldri til Intervals.** UI-banner + API-felt `compliance_written_to_intervals: false`.

## API

| Endpoint | Formål |
|----------|--------|
| `GET /v1/dashboard` | Hours/load, sleep, body (om toggle), compliance |
| `GET /v1/sessions` | Recent / today / upcoming (soft-fail uten credentials) |
| `GET /v1/sessions/{id}` | Detalj + `seed_prompt` for chat |
| `POST /v1/sessions/{id}/completion` | Logg status/grunn → SQLite + profilnotat |
| `PATCH /v1/athlete/me` | `show_body_metrics` (bool, default `true`) |

## `show_body_metrics`

SQLite-kolonne på `athletes` (default 1). Når `false`, Dashboard setter `body_hidden` og utelater vekt/fett%-analyse. Styres under **Du → Personvern / visning**.

## Øktlogg

Tabell `session_completions`. Status: `completed | skipped | injured | tired | sick | other`. Appendes også under «Øktlogg (app)» i `notes` / `profile.md`.
