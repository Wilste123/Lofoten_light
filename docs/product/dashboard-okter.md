# Dashboard & Økter

**Branch:** `cursor/web-coach-mvp-42ac` · **PR:** #13

## Faner

| Fane | Innhold |
|------|---------|
| **Coach** | Chat (kan seedes fra en økt; Intervals sessions i kontekst) |
| **Dashboard** | **Periodevelger** + trening (timer/økter), søvn, valgfri kropp, **sesong compliance** |
| **Plan** | Grovplan / sync til Intervals |
| **Økter** | Siste + kommende fra Intervals; logg + spør coach |
| **Du** | Profil, sesongmål, Intervals, `show_body_metrics` |

Compliance-fanen er fjernet — compliance bor på Dashboard (egen blokk under periode-data).

## Periode (Dashboard)

UI: chips **7 d / 14 d / 30 d / 90 d / Egen** (fra–til). Default **14 d**.

Når perioden endres, lastes treningsdata + wellness for det vinduet på nytt. Sesongmål / compliance endres **ikke** med periodevalget.

## Compliance (app-beregnet)

- Samme formel som [progress-compliance.md](progress-compliance.md): `completed / season_target`.
- **Skrives aldri til Intervals.** UI-banner + API-felt `compliance_written_to_intervals: false`.
- Vises som egen «Fremskritt & compliance»-blokk under periode-data.

## API

| Endpoint | Formål |
|----------|--------|
| `GET /v1/dashboard` | Period training, sleep/body, season compliance |
| `GET /v1/sessions` | Recent / today / upcoming (soft-fail uten credentials) |
| `GET /v1/sessions/{id}` | Detalj + `seed_prompt` for chat |
| `POST /v1/sessions/{id}/completion` | Logg status/grunn → SQLite + profilnotat |
| `POST /v1/chat` | Ett LLM-kall; **inkl. Intervals sessions-snapshot** (upcoming/recent) i kontekst |
| `POST /v1/athlete/me/intervals/workouts/preview` | Forhåndsvis strukturert WORKOUT (`ll-coach-w-…`) → pending |
| `POST /v1/athlete/me/intervals/calendar/confirm` | Bekreft pending (plan-noter **eller** workout_push) |
| `PATCH /v1/athlete/me` | `show_body_metrics` (bool, default `true`) |

### `GET /v1/dashboard` query

| Param | Beskrivelse |
|-------|-------------|
| `period` | `7d` \| `14d` \| `30d` \| `90d` \| `custom` (default `14d`) |
| `from` | Custom startdato `YYYY-MM-DD` (kreves med `to` når custom) |
| `to` | Custom sluttdato `YYYY-MM-DD` |

Respons (utdrag): `period`, `training` (timer/økter per disiplin, ingen sesongmål), `hours`/`load` (speiler perioden), `sleep`/`body` (samme vindu), `compliance` (sesong — uendret av periode).

## Coach chat ↔ Intervals

**READ:** `/v1/chat` henter samme øktliste som Økter-fanen (`list_sessions`) og legger en kompakt `sessions`-strip i LLM-snapshotet. Coach kan svare på «hva har jeg denne uka?» fra ekte ICU-data når Intervals er koblet.

**WRITE (tynn):** Når utøveren ber om å legge inn en økt, kan LLM returnere en `workout_proposal`-blokk. UI viser **Forhåndsvis → Ja, sync** (samme pending_actions-mønster som Plan-noter). Skriver enkle `WORKOUT`-events (navn, dato, sport, varighet, beskrivelse) — **ikke** full ZWO/CSV-push (det er fortsatt CLI `scripts/intervals_push_calendar.py`).

**Ikke:** stille tool-loop, Pondus-orchestrator, eller auto-overwrite av Intervals-økter.

## `show_body_metrics`

SQLite-kolonne på `athletes` (default 1). Når `false`, Dashboard setter `body_hidden` og utelater vekt/fett%-analyse. Styres under **Du → Personvern / visning**.

## Øktlogg

Tabell `session_completions`. Status: `completed | skipped | injured | tired | sick | other`. Appendes også under «Øktlogg (app)» i `notes` / `profile.md`.
