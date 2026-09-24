# Intervals.icu — analyse-hub for coach (Ole)

**Kort svar:** Intervals.icu er **primær hub** for William (plan-push fra repo, analyse, Garmin/Wahoo struktur). TrainingPeaks er valgfri.

**Verifisert oppsett (fungerende push):** [`intervals-push-verified.md`](intervals-push-verified.md) — GitHub secret **`INTERVALS_API`**.

---

## Anbefalt arkitektur (William 2026)

```text
Plan (repo CSV + ZWO) ──► Intervals.icu kalender  (API push)
        │
        ├── Garmin / Wahoo: «Upload planned workouts»
        └── Agent: fetch activities → ukesopp

Garmin / Wahoo / Zwift ──► Intervals.icu  (fullførte økter)
```

| Rolle | Intervals.icu | TrainingPeaks (valgfri) |
|--------|---------------|-------------------------|
| Plan fra coach | **`intervals_push_calendar.py`** | Dojo hvis du vil beholde TP |
| Struktur på klokke / Wahoo | Ja (koblinger i Settings) | Alternativ via TP |
| Ole / agent ukesopp | **API + plan↔aktivitet** | Plan-CSV uten TSS er svak |

---

## Steg 1 — Aktiviteter «samtidig» (automatisk)

1. **Intervals.icu → Settings → Connections:** Koble **Garmin** (eller Strava/Wahoo — én primær er nok).
2. **TrainingPeaks:** Koble samme enhet til TP (Garmin Connect → TP), *eller* bruk Intervals sin kobling til TP hvis du har det aktivert (sjekk Connections på begge).
3. Etter hver økt: aktiviteten skal dukke opp på Intervals **uten** at agenten gjør noe. TP kan være noen minutter forsinket — det er normalt.

Agenten **laster ikke opp** FIT-filer for deg; det gjør enheten/synken.

---

## Steg 2 — Push plan fra repo (strukturerte økter)

Sett **FTP 210 W**, **løp 6:20/km**, **LTHR 165** under Intervals Settings → Zones (samme som TP).

```bash
cp .env.example .env   # fyll INTERVALS_API_KEY, valgfritt INTERVALS_ATHLETE_ID
export $(grep -v '^#' .env | xargs)

# Test uten API
python3 scripts/intervals_push_calendar.py --start 2026-09-28 --dry-run

# Legg 4 uker på kalender (økter + søndags-UKENOTE)
python3 scripts/intervals_push_calendar.py --start 2026-09-28
```

| Input | Fil |
|--------|-----|
| Alle økter | `plans/csv/trainingdojo-4uker-2026-09-28.csv` |
| Sykkel-ZWO på dato | `plans/csv/sykkel-zwo-kalender-4uker.csv` |
| Ukentlige notater | `plans/csv/trainingdojo-uke-notater-4uker-opv.csv` |

Sykkel/løp/svøm får **ZWO** når fil finnes i `workouts/zwo/`. Styrke = tekst + varighet. `external_id` `ll-agent-…` gjør re-push tryggere (`upsert=true`).

**Garmin / Wahoo:** Settings → Connections → huk av **Upload planned workouts** (ca. 7 dager frem).

---

## Steg 3 — Koble agenten (API-nøkkel, ikke i git)

1. Intervals → **Settings** → **Developer settings** → generer **API key** (roter hvis den har vært i chat/logg).
2. Lokalt: `.env` (allerede i `.gitignore`):

   ```bash
   INTERVALS_API=din_nøkkel_her
   INTERVALS_ATHLETE_ID=0
   ```

   GitHub: repo secret **`INTERVALS_API`**. `INTERVALS_API_KEY` fungerer også lokalt. `0` = autentisert utøver i API-path.

3. Hent siste uke til repo (valgfritt lagring):

   ```bash
   source .env  # eller export INTERVALS_API_KEY=...
   python3 scripts/fetch_intervals_activities.py --days 7 \
     -o data/intervals/exports/uke-activities.csv
   python3 scripts/analyze_intervals_export.py data/intervals/exports/uke-activities.csv

   python3 scripts/fetch_intervals_wellness.py --days 7 \
     -o data/intervals/exports/uke-wellness.csv
   python3 scripts/analyze_intervals_wellness.py data/intervals/exports/uke-wellness.csv
   ```

   **BIA / smartvekt (push):** `plans/csv/intervals-bia-daily.csv` og `intervals-bia-ukesnitt.csv` → `scripts/push_intervals_wellness.py` (vekt + `bodyFat` + vann/FFM i `comments`). Se `docs/athlete/kroppssammensetning-smartvekt.md`.

   **Wellness** (søvn, hvilepuls, HRV, vekt, readiness, subjektivt) kommer fra Garmin/klokke **og/eller** push over. API: `GET /athlete/0/wellness.csv?oldest=&newest=`.

4. **Cloud Agent:** Legg `INTERVALS_API_KEY` som **secret** i Cursor-miljøet hvis du vil at agenten skal hente uten manuell CSV. Uten secret: last ned **activities.csv** fra Intervals (eller kjør fetch lokalt) og legg i `data/intervals/exports/` / lim inn i chat.

**Auth:** Personlig nøkkel = HTTP Basic, brukernavn `API_KEY`, passord = nøkkelen ([Intervals API-guide](https://forum.intervals.icu/t/api-access-to-intervals-icu/609)).

---

## Steg 4 — Ukentlig ukesopp (samme OPV-rutine)

Erstatt eller **suppler** TP CSV med Intervals:

1. `fetch_intervals_activities.py` eller manuell export.
2. `analyze_intervals_export.py` → kort talloppsummering.
3. Skriv til agent: «ukesopp» + evt. TP-kommentarer / `AthleteComments`.

Agenten bruker da **faktisk load/TSS**, intensitet og (når plan er speilet) avvik plan vs. utført.

---

## Sikkerhet

- Roter API-nøkkel hvis den lekker.
- Agent i cloud skal **ikke** commite nøkler; kun `INTERVALS_API_KEY` i secrets / lokal `.env`.

---

## Relatert

- [`integrasjon-coach-og-tp.md`](integrasjon-coach-og-tp.md) — TP uten partner API  
- [`trener-feedback-syklus.md`](trener-feedback-syklus.md) — OPV-kommentarer  
- [`../athlete/profile.md`](../athlete/profile.md) — FTP 210 / 6:20 / 165  
