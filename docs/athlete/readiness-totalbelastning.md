# TB-Score — treningsevne / totalbelastning

**Mål:** Én **0–100**-indeks som svarer på *«har William kapasitet til det som står i planen i dag?»* — ikke bare Garmin, ikke bare CTL.

Garmin **Training Readiness** bruker søvn, HRV, stress og nylig trening internt. **TB-Score** er repoets variant, optimalisert for **Half Extreme-comeback** og **totalbelastning** (trening + recovery + kjente livsfaktorer fra profil).

## Hva inngår

| Komponent | Vekt (default) | Kilde |
|-----------|----------------|--------|
| **Trening** | 35 % | Intervals `ctl`, `atl` → TSB og ATL/CTL-ratio |
| **HRV** | 25 % | `hrv` vs **21-dagers median** (personlig baseline) |
| **Hvilepuls** | 15 % | `restingHR` vs median |
| **Søvn** | 15 % | `sleepSecs` mot mål (7,5 h) eller `sleepScore` |
| **Subjektivt** | 10 % | `soreness`, `fatigue`, `stress`, `injury` (hvis fylt) |

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
python3 scripts/compute_readiness.py data/intervals/exports/wellness-latest.csv
python3 scripts/compute_readiness.py data/intervals/exports/wellness-latest.csv --json
python3 scripts/compute_readiness.py data/intervals/exports/wellness-latest.csv --push-readiness  # skriver readiness i Intervals
python3 scripts/compute_readiness.py --self-test
```

**Konfig:** [`readiness-config.json`](readiness-config.json)

**Kobling profil:** [`profile.md`](profile.md) → *Totalbelastning* — TB-Score er **operativt mål** for om uken skal strammes eller holdes.

## Garmin vs TB-Score

| | Garmin Readiness | TB-Score |
|---|------------------|----------|
| Trening | Ja (ukjent vekting) | CTL/ATL/TSB eksplisitt |
| Liv (underskudd) | Nei | Ja (config) |
| Subjektivt | Delvis | Intervals-felt |
| Synk | `readiness`-kolonne hvis fylt | `--push-readiness` eller manuell |

Bruk begge: hvis Garmin **høy** og TB-Score **gul** → stol på **TB** når ATL ≫ CTL (typisk etter hard helg).

## Vedlikehold

- Etter **FTP/CSS-test** eller stor formendring: vurder å justere `bands` eller vekter i JSON (commit i repo).
- Når **ikke** lenger i kaloriunderskudd: sett `calorie_deficit_active` til **0** eller fjern nøkkelen.
