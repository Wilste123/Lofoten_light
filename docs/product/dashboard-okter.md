# Dashboard & Økter

**Branch:** `cursor/web-coach-mvp-42ac` · **PR:** #13

## Faner

| Fane | Innhold |
|------|---------|
| **Coach** | Chat (kan seedes fra en økt; Intervals sessions i kontekst) |
| **Dashboard** | **Periodevelger** + trening (timer/økter), søvn, valgfri kropp, **sesong compliance** |
| **Plan** | Grovplan / sync til Intervals |
| **Økter** | **Bibliotek** (samme økt én gang + datoer) / **Kommende**; trykk → detalj med steg, coach-chat, redigering, logg |
| **Du** | Profil, sesongmål, Intervals, `show_body_metrics` |

Compliance-fanen er fjernet — compliance bor på Dashboard (egen blokk under periode-data).

## Periode (Dashboard)

UI: chips **7 d / 14 d / 30 d / 90 d / Egen** (fra–til). Default **14 d**.

Når perioden endres, lastes treningsdata + wellness for det vinduet på nytt. Sesongmål / compliance endres **ikke** med periodevalget.

### Grafer (periode)

Under periodevalget (fortsatt over sesong-compliance):

| Graf | Data | Merknad |
|------|------|---------|
| **Volum per dag/uke/måned/år** | `training.charts.volume` | Dynamisk bucket: ≤31 d → dag; ≤75 d → uke; ≤550 d → måned; ellers år |
| **Per disiplin** | `training.charts.by_discipline` | Horisontale søyler (Svøm/Sykkel/Løp/Styrke) |
| **Belastning CTL/ATL** | `load.series` | Linjegraf hvis wellness har CTL/ATL; ellers tom tekst |

Ingen ekstra chart-bibliotek — CSS + SVG i `apps/coach-web/src/charts.js`.

## Compliance (app-beregnet)

- Samme formel som [progress-compliance.md](progress-compliance.md): `completed / season_target`.
- **Skrives aldri til Intervals.** UI-banner + API-felt `compliance_written_to_intervals: false`.
- Vises som egen «Fremskritt & compliance»-blokk under periode-data.

## API

| Endpoint | Formål |
|----------|--------|
| `GET /v1/dashboard` | Period training, sleep/body, season compliance |
| `GET /v1/sessions` | Recent / today / upcoming + **`library`** (gruppert etter template) |
| `GET /v1/sessions/{id}` | Strukturert detalj: steg, datoer, `editable_fields`, `seed_prompt` |
| `POST /v1/sessions/{id}/completion` | Logg status/grunn → SQLite + profilnotat |
| `POST /v1/sessions/{id}/edit/preview` | Utøver-redigering → pending ICU workout (bekreft etterpå) |
| `POST /v1/chat` | Ett LLM-kall; valgfri `session_id` fokuserer `focused_session` |
| `POST /v1/athlete/me/intervals/workouts/preview` | Forhåndsvis strukturert WORKOUT (`ll-coach-w-…`) → pending |
| `POST /v1/athlete/me/intervals/calendar/confirm` | Bekreft pending (plan-noter **eller** workout_push) |
| `PATCH /v1/athlete/me` | `show_body_metrics` (bool, default `false`) |

### `GET /v1/dashboard` query

| Param | Beskrivelse |
|-------|-------------|
| `period` | `7d` \| `14d` \| `30d` \| `90d` \| `custom` (default `14d`) |
| `from` | Custom startdato `YYYY-MM-DD` (kreves med `to` når custom) |
| `to` | Custom sluttdato `YYYY-MM-DD` |

Respons (utdrag): `period`, `training` (timer/økter per disiplin, `daily_hours`, `charts.volume` / `charts.by_discipline`), `hours`/`load` (speiler perioden; `load.series` = CTL/ATL-punkter), `sleep`/`body` (samme vindu), `compliance` (sesong — uendret av periode).

## Coach chat ↔ Intervals

**READ:** `/v1/chat` henter samme øktliste som Økter-fanen (`list_sessions`) og legger en kompakt `sessions`-strip i LLM-snapshotet. Med `session_id` legges også `focused_session` (navn, dato, beskrivelse/steg) inn — brukt av detaljvisningens chat.

**WRITE (tynn):** Når utøveren ber om å legge inn / endre en økt, kan LLM returnere en `workout_proposal`-blokk. UI viser **Forhåndsvis → Ja, sync** (samme pending_actions-mønster som Plan-noter). Redigering i detaljvisning bruker `POST /v1/sessions/{id}/edit/preview` mot samme confirm-endpoint. Skriver enkle `WORKOUT`-events — **ikke** full ZWO/CSV-push.

**Ikke:** stille tool-loop, Pondus-orchestrator, eller auto-overwrite av Intervals-økter.

## Økter: bibliotek + detalj

Default-visning er **Bibliotek**: grupperer coach-økter på `ll-coach-w-{dato}-{slug}-N` (slug+disiplin) eller `title+sport` for øvrige. Hvert kort viser datoene økten går på. Toggle **Kommende** gir kronologisk liste (i dag / kommende / siste).

Trykk kort → **detaljvisning**: tittel, sport, «Fra treneren» (steg), planlagte datoer, status, innebygd coach-chat (seedet), valgfri felt-redigering for coach-økter, og fullføringslogg.

## `show_body_metrics`

SQLite-kolonne på `athletes` (default **0** / `false` — personvern først).

**Policy:** nye utøvere (onboarding/`insert_athlete`) får `false`. Eksisterende rader endres **ikke** ved migrate — lagrede verdier beholdes. Du-toggle (`PATCH /v1/athlete/me`) fungerer som før.

Når `false`, Dashboard setter `body_hidden`, utelater vekt/fett%-analyse, og UI **utelater hele Kropp-blokken** (ingen «Skjult»-placeholder). Styres under **Du → Personvern / visning**.

## Øktlogg

Tabell `session_completions`. Status: `completed | skipped | injured | tired | sick | other`. Appendes også under «Øktlogg (app)» i `notes` / `profile.md`.
