# Kroppssammensetning — smartvekt (BIA) + coach-mål

William: **187 cm**, start **~90 kg** (sep 2026), **race &lt;80 kg** Half Extreme aug 2027. Smartvekt (BIA) brukes til **trend**, ikke til å styre livet dag for dag.

## Målerutine (ellers er tallene søppel)

| Regel | Hvorfor |
|--------|---------|
| **Samme tid:** morgen, etter toalett, **før** mat/kaffe | Væske og mageinnhold svinger kg og «vann %» |
| **Samme underlag** (hardt gulv, ikke teppe) | BIA er upresis nok uten ekstra feil |
| **Logg 3–7 dagers snitt** i Intervals wellness / TP-notat | Én dag = støy |
| **Ikke etter hard økt / alkohol / flyreise** | Vannbinding forvrenger |
| **Samme enhet** hele perioden | Ikke sammenlign Garmin vs Withings vs Tanita absolutt |

**BIA-feil:** Consumer-skalaer leser ofte **3–5 prosentpoeng høyere** fettprosent enn DEXA på magre menn. Bruk **din egen kurve** — ikke internett-tabeller for «absolutt sannhet».

---

## Mål ved race (Half Extreme, ca. 78–79 kg)

Tallene under er **coach-mål for en høy mann (187 cm) som skal løpe/sykle bakke** — justeres hvis styrke eller FTP kollapser.

| Parameter | Race (aug 2027) | Kommentar |
|-----------|-----------------|-----------|
| **Vekt** | **&lt;80 kg** (sweet spot **78–79**) | Avtale med William sep 2026 |
| **Fett % (BIA)** | **12–15 %** på skala ≈ **~10–12 %** «ekte» | Under **10 % BIA** over tid: sjekk energi, skade, libido — ikke jakt |
| **Fettfri masse (FFM)** | **Hold ~68–70 kg** (trend) | FFM **ned** &gt;1–2 kg fra base → brems vektnedgang, mer mat/styrke |
| **Vann % (total)** | **55–60 %** av kroppsvekt (morgen) | Ikke «mer er bedre» — **stabil snitt** viktigere enn tall |
| **Muskelmasse (skala)** | **Stabil eller opp** mens kg faller | BIA overestimerer muskel; se styrkerom + FTP |
| **Visceralt fett** (hvis skala viser) | **Nedover trend** | Mer helse enn prestasjon, men god indikator på recomp |

### Referanse — historikk

| Tidspunkt | Vekt | FTP | Merk |
|-----------|------|-----|------|
| Peak sykkel | **~74 kg** | **410 W** | ~5,5 W/kg — **ikke** automatisk race-mål for tri |
| Sep 2026 | **~90 kg** | **210 W** | ~2,3 W/kg — re-trening + masse |

---

## Off-season vs race (BIA-fett % på **din** skala)

| Periode | Fett % (BIA, trend) | Vekt (ca.) |
|---------|---------------------|------------|
| Re-etablering / base vinter | **16–20 %** ok | 86–90 |
| Build (apr–jun) | **14–17 %** | 82–86 |
| Spesifikk + taper | **12–15 %** | **78–80** |

**Rødt flagg (stopp/aggressiv nedjustering av underskudd):**

- FFM faller 3 uker på rad  
- FTP eller styrke (hovedløft) faller mens vekt faller  
- Konstant sult, søvn ødelagt, sykdom  
- Fett % BIA **under 11–12 %** uten at prestasjon og velbefinnende er upåklagelig  

Se også `knowledge/ernaring/grunnlag.md` — ved uønsket vekttap i base: **øk mat før du kutter trening**.

---

## Intervals + CSV (BIA-felter)

| Fil | Bruk |
|-----|------|
| `plans/csv/intervals-bia-daily.csv` | **Hver morgen:** vekt, fett %, vann %, FFM, muskel, visceral, RHR |
| `plans/csv/intervals-bia-ukesnitt.csv` | **Søndag:** 7-dagers snitt + `opv_line` til coach |

**Push til Intervals wellness** (API-felt `weight`, `bodyFat`, `restingHR`; vann/FFM/muskel i `comments` som `BIA water=… ffm=…`):

```bash
# Daglige rader
python3 scripts/push_intervals_wellness.py plans/csv/intervals-bia-daily.csv --dry-run
python3 scripts/push_intervals_wellness.py plans/csv/intervals-bia-daily.csv

# Søndags ukesnitt (lagres på week_ending-dato)
python3 scripts/aggregate_bia_weekly.py --week-ending 2026-10-04   # fyller snitt fra daily
python3 scripts/push_intervals_wellness.py plans/csv/intervals-bia-ukesnitt.csv --weekly
```

Hent tilbake / analyse: `fetch_intervals_wellness.py` + `analyze_intervals_wellness.py`.

## Hva du logger til OPV (ukentlig, søndag)

**UKENOTE (søndag 19:00 i Intervals)** gjentar vekttak + BIA-rutine — se `plans/csv/trainingdojo-uke-notater-4uker-opv*.csv`.

Fyll `opv_line` i `intervals-bia-ukesnitt.csv` (eller kommentar i Intervals). Eksempel:

`Snitt 87,2 kg | fett 16,1 % | FFM 73,1 | vann 57 % | styrke ok`

Agenten bruker dette mot tabellen i `plans/2026-2027-12mnd-periodisering.md`.
