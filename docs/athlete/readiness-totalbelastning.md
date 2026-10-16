# TB-Score — treningsevne / totalbelastning

**Mål:** Én **0–100**-indeks for *«har jeg kapasitet **nå** (klokkeslett), ikke bare i dag?»* — totalbelastning, ikke Garmin-black-box.

**Snapshot (default):** `--at now` + **activities.csv** → timer siden siste økt, load siste 24/48 t, plus morgen-HRV/søvn fra wellness-dato.

Garmin **Training Readiness** oppdateres gjennom dagen; TB-Score gjør det samme eksplisitt fra Intervals-aktiviteter.

## Hva inngår (v2, subjektiv **av**)

| Komponent | Vekt (default) | Kilde |
|-----------|----------------|--------|
| **Kronisk form** | 30 % | `ctl`, `atl` → TSB og ATL/CTL |
| **Tid siden siste økt** | 25 % | `activities.csv`: sluttid + `icu_training_load` |
| **Akutt vindu** | 10 % | Sum load **siste 24/48 t** fra `--at`; straff hvis hard økt &lt; 14 t siden |
| **HRV** | 22 % | `hrv` vs **21-dagers median** (wellness-dato) |
| **Hvilepuls** | 13 % | `restingHR` vs median |
| **Søvn** | 10 % | `sleepSecs` / score (natt til wellness-dato) |
| **Subjektivt** | **0 %** | Kun med `--include-subjective` (gaming-risiko) |

**Livsjustering** (fra `readiness-config.json`, ikke Garmin):

- `calorie_deficit_active`: **−6** poeng når aktivt underskudd (William okt 2026)

Juster eller slå av i JSON når situasjonen endres. Snus taper er **ikke** auto — bruk `stress` / `comments` eller legg inn egen nøkkel senere.

## Tolkning (styr plan, ikke moral)

| TB-Score | Farge | Coach-handling |
|----------|-------|----------------|
| **≥ 78** | Grønn | Planlagt kvalitet ok |
| **58–77** | Gul | Plan B (f.eks. 6×2), ellers Z2; maks én hard økt/uke |
| **&lt; 58** | Rød | Recovery — ingen VO2/threshold-test |

Sammenlign **trend** (7–14 dager), ikke én dag isolert.

## Kjøring

```bash
python3 scripts/fetch_intervals_wellness.py --days 30 -o data/intervals/exports/wellness-latest.csv
python3 scripts/fetch_intervals_activities.py --days 30 -o data/intervals/exports/activities-latest.csv

# Snapshot nå (anbefalt før intervall)
python3 scripts/compute_readiness.py data/intervals/exports/wellness-latest.csv \
  --activities data/intervals/exports/activities-latest.csv --at now

# «Kan jeg kjøre 5×3 kl 17?»
python3 scripts/compute_readiness.py data/intervals/exports/wellness-latest.csv \
  --activities data/intervals/exports/activities-latest.csv --at 2026-10-16T17:00

python3 scripts/compute_readiness.py ... --json
python3 scripts/compute_readiness.py ... --push-readiness   # Intervals readiness-felt
python3 scripts/compute_readiness.py ... --daily            # kun daglig historikk
python3 scripts/compute_readiness.py --self-test

# Standard coach-rapport (tekst + alle grafer)
python3 scripts/generate_coach_report.py --days 30
python3 scripts/generate_coach_report.py --fetch --days 30   # med Intervals API
```

**Grafer:** `reports/coach/latest/tb-dashboard.png`, `tb-score-trend.png`, `tb-components-now.png`, `tb-score-now.png`.

**Konfig:** [`readiness-config.json`](readiness-config.json)

**Kobling profil:** [`profile.md`](profile.md) → *Totalbelastning* — TB-Score er **operativt mål** for om uken skal strammes eller holdes.

## Garmin vs TB-Score

| | Garmin Readiness | TB-Score |
|---|------------------|----------|
| Trening | Ja (ukjent vekting) | CTL/ATL/TSB eksplisitt |
| Liv (underskudd) | Nei | Ja (config) |
| Tid siden hard økt | Delvis | TB + activities |
| Subjektivt | Delvis | TB default **av** |
| Synk | `readiness`-kolonne hvis fylt | `--push-readiness` eller manuell |

Bruk begge: hvis Garmin **høy** og TB-Score **gul** → stol på **TB** når ATL ≫ CTL (typisk etter hard helg).

## Vedlikehold

- Etter **FTP/CSS-test** eller stor formendring: vurder å justere `bands` eller vekter i JSON (commit i repo).
- Når **ikke** lenger i kaloriunderskudd: sett `calorie_deficit_active` til **0** eller fjern nøkkelen.
