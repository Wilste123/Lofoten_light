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

**Muterbar over tid:** `generell` → `runner` → `half_marathon_runner` / maraton når mål blir klart. Historikk i `athlete_type_notes`. Chat kan foreslå `athlete_type_update` (preview → `POST /v1/athlete/me/athlete-type`) — plan skrives **ikke** stille om; øktvalg følger ny type etter bekreftelse.

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
| Athlete-felt (inkl. `athlete_type`), `plan_blocks`, `profile.md`, valgfri `athlete_secrets` | **WORKOUT** første 1–2 uker via CLI-byggeren — etter athlete_type |
| — | Grovplan-**NOTE** ukemarkører (`ll-coach-…`) |
| — | Ikke stille auto-push; seed `william` tvinges ikke |

**Builder (struktur):** `scripts/intervals_push_calendar.py` + `scripts/intervals_lib.py`  
**Prescription (innhold):** knowledge-templated valg av `workouts/planned/**` etter athlete_type + signaler.

## Feilmeldinger

Setup-preview/confirm skal aldri bare vise «Feil 500» — API returnerer `detail` / `intervals_prep_error` med lesbar norsk tekst (inkl. `KeyError`/`ImportError`-årsak). Økt-forhåndsvisning kan degradere til notes-only uten å drepe periodiseringen.

## Tester

`services/coach-api/tests/test_setup_onboarding.py`  
`services/coach-api/tests/test_plan_workouts.py`  
`services/coach-api/tests/test_athlete_type.py`  
`services/coach-api/tests/test_chat_intervals.py`
