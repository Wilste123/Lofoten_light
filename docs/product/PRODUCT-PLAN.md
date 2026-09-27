# Lofoten coach produkt — kanonisk plan

**Branch:** `cursor/web-coach-mvp-42ac` · **Repo:** [Lofoten_light](https://github.com/Wilste123/Lofoten_light) · **PR:** https://github.com/Wilste123/Lofoten_light/pull/13  
**Siste gap:** [gap-analysis-2026-09-27.md](gap-analysis-2026-09-27.md) · **Konkurrenter:** [competitor-humango.md](competitor-humango.md) · **HEAD ved siste gap:** `5cfb32f`

## Produktfokus

1. Chat med personlig trener (forutsigbar, ett LLM-kall)
2. Kjapt overblikk / **dashboard** (ikke erstatte Intervals) — inkl. **fremskritt / compliance**
3. App eier: mål, avtaler, skade, test-FTP, profilfil, **grovplan / periodisering / bulk**
4. Intervals eier: økter, kalenderdetaljer (ikke makro/bulk-oversikt)
5. Treningspar (fase 3): to trenere, samkjørte tid/sted-vinduer
6. **UX:** litt mer moderne flate (tydelig aksent, knapper, spacing) — fortsatt enkel, ikke dashboard-monster
7. **Øktbibliotek / workout builder** — se økter, spør coach, logg completion + reason (uten å bli TP-erstatning)

## Det Intervals ikke gir — appens oversikt

### Grovplan / periodisering / bulk

Appen viser **makro- og meso-nivå** som Intervals ikke gjør godt. Se [periodization-overview.md](periodization-overview.md).

| Objekt | Eksempel | Lagring |
|--------|----------|---------|
| **Sesong / makro** | «Mot Lofoten 2027», faser (base → bygg → peak) | SQLite `plan_blocks` + valgfri markdown under `data/athletes/{id}/plan/` |
| **Bulk / blokk** | 4-ukers bulk med tema og uketimer | Samme |
| **Grovplan-oversikt** | Én skjerm: nåværende blokk, neste blokk, dager til race | Plan-fane / Overblikk (read-first) |

Ikke full kalenderklone. Lenke «detaljer i Intervals» for dagsøkter.

### Fremskritt og compliance (app-side, ikke ICU-write)

Deterministiske tall (Python, ikke LLM). Se [progress-compliance.md](progress-compliance.md).

| Metrikk | Eksempel | Kilde |
|---------|----------|--------|
| **Volummål** | Sykkel **175 / 500 t** (sesong) | ICU **activities** (READ) + mål i SQLite |
| **Compliance** | Sykkel **35 %** (`completed / target`) | Samme — **beregnet i appen** |
| **On-pace** | «På plan / Foran / Bak» | `completed / (target × elapsed/season)` |
| Per disiplin | Svøm / sykkel / løp / styrke | Samme |
| Progress bar | Visuell 175/500 | UI |

**Viktig skille:**

- Compliance / volum / form_estimates = **app-side** fra ICU-data (les). Skrives **ikke** tilbake til Intervals.
- Det eneste ICU-**write** i MVP er når brukeren under Plan aktivt kjører **Sync til Intervals** (grovplan-noter `ll-coach-…`, preview → confirm). Uten Sync forblir Intervals urørt.

Uten Intervals-credentials: **demo/stub**-tall merket «Demo».

## Dashboard-side (ønsket / neste)

Dedikert (eller utvidet Overblikk) **training status**-flate — fortsatt companion, ikke ICU-klon:

| Blokk | Innhold | Kilde |
|-------|---------|--------|
| **Training status** | Kort uplift, nåværende blokk, dager til race, Intervals-koblet? | Overview + plan_blocks |
| **Timer / volum** | Per disiplin completed/target + compliance % | App-beregnet fra ICU activities |
| **Søvnanalyse** | Trend siste 7–14 d | App-beregnet fra Intervals **wellness** hvis tilgjengelig |
| **Vekt + body-fat** | Trend / enkel analyse | Wellness/BIA eller manuell; **kan slås AV** under Du |

### Toggle (Du-innstillinger)

- `[ ] Vis vekt- og fettanalyse på Dashboard` — OFF skjuler blokken helt.
- Senere: egen toggle for søvn hvis ønskelig.

## Workout builder / øktbibliotek (ønsket / neste)

1. **Liste økter** — speil planlagte/fullførte fra Intervals (READ) og/eller lokale maler (`workouts/`).
2. **Spør coach om økten** — deep-link til Coach med økt-kontekst.
3. **Completion + reason** — gjort / delvis / hoppet over + kort årsak; lagres i app-SQLite. Valgfri senere speil til ICU kun med eksplisitt Sync.

## Onboarding → profilfil

Ved fullført onboarding **skriver API** `data/athletes/{id}/profile.md`. Oppdateres fra Du.

**Ikke i onboarding-wizard:** dypt IBS/ernæring-kurs — knowledge i `knowledge/ernaring/`; matbegrensninger kan ligge i profil/Du.

GI-felter (IBS/gluten/laktose) samles i onboarding/Du → SQLite + `profile.md`. Chat diagnostiserer aldri.

## Datalagring

SQLite + Fly volume. Secrets: OpenAI i `.env`; Intervals ID+nøkkel i Du → `athlete_secrets`. Se [data-storage.md](data-storage.md).

Sesongmål (`season_*_hours_target`) og `plan_blocks` lever i SQLite — appens SoT for makro.

## Innlogging (returning user)

Uten passord / OAuth. Se [returning-login.md](returning-login.md).

- Start: **Ny bruker** | **Jeg har allerede profil**
- Login: lim inn **profil-ID** (+ valgfri invite-token)
- `POST /v1/session/login` — oppretter ikke ny atlet
- Under **Du**: vis/kopier **Din profil-ID**
- Snarveier: `?athlete=` og «Bruk seedet William-profil»

## Smarte estimater

Gate ≥ 5 sykkeløkter med watt. Se [form-estimates.md](form-estimates.md).

## Faser (oppdatert)

| Fase | Innhold |
|------|---------|
| 0–1 | ~~Docs + onboarding + chat + Du + Intervals-settings~~ (landet på PR #13) |
| 2 | ~~ICU activity-les + fremskritt/compliance~~ |
| 2b | ~~Grovplan-strip~~ (current/next + dager til race) |
| 2c | UX-polish leftovers |
| 2d | ~~Returning-user login~~ |
| 2e | ~~Plan + Compliance-faner, form_estimates, Sync til Intervals~~ (`5cfb32f`) |
| 2f | **Dashboard** — status, timer, søvn (wellness READ), vekt/fett med Du-toggle |
| 2g | **Øktbibliotek** — list, spør coach, completion + reason |
| 3 | Invite + training_pair |
| 4 | Intervals-write videre etter telefon-test av sync |
| 5 | Proaktiv post-MVP |

**Deploy:** `fly deploy --app lofoten-coach` · live health OK på `lofoten-coach.fly.dev` (2026-09-27).

## Anti

Ingen Pondus-import, ingen Slack i MVP, ingen tool-spam-chat, ingen full kalender-UI, ingen stille overwrite av Intervals-økter, ingen body-comp-UI uten av-toggle. Se [anti-patterns.md](anti-patterns.md).

## Relaterte docs

[gap-analysis-2026-09-27.md](gap-analysis-2026-09-27.md) · [competitor-humango.md](competitor-humango.md) · [mvp-scope.md](mvp-scope.md) · [progress-compliance.md](progress-compliance.md) · [periodization-overview.md](periodization-overview.md) · [athlete-profile.md](athlete-profile.md) · [partner-sync.md](partner-sync.md) · [returning-login.md](returning-login.md) · [README.md](README.md)
