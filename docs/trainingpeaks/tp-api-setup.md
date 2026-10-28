# TrainingPeaks API — oppsett for coach-repo

William planlegger i **TrainingPeaks**. Agenten skal **lese** kalender/økter og **skrive** planlagte økter — samme rolle som Intervals, men TP er plan-sannhet.

---

## To veier inn (velg én)

| Vei | Hvem | Les | Skriv plan | Kommentarer på økter |
|-----|------|-----|------------|---------------------|
| **A. Partner OAuth** (offisiell) | Godkjent app | Ja | Ja | Ja (`workouts:details`) |
| **B. Bearer-token** (midlertidig) | Deg selv | Ofte ja* | Ofte ja* | Usikkert |

\*TrainingPeaks **godtar ikke API for ren personlig bruk** ([FAQ](https://github.com/TrainingPeaks/PartnersAPI/wiki/Frequently-Asked-Questions)). Bearer fra innlogget session (som **TrainingDojo**) kan fungere en stund, men **utløper** og er **uoffisiell** — bruk kun lokalt.

**Anbefaling:** Søk **Partner API** med use case «Lofoten coach sync for én utøver» ([request access](https://api.trainingpeaks.com/request-access)). Implementer **OAuth** når du får `client_id` / `client_secret`. Bruk **B** til appen er godkjent.

---

## Miljøvariabler (`.env`, aldri i git)

```bash
# Les + skriv (Partner access token ELLER midlertidig session bearer)
TRAININGPEAKS_ACCESS_TOKEN=
# alias:
# TP_BEARER_TOKEN=

# Påkrevd for POST /v2/workouts/plan
TRAININGPEAKS_ATHLETE_ID=

# Valgfritt
# TRAININGPEAKS_API_BASE=https://api.sandbox.trainingpeaks.com
```

**Cloud Agent:** legg samme nøkler som **repo secrets** (f.eks. `TRAININGPEAKS_ACCESS_TOKEN`, `TRAININGPEAKS_ATHLETE_ID`) i Cursor environment — ikke i chat.

### Finne `TRAININGPEAKS_ATHLETE_ID`

1. TP web → innlogget → DevTools → Network → filtrer `trainingpeaks.com/api`.  
2. Se JSON på kall som inneholder `"AthleteId"` eller `"Id"` for deg (numerisk).  
3. Eller fra Partner OAuth profile-endepunkt når app er satt opp.

### Bearer-token (vei B, midlertidig)

1. Logg inn på [app.trainingpeaks.com](https://app.trainingpeaks.com).  
2. DevTools → Application → Cookies / eller Network → request headers `Authorization: Bearer …` (samme metode TrainingDojo dokumenterer).  
3. Lim inn i `.env` som `TRAININGPEAKS_ACCESS_TOKEN`.  
4. **Roter** hvis det lekker; forvent at det **stopper** uten varsel.

---

## Partner OAuth (vei A) — scopes

| Scope | Bruk i repo |
|-------|-------------|
| `workouts:read` | `fetch_tp_workouts.py` |
| `workouts:plan` | `tp_push_calendar.py` |
| `athlete:profile` | AthleteId + soner |
| `workouts:details` | Fremtid: OPV-kommentarer på økter |

Flow: [OAuth wiki](https://github.com/TrainingPeaks/PartnersAPI/wiki/OAuth) · eksempel-app [tp-public-api-auth](https://github.com/TrainingPeaks/tp-public-api-auth).

---

## Kommandoer

### Les kalender (max 45 dager)

```bash
python3 scripts/fetch_tp_workouts.py --start 2026-10-01 --end 2026-10-28
# → data/trainingpeaks/exports/tp-workouts.json + .csv
python3 scripts/analyze_tp_export.py data/trainingpeaks/exports/tp-workouts.csv
```

### Skriv plan (TrainingDojo-CSV)

```bash
python3 scripts/tp_push_calendar.py plans/csv/trainingdojo-4uker-2026-09-28.csv \
  --plan-start 2026-09-28 --dry-run

python3 scripts/tp_push_calendar.py plans/csv/trainingdojo-4uker-2026-09-28.csv \
  --plan-start 2026-09-28
```

Structured `Structure` JSON (Workout Builder) er **ikke** auto-generert ennå — beskrivelse + TSS + varighet. Sykkel med watt: fortsatt **ZWO → Library** (`export_intervals_plan_to_tp.py` / manuell).

---

## Agent-arbeidsflyt (mål)

1. **Plan:** William i TP (eller agent `tp_push_calendar.py` etter CSV).  
2. **Utført + wellness:** Fortsatt **Intervals** (Garmin) for agent-analyse (`fetch_intervals_*`, TB-Score).  
3. **TP read:** `fetch_tp_workouts.py` for plan vs faktisk i TP-tall (TSS Planned/Actual).  
4. **Senere:** `workouts:details` for å poste korte OPV-kommentarer (`trener-feedback-syklus.md`).

---

## Feilsøking

| Feil | Fix |
|------|-----|
| 401 Unauthorized | Token utløpt — ny bearer eller refresh OAuth |
| 403 on plan | Basic athlete / mangler Premium eller scope `workouts:plan` |
| Tom liste | Feil datoer eller feil athlete token |
| Duplikat økter | Ikke push samme CSV uten å slette plan i TP først |

---

## Relatert

- [`api.md`](api.md) — endepunkter  
- [`integrasjon-coach-og-tp.md`](integrasjon-coach-og-tp.md) — nivå 1–3  
- [`importere-plan-norsk.md`](importere-plan-norsk.md) — TrainingDojo uten skript
