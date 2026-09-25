# MVP-scope — Lofoten coach web

## Success (fase 1–2)

Brukeren kan:

1. **Chatte med treneren** — ett LLM-kall per melding; kort kontekst (profil + trimmet knowledge); forutsigbar tone.
2. **Se kjapt overblikk** — plan-hode / siste økt / belastning (fase 2 med Intervals) + testet vs estimert form + én fremgangs-/oppløftende linje.
3. **Eie egen kontekst i appen** — mål, avtaler, skade, testet FTP, ukens fokus, notater (Du-fanen).
4. **Få profilfil** — ved fullført onboarding skrives `data/athletes/{id}/profile.md` (mal à la `docs/athlete/profile.md`) slik at coach tilpasser for andre enn William. Oppdateres når Du lagres.

Intervals.icu forblir stedet for **full kalender, øktdetaljer og grafer**. Appen konkurrerer ikke med det.

## Produktfokus (prioritet)

1. Chat med personlig trener  
2. Kjapt overblikk (ikke erstatte Intervals)  
3. App eier: mål, avtaler, skade, test-FTP, profilfil  
4. Intervals eier: økter, kalenderdetaljer  
5. Treningspar (fase 3): to trenere, samkjørte tid/sted-vinduer  

## Onboarding (fase 1) — felter

| Steg | Felt |
|------|------|
| Velkommen | Visningsnavn |
| Treneren | Trenernavn, personlighet (preset), valgfri stil-setning |
| Utseende | Aksentfarge (forhåndsvalg / hex) → `--accent` |
| Mål & kropp | Mål/race, skade/begrensning, testet FTP (+ dato) valgfritt, vekt/alder valgfritt |
| Senere | Intervals-kobling (kan hoppes over i fase 1) |

**Ikke i onboarding:** IBS, gluten, detaljert ernæring (se `knowledge/ernaring/`).

## Non-goals (MVP)

- Kalender-/uke-UI som erstatter Intervals  
- Slack, proaktiv cron / morgenlinje (fase 5)  
- Supabase / Postgres (se `data-storage.md`)  
- Pondus / xtri `coach_bot`-import, intent-router, tool-spam  
- Ernæring/IBS-wizard i UI  
- Norseman / full Extreme-volum som default  
- Merge til `main` før pilot er grønn  

## Fasestatus

| Fase | Leveranse |
|------|-----------|
| 0 | Branch + product docs (denne mappen) |
| 1 | Onboarding → profilfil + chat + Du (uten ICU) |
| 2 | ICU les + overview + `form_estimates` |
| 3 | Invite + `training_pair` (samboer) |
| 4 | Valgfri Intervals-write |
| 5 | Proaktiv post-MVP |
