# MVP-scope — Lofoten coach web

## Success (fase 1–2)

Brukeren kan:

1. **Onboarde** (navn, trener, personlighet, aksent, mål, skade, **ernæring/GI**, valgfri test-FTP, vekt/alder) → SQLite + `profile.md`.
2. **Chatte** med treneren som husker *sin* kontekst (ikke William-only hardcoding).
3. **Se kjapt overblikk** — fremskritt/compliance-barer, grovplan-strip, form_estimates.
4. **Eie egen kontekst** under Du (mål, sesongvolum, plan-blokker, avtaler, skade, GI).

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
| 0–1 | Docs + onboarding → profil + chat + Du + Intervals-settings |
| 2 | ~~ICU activity-les + compliance-bars~~ (live når credentials) |
| 2b | ~~Grovplan / `plan_blocks` på Overblikk~~ |
| 2c | UX-polish leftovers |
| 3 | Invite + `training_pair` |
| 4 | Valgfri Intervals-write |
| 5 | Proaktiv post-MVP |
