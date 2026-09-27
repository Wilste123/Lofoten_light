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
- ICU-**write** krever alltid preview → confirm:
  - **Plan:** grovplan-noter (`ll-coach-…`) under Plan-fanen.
  - **Chat:** enkle kalender-WORKOUT (`ll-coach-w-…`) når utøveren ber om å legge inn økt — se [dashboard-okter.md](dashboard-okter.md).
- Full ZWO/CSV-ukeplan pushes fortsatt via CLI, ikke via chat. Uten Sync forblir Intervals urørt.

Uten Intervals-credentials: **demo/stub**-tall merket «Demo».

## Dashboard-side (ønsket / neste)

Dedikert (eller utvidet Overblikk) **training status**-flate — fortsatt companion, ikke ICU-klon:

| Blokk | Innhold | Kilde |
|-------|---------|--------|
| **Periode** | 7d / 14d / 30d / 90d / custom fra–til | Query på `GET /v1/dashboard` |
| **Training status** | Kort uplift, nåværende blokk, dager til race, Intervals-koblet? | Overview + plan_blocks |
| **Timer / volum (periode)** | Per disiplin hours + øktantall for valgt vindu | App-beregnet fra ICU activities |
| **Sesong compliance** | Completed/target + % (egen blokk) | Sesongvindu vs targets |
| **Søvnanalyse** | Trend i valgt periode | App-beregnet fra Intervals **wellness** |
| **Vekt + body-fat** | Trend / enkel analyse | Wellness/BIA eller manuell; **kan slås AV** under Du |

### Toggle (Du-innstillinger)

- `[ ] Vis vekt- og fettanalyse på Dashboard` — OFF skjuler blokken helt.
- Senere: egen toggle for søvn hvis ønskelig.

## Workout builder / øktbibliotek (ønsket / neste)

1. **Liste økter** — speil planlagte/fullførte fra Intervals (READ) og/eller lokale maler (`workouts/`).
2. **Spør coach om økten** — deep-link til Coach med økt-kontekst.
3. **Completion + reason** — gjort / delvis / hoppet over + kort årsak; lagres i app-SQLite. Valgfri senere speil til ICU kun med eksplisitt Sync.

## Onboarding → profilfil

Ved fullført setup **skriver API** `data/athletes/{id}/profile.md` + `plan_blocks`. Oppdateres fra Du.

**Flyt:** veiledet AI-samtale (knowledge-grounded) → forhåndsvis periodisering → bekreft. Se [onboarding-setup.md](onboarding-setup.md).

**Ikke** rigid one-size wizard: nybegynner / comeback / skade / tidsklemma divergerer via knowledge + LLM (fallback signal-aware).

GI-felter kan komme fra samtale eller Du → SQLite + `profile.md`. Chat diagnostiserer aldri.

## Datalagring

SQLite + Fly volume. Secrets: OpenAI i `.env`; Intervals ID+nøkkel i Du → `athlete_secrets`. Se [data-storage.md](data-storage.md).

Sesongmål (`season_*_hours_target`) og `plan_blocks` lever i SQLite — appens SoT for makro.

## Innlogging (returning user)

Uten passord / OAuth. Se [returning-login.md](returning-login.md).

- Start: **Ny bruker** | **Jeg har allerede profil**
- Login: **brukernavn** (slug, f.eks. `william`) — ikke bare rå athlete-id
  - Valgfritt fortsatt: lim inn athlete-id eller invite-token for power users
- Onboarding: velg unik **brukernavn**-slug; seed speiler f.eks. `william`
- `POST /v1/session/login` aksepterer `{ username }` **eller** `{ athlete_id }`
- Under **Du**: vis brukernavn + profil-ID (kopier)
- Snarveier: `?athlete=` og «Bruk seedet William-profil»

**Status:** athlete-id-login landet (`6ce6872`); **username login = fase 2d+** (egen worker).

## Smarte estimater

Gate ≥ 5 sykkeløkter med watt. Se [form-estimates.md](form-estimates.md).

## Faser (oppdatert)

| Fase | Innhold |
|------|---------|
| 0–1 | ~~Docs + onboarding + chat + Du + Intervals-settings~~ (landet på PR #13) |
| 2 | ~~ICU activity-les + fremskritt/compliance~~ (Intervals når credentials; demo ellers) |
| 2b | ~~Grovplan-strip~~ (current/next + dager til race); form_estimates fortsatt gated |
| 2c | UX-polish leftovers (unngå konflikt med Du/Intervals Lagre-fix) |
| 2d | ~~Returning-user login~~ (profil-ID + `POST /v1/session/login`) |
| 2d+ | ~~Username login~~ — unik slug; login med brukernavn; athlete-id valgfritt |
| 2e | ~~Dashboard + Økter~~ (wellness/søvn, kropp-toggle, øktlogg) — se [dashboard-okter.md](dashboard-okter.md) |
| 2e+ | **Dashboard periode** — 7d/14d/30d/90d/custom; trening vs sesong compliance separert |
| 2f | **Veiledet setup** — AI-samtale + knowledge → plan-preview → confirm; restart/logout under Du |
| 3 | Invite + training_pair |
| 4 | Intervals-write: plan-noter + chat WORKOUT (beskrivelse) landet; ZWO/CSV fortsatt CLI |
| 5 | Proaktiv post-MVP |

**Deploy:** `fly deploy --app lofoten-coach` · live health OK på `lofoten-coach.fly.dev` (2026-09-27).

## Anti

Ingen Pondus-import, ingen Slack i MVP, ingen tool-spam-chat, ingen full kalender-UI, ingen stille overwrite av Intervals-økter, ingen body-comp-UI uten av-toggle. Se [anti-patterns.md](anti-patterns.md).

## Relaterte docs

[gap-analysis-2026-09-27.md](gap-analysis-2026-09-27.md) · [competitor-humango.md](competitor-humango.md) · [mvp-scope.md](mvp-scope.md) · [progress-compliance.md](progress-compliance.md) · [dashboard-okter.md](dashboard-okter.md) · [periodization-overview.md](periodization-overview.md) · [onboarding-setup.md](onboarding-setup.md) · [athlete-profile.md](athlete-profile.md) · [partner-sync.md](partner-sync.md) · [returning-login.md](returning-login.md) · [README.md](README.md)