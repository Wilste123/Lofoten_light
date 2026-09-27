# Veiledet setup / onboarding (AI + knowledge)

**Branch:** `cursor/web-coach-mvp-42ac` · **PR:** [#13](https://github.com/Wilste123/Lofoten_light/pull/13)

## Produktkrav

Ny bruker lander **ikke** i tom chat. De jobber med treneren (AI) for å samle mål, bakgrunn, helse, fritekst og valgfri Intervals-nøkkel. Deretter genereres **periodisering + treningsplan-outline** med **forhåndsvisning** før lagring/sync.

Onboarding er **agil** — ikke én mal for alle:

| Profil | Typisk divergens |
|--------|------------------|
| Nybegynner | Lavere uketimer, lengre grunnlag, `svom/nybegynner-til-triatlet.md` |
| Comeback / tidligere atlet | Re-etablering uten 2019-volum, `lop/oppbygging-etter-pause.md` |
| Skade / rehab | ACWR-trygg progresjon, `skader/belastningsstyring-acwr.md` |
| Tidsklemma | Færre blokker, effektiv base, `mental/kontinuitet-motivasjon.md` |
| Flersport / Lofoten | Tri-periodisering + brick/OWS knowledge |
| Halvmaraton / løper | Løpsfokus — **ikke** default swim/bike/run-tri-pack |

## Hovedprofil / `athlete_type` (muterbar)

Coach infererer og lagrer en **primær utøvertype** (`athletes.athlete_type` + `profile.md`):

| Id | Norsk label | Sesongsplit (typisk) |
|----|-------------|----------------------|
| `half_marathon_runner` | halvmaraton-løper | ~80 % løp |
| `marathon_runner` | maraton-løper | ~80 % løp |
| `runner` | løper | løpsdominant |
| `cyclist` | syklist | sykkeldominant |
| `swimmer` | svømmer | svømdominant |
| `triathlete` | triatlet | svøm/sykkel/løp |
| `beginner_multi` | nybegynner flersport | balansert intro |
| `general_endurance` | generell utholdenhet | startpunkt |

**Treningsavtaler (setup → SQLite):**

| Felt | Betydning |
|------|-----------|
| `goal_text` | Du → Mål — syntetiseres fra samtale («Triatlon 2028») hvis extract mangler |
| `goal_race_date` | År-only («2028») → sen sesong det året (f.eks. 2028-09-15); ikke ~8 mnd default |
| `allowed_disciplines` | JSON-liste: `run` / `bike` / `swim` / `strength` |
| `sessions_per_week` | Heltall 2–8 — loft for WORKOUT-økter/uke |
| `fitness_notes` | Form OK / trener allerede → ikke «Re-etablering» |
| `agreements` / `notes` / `weekly_focus` / `injury_notes` | Persisteres ved confirm til SQLite + `profile.md` |

Halvmaraton / «kun løp + styrke» / «3 økter» → **ikke** default tri-uke. Form OK + N×/uke → **Base**, ikke Re-etablering. Preview viser `constraints_summary_nb` + `prescription_rationale_nb` (norsk coach-stemme).

**Preview === push:** Samme `build_plan_sync_bundle` for Forhåndsvis og Intervals-pending. `draftPayload` sender `sessions_per_week` / `allowed_disciplines` / `athlete_type` / `fitness_notes`. Confirm kjører `merge_confirm_athlete_patch` så Du-fanen ikke blir blank.

**Du → chat → plan:** «Snakk med treneren om endringene» **lagrer Du-skjemaet først**, deretter `POST /v1/athlete/me/plan/adjust/preview` (knowledge-grounded; `sessions_per_week` / `goal_race_date` fra lagret profil). Bekreft med `…/plan/adjust/confirm`. Intervals skrives **ikke** stille.

**Intervals WORKOUT-horisont:** alltid første **2 uker** × avtalt økter/uke (f.eks. 3 → ~6, 5 → ~10). Grovplan-**NOTE** kan dekke sesong til måldato — UI forklarer skillet så det ikke føles «broken».

**Muterbar over tid:** `generell` → `runner` → `half_marathon_runner` / maraton når mål blir klart. Historikk i `athlete_type_notes`. Chat kan foreslå `athlete_type_update` (preview → `POST /v1/athlete/me/athlete-type`) — plan skrives **ikke** stille om; øktvalg følger ny type etter bekreftelse.

## Knowledge som mater øktvalg

| Situasjon | Nøkkelfiler |
|-----------|-------------|
| HM / løpsfokus | `lop/halvmaraton-periodisering.md`, `lop/ukeplaner-lav-frekvens.md`, `lop/styrke-og-lop.md` |
| 2–5 økter / tidsklemma | `lop/ukeplaner-lav-frekvens.md`, `coach/ukeplaner-generell-utholdenhet.md`, Seiler 80/20 + IOC load (`kilder/referanser.md`) |
| Nybegynner løp | `lop/nybegynner-lop.md` |
| Comeback | `lop/oppbygging-etter-pause.md` |
| Load / intensitet | `load-and-intensity.md` |
| Tri / Lofoten | `triathlon/periodisering-mot-2027.md`, `coach/ukemaler.md` |

Injiseres via `knowledge_ctx.select_knowledge_paths` (setup chat + plan). Prescription i `plan_workouts.py` plukker navngitte `workouts/planned/**` med restitusjonsdager — max **2 uker** WORKOUT til Intervals.

## Flyt (UI)

1. **Profil** — navn, brukernavn, trener/aksent (minimalt)
2. **Samtale** — `POST /v1/setup/chat` (ett LLM-kall + adaptive knowledge-chunks)
3. **Intervals** — norsk how-to (Settings → Developer Settings); hopp over OK
4. **Forhåndsvis** — `POST /v1/setup/plan/preview` → blokker + overview + athlete_type
5. **Bekreft** — `POST /v1/setup/confirm` → SQLite + `profile.md` (Intervals kun hvis huket + senere confirm)

**Du → Innstillinger:** Logg ut (clear localStorage). Start setup på nytt = dobbelt bekreftelse (`acknowledge_wipe` + `confirm_phrase=SLETT`) → valgfri sletting av **kun** coach-Events (`ll-coach-*` / `ll-coach-w-*`) på Intervals.

Seed `william` er `setup_completed=true` (seed / migrate) — login går rett til appen, ikke AI-setup. Re-seed på boot overskriver ikke goals, `plan_blocks`, `profile.md` eller Intervals-secrets når setup er fullført. Nye brukere (`Ny bruker`) får fortsatt full AI-flyt.

## API

| Endpoint | Skriver? |
|----------|----------|
| `POST /v1/setup/chat` | Nei — reply + extracted draft (+ athlete_type) |
| `POST /v1/setup/plan/preview` | Nei — plan_blocks + knowledge meta |
| `POST /v1/setup/confirm` | Ja lokalt; Intervals pending kun hvis `prepare_intervals_sync` (feiler ikke hele lagringen) |
| `POST /v1/athlete/me/setup/reset` | Ja — wipe plan/mål; valgfri ICU coach-delete |
| `POST /v1/athlete/me/athlete-type` | Ja — muterbar type + historikk; valgfri plan-preview |
| `POST /v1/athlete/me/plan/adjust/preview` | Nei — grovplan fra Du-profil (seed chat + blocks) |
| `POST /v1/athlete/me/plan/adjust/confirm` | Ja lokalt blocks; Intervals kun pending ved prepare |
| `POST /v1/athlete/me/intervals/workouts/remove/preview` | Pending delete (ll-coach-* only) |
| `POST /v1/athlete/me/intervals/calendar/confirm` | Ja ICU — etter pending |

## Knowledge-injeksjon

Heuristisk utvalg i `knowledge_ctx.py` (ingen vector DB):

**Alltid:** `coach/coach-filosofi.md`, `treneridentitet.md`, `ole-grenser.md`, `feil-og-fixes.md`, periodisering/`ukemaler`/`load-and-intensity`, ernæring-kort.

**Betinget** (nøkkelord i samtale/draft): beginner → svøm-nybegynner; returning → oppbygging-etter-pause + OPV; injury → ACWR/skader; tid → sovn/mental; disiplinord → svøm/sykkel/løp; race → lofoten/brick. Multisport krever eksplisitte tri-/race-cues (ikke bare ordet «løp»).

Plan-generering: **ett** LLM-kall med knowledge-bundle → JSON-blokker, validert i Python. Uten API-nøkkel: signal-aware deterministic fallback (fortsatt ulik struktur per arketype + athlete_type).

## Preview vs Intervals

| Lagres ved bekreft | Synces til Intervals (valgfritt, preview→confirm) |
|--------------------|-----------------------------------------------------|
| Athlete-felt (inkl. `athlete_type`, `allowed_disciplines`, `sessions_per_week`), `plan_blocks`, `profile.md`, valgfri `athlete_secrets` | **WORKOUT** første **maks 2 uker** via CLI-byggeren — kun avtalte disipliner / frekvens |
| — | Grovplan-**NOTE** ukemarkører (`ll-coach-…`) — kan dekke sesong |
| — | Ikke stille auto-push; seed `william` tvinges ikke |

**Builder (struktur):** `scripts/intervals_push_calendar.py` + `scripts/intervals_lib.py`  
**Prescription (innhold):** knowledge-templated valg av `workouts/planned/**` etter athlete_type + constraints + signaler (+ norsk `prescription_rationale_nb`).

## Feilmeldinger

Setup-preview/confirm skal aldri bare vise «Feil 500» — API returnerer `detail` / `intervals_prep_error` med lesbar norsk tekst (inkl. `KeyError`/`ImportError`-årsak). Økt-forhåndsvisning kan degradere til notes-only uten å drepe periodiseringen.

## Tester

`services/coach-api/tests/test_setup_onboarding.py`  
`services/coach-api/tests/test_plan_align_onboarding.py` — 2028-mål, ingen re-etablering ved form OK, preview≡sync, Du-persist, plan-adjust  
`services/coach-api/tests/test_plan_workouts.py`  
`services/coach-api/tests/test_athlete_type.py`  
`services/coach-api/tests/test_workout_constraints.py`  
`services/coach-api/tests/test_chat_intervals.py`
