# MVP-scope — Lofoten coach web

## Success (fase 1–2)

Brukeren kan:

1. **Onboarde** (navn, trener, personlighet, aksent, mål, skade, **ernæring/GI**, valgfri test-FTP, vekt/alder) → SQLite + `profile.md`.
2. **Chatte** med treneren som husker *sin* kontekst (ikke William-only hardcoding).
3. **Se kjapt overblikk** — stub i fase 1; ICU + form_estimates i fase 2.
4. **Eie egen kontekst** under Du (mål, avtaler, skade, GI, tema).

Intervals.icu forblir stedet for **full kalender, øktdetaljer og grafer**.

## Onboarding (fase 1) — felter

| Steg | Felt |
|------|------|
| Velkommen | Visningsnavn |
| Treneren | Trenernavn, personlighet, stil-setning |
| Utseende | Aksentfarge → `--accent` |
| Mål & kropp | Mål/race, tilgjengelighet, skade, testet FTP (+ dato), vekt/alder |
| Ernæring / GI | IBS, gluten, laktose, andre restriksjoner, notater |
| Senere | Intervals-kobling (hoppes over i fase 1) |

## Non-goals (MVP)

- Kalender-/uke-UI som erstatter Intervals
- Slack, proaktiv cron (fase 5)
- Supabase / Postgres
- Pondus `coach_bot`-import, intent-router, tool-spam
- Full Intervals write/push
- Agent-til-agent coach chat
- Partner sync UI (kun docs + tom schema)
- Merge til `main` før pilot er grønn

## Fasestatus

| Fase | Leveranse |
|------|-----------|
| 0 | Branch + product docs |
| 1 | Onboarding → profilfil (+ GI) + chat + Du (uten ICU) |
| 2 | ICU les + overview + `form_estimates` |
| 3 | Invite + `training_pair` |
| 4 | Valgfri Intervals-write |
| 5 | Proaktiv post-MVP |
