# Kroppssammensetning — smartvekt (BIA) + coach-mål

William: **187 cm**, **målt baseline ~83 kg / ~20 % fett BIA** (25. sep 2026), **race &lt;75 kg** (sweet spot **74–75**) Half Extreme aug 2027. (Plan-estimat ~90 kg brukes ikke.) Smartvekt (BIA) brukes til **trend**, ikke til å styre livet dag for dag.

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

## Mål ved race (Half Extreme, ca. 74–75 kg)

Tallene under er **coach-mål for en høy mann (187 cm) som skal løpe/sykle bakke** — justeres hvis styrke eller FTP kollapser. **Plan B:** **76–77 kg** race hvis røde flagg jun–jul 2027.

| Parameter | Race (aug 2027) | Kommentar |
|-----------|-----------------|-----------|
| **Vekt** | **&lt;75 kg** (sweet spot **74–75**) | Rev. William nov 2026; historisk sykkel **~74 kg** — tri krever **FFM-sjekk** |
| **Fett % (BIA)** | **11–14 %** på skala | Under **10 % BIA** over tid: sjekk energi, skade, libido — ikke jakt |
| **Fettfri masse (FFM)** | **Hold ≥ ~64–66 kg** (fra baseline ~66) | FFM **ned** &gt;1 kg fra 4-ukers snitt → brems vektnedgang, mer mat/styrke |
| **Vann % (total)** | **55–60 %** av kroppsvekt (morgen) | Ikke «mer er bedre» — **stabil snitt** viktigere enn tall |
| **Muskelmasse (skala)** | **Stabil eller opp** mens kg faller | BIA overestimerer muskel; se styrkerom + FTP |
| **Visceralt fett** (hvis skala viser) | **Nedover trend** | Mer helse enn prestasjon, men god indikator på recomp |

### Referanse — historikk

| Tidspunkt | Vekt | FTP | Merk |
|-----------|------|-----|------|
| Peak sykkel | **~74 kg** | **410 W** | ~5,5 W/kg — **ikke** automatisk race-mål for tri |
| Sep 2026 (målt) | **~83 kg** | **210 W** (guess) | ~2,5 W/kg — re-trening; plan ~90 kg var estimat |

---

## Off-season vs race (BIA-fett % på **din** skala)

| Periode | Fett % (BIA, trend) | Vekt (ca.) |
|---------|---------------------|------------|
| Re-etablering / base vinter | **18–20 %** ok | **82–83** |
| Build (apr–jun) | **14–17 %** | **78–80** |
| Spesifikk + taper | **11–14 %** | **74–76** |

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
