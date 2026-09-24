# Coach (Ole) ↔ TrainingPeaks — uten TrainingDojo?

Kort svar: **full automatisk «Ole i TP»** krever **TrainingPeaks Partner API** (OAuth-app). **Personlig hobby-API får du normalt ikke.** TrainingDojo bruker **ditt utøver-token** i nettleseren — det er en mellomløsning, ikke offisiell integrasjon.

---

## Hva «snakke sammen» kan bety

| Ønske | Realistisk uten partner-API? | Merk |
|--------|-------------------------------|------|
| Legge plan på kalender | Delvis | CSV → **TrainingDojo**, eller **ZWO + manuell dra**, eller eget skript med **samme bearer-token** som Dojo (lokalt, `.env`) |
| Ole leser **fullførte** økter | Ja (manuelt/halvauto) | **CSV-eksport** → `scripts/analyze_tp_export.py` + lim inn skjerm/kommentar til agent |
| Ole **kommenterer** økter i TP | Nei (offisielt) | Krever `workouts:details` (post comments) via **partner**-token |
| Oppdatere FTP/soner fra agent | Nei | `athlete:profile` via partner, eller du setter i TP UI |
| Ukentlig ukesopp automatisk | Delvis | Agent når du **sender** eksport; evt. cron + eksport hvis du bygger partner-app |

---

## Tre nivåer (anbefalt rekkefølge)

### Nivå 1 — Det du har nå (ingen API)

**Trener:** Cursor-agent + filer i repo (`plans/`, `knowledge/coach/`).  
**TP:** Du importerer plan (Dojo eller ZWO), trener, **kommenterer** i TP.  
**Tilbake til Ole:** Eksport CSV eller skjermbilde → agent gir ukesopp / øktkommentar (se `trener-feedback-syklus.md`).

Dette er nærmest **NTG med Ole** — han så ikke API heller, han så **kalender + kommentarer**.

### Nivå 2 — «Dojo i eget hus» (samme token, uten Dojo-nettside)

TrainingDojo er bare en **frontend** som kaller TP med **bearer token** du kopierer fra innlogget session.

Mulig å lage `scripts/tp_push_calendar.py` i dette repoet som:

1. Leser `trainingdojo-*.csv` fra `docs/trainingpeaks/imports/`
2. Leser `TP_BEARER_TOKEN` fra miljø (aldri i git)
3. Pusher planlagte økter via **samme uoffisielle** API som Dojo

**Fordeler:** Ingen tredjepartsnettsted; agenten kan generere CSV, du kjører ett kommando.  
**Ulemper:** Token utløper; TP kan endre API; ikke dokumentert for personlig bruk; **ikke** lesing/kommentarer uten partner.

*Status i repo: ikke implementert — si fra om du vil at vi bygger nivå 2.*

### Nivå 3 — Ekte integrasjon (Partner API)

1. Søk tilgang: https://api.trainingpeaks.com/request-access  
2. OAuth-app med scopes f.eks. `workouts:read`, `workouts:plan`, `workouts:details` (kommentarer), `athlete:profile`  
3. Repo kan da få f.eks. `scripts/tp_oauth/` + synk plan/kommentarer/lesing

TP skriver eksplisitt at de **ikke** gir API for ren personlig bruk — realistisk hvis du bygger et **lite verktøy** (f.eks. «Lofoten coach sync») eller har **coach-konto** med utøvere.

**Premium utøver:** Noen plan-endepunkter fungerer for egen kalender med riktig token — fortsatt via godkjent app.

---

## Alternativ hub: Intervals.icu

Intervals.icu har **åpenere API** og synk mot TP. TrainingDojo støtter også Intervals.icu. Flyt:

Agent → CSV → Intervals → (synk) → TP  

Mer teknisk oppsett, men bedre for **automation** enn å vente på TP partner.

**Anbefalt for William:** aktiviteter via Garmin → Intervals; plan speiles TP → Intervals; agent henter uke med `scripts/fetch_intervals_activities.py` + `analyze_intervals_export.py`. Se **[`integrasjon-intervals-icu.md`](integrasjon-intervals-icu.md)**.

---

## Anbefaling for William (2026)

| Prioritet | Handling |
|-----------|----------|
| 1 | Hold **trener i Cursor** + **TP som kalender** |
| 2 | **CSV-eksport** ukentlig (eller etter harde økter) til agent — det *er* Ole som «ser gjennom øktene» |
| 3 | Unngå dobbeltarbeid: **én** import-metode (Dojo *eller* eget skript, ikke begge) |
| 4 | Hvis du vil automatisere push: enten **nivå 2-skript** i repo, eller søk **partner API** med konkret use case |

---

## Sikkerhet

- `TP_BEARER_TOKEN`, `client_secret`, refresh tokens: kun i **`.env`** lokalt, listet i `.gitignore`
- Agent i cloud skal **ikke** lagre TP-passord uten at du eksplisitt setter secrets i miljø

---

## Relatert

- [`api.md`](api.md) — partner-endepunkter  
- [`trener-feedback-syklus.md`](trener-feedback-syklus.md) — OPV uten API  
- [`importere-plan-norsk.md`](importere-plan-norsk.md) — import i dag
