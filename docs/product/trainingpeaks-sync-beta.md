# TrainingPeaks kalender-speil (beta)

**Status:** beta / uoffisiell. Speiler **planlagte WORKOUT** fra samme bundle som Intervals-sync (`build_plan_sync_bundle`), med egen preview → confirm.

## Aktivering

- Server: `TRAININGPEAKS_BETA_ENABLED=1` (standard på).
- DB: `migrations/003_trainingpeaks_beta.sql` (eller SQLite auto-migrate via `init_db`).
- Utøver: `PUT /v1/athlete/me/trainingpeaks/beta` med `Production_tpAuth`-cookie + `verify: true` → lagrer `tp_user_id`.

## API

| Metode | Sti | Hensikt |
|--------|-----|---------|
| GET | `/v1/athlete/me/trainingpeaks/beta` | Status (ingen cookie i klartekst) |
| PUT | `/v1/athlete/me/trainingpeaks/beta` | Lagre cookie, valgfri verify |
| POST | `/v1/athlete/me/trainingpeaks/beta/calendar/preview` | Pending push |
| POST | `/v1/athlete/me/trainingpeaks/beta/calendar/confirm` | Skriv til TP |

## Struktur

Intervals-tekst (`---intervals---`, `- 3m 70-75% LTHR`, `Main Set 4x`) mappes til TP `structure` JSON (`percentOfFtp` / `percentOfThresholdHr` / `percentOfThresholdPace`). Sykkel-ZWO til Intervals speiles som beskrivelse + varighet inntil ZWO→TP struktur er implementert.

## Risiko

Uoffisiell `tpapi.trainingpeaks.com` (som tp2intervals / TrainingDojo). For kommersiell drift: vurder Partner API. tp2intervals er GPLv3 — denne koden er ny Python-implementasjon, ikke kopi.
