# Intervals.icu — analyse-hub for coach (Ole)

**Kort svar:** Ja. Intervals.icu er **bedre enn TrainingPeaks** for at agenten skal lese **fullførte** økter (åpent API, plan↔aktivitet-parring, soner allerede beregnet). **Samtidig** med TP betyr i praksis: **én opptakskilde** (Garmin/Wahoo/Zwift) som sender til begge, **plus** at **plan** speiles til Intervals så analyse ikke bare ser «tom kalender».

TP forblir greit som **plan-import** (TrainingDojo + ZWO) slik du har nå.

---

## Anbefalt arkitektur (William 2026)

```text
Plan (repo / Dojo) ──► TrainingPeaks kalender  (økttekst, sykkel-ZWO)
        │
        └── (valgfritt speil) ──► Intervals.icu kalender  (plan vs faktisk)

Garmin / Wahoo / Zwift ──► Intervals.icu  (aktiviteter, soner, PMC)
        │
        └── (valgfritt) ──► TrainingPeaks  (hvis du vil beholde grønn/rød-kalender der)
```

| Rolle | TrainingPeaks | Intervals.icu |
|--------|---------------|---------------|
| Plan fra coach / Dojo | **Primær** | Speil (anbefalt for analyse) |
| Fullførte økter | CSV-eksport (tungt) | **API / activities.csv** |
| Ole / agent ukesopp | Fungerer, ofte uten TSS i plan-CSV | **Anbefalt** — load, IF, soner, parring |
| Push kommentarer tilbake | Partner API | Ikke nødvendig — agent svarer i Cursor |

---

## Steg 1 — Aktiviteter «samtidig» (automatisk)

1. **Intervals.icu → Settings → Connections:** Koble **Garmin** (eller Strava/Wahoo — én primær er nok).
2. **TrainingPeaks:** Koble samme enhet til TP (Garmin Connect → TP), *eller* bruk Intervals sin kobling til TP hvis du har det aktivert (sjekk Connections på begge).
3. Etter hver økt: aktiviteten skal dukke opp på Intervals **uten** at agenten gjør noe. TP kan være noen minutter forsinket — det er normalt.

Agenten **laster ikke opp** FIT-filer for deg; det gjør enheten/synken.

---

## Steg 2 — Plan på Intervals (så analyse gir mening)

Uten plan på Intervals ser agenten bare watt og puls — ikke om du traff **R01 easy** vs. planlagt struktur.

**Alternativer:**

| Metode | Beskrivelse |
|--------|-------------|
| **A. Manuelt** | Dra inn sykkel-ZWO fra `workouts/zwo/bike/` i Intervals-kalender (løp/svøm: bygg eller kopier fra Dojo-beskrivelse). |
| **B. tp2intervals** | [freekode/tp2intervals](https://github.com/freekode/tp2intervals) — speiler plan TP ↔ Intervals (krever TP-cookie + Intervals API-nøkkel). |
| **C. trainingpeaks-to-intervals-icu** | [Sladck/trainingpeaks-to-intervals-icu](https://github.com/Sladck/trainingpeaks-to-intervals-icu) — plan TP → Intervals med absolutte watt/pace fra **dine TP-terskler** (210 W, 6:20, 165). |

For **Cursor-coach** er **B eller C** mest lik «alt på ett sted for analyse», mens du **fortsatt importerer plan via Dojo til TP**.

Fremtidig repo-idé: push plan direkte til Intervals API fra `plans/csv/` (samme som nivå 2 for TP) — ikke bygget ennå.

---

## Steg 3 — Koble agenten (API-nøkkel, ikke i git)

1. Intervals → **Settings** → **Developer settings** → generer **API key**.
2. Lokalt: `.env` (allerede i `.gitignore`):

   ```bash
   INTERVALS_API_KEY=din_nøkkel_her
   ```

3. Hent siste uke til repo (valgfritt lagring):

   ```bash
   source .env  # eller export INTERVALS_API_KEY=...
   python3 scripts/fetch_intervals_activities.py --days 7 \
     -o data/intervals/exports/uke.csv
   python3 scripts/analyze_intervals_export.py data/intervals/exports/uke.csv
   ```

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
