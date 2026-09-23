# Athlete profile — William

Kilde for sannhet for agenten. Oppdater ved nye tester, skader eller endret tilgjengelighet.

## Om William

### Profil

| | |
|---|---|
| Kjønn / alder | Mann, 24 år |
| Høyde / vekt | Ca. 187 cm, ca. 89 kg |
| Bosted | Trondheim / Trøndelag, Norge |

### Idrettsbakgrunn

- **Landeveissykling** ca. 11–19 år, konkurrerte på relativt høyt nivå
- Erfaring med strukturert utholdenhetstrening, intervaller, perioder med høy belastning, konkurranser og restitusjon
- **Siste ~4–5 år:** svært lite og ujevn trening; enkelte perioder med bedre form, ingen stabil langtidsrutine

### Disipliner (subjektivt)

| Disiplin | Erfaring | Motivasjon nå |
|----------|----------|----------------|
| Sykkel | Høy (historisk) | Moderat – kjedelig å bare sykle, men vet hvordan man trener |
| Løp | Middels (mindre volum nylig) | Høy – liker løping |
| Svøm | Lav (seriøs svøm) | Må bygges – sannsynlig svakeste triatlonben |

### Treningsmessig utgangspunkt (vurdering)

**Ikke nybegynner mentalt eller teknisk på sykkel**, men **MSK og belastningstoleranse må bygges opp igjen** som etter lang pause. Mulig god «motor» i enkelte systemer samtidig som sener/muskler ikke tåler tenåringsvolum.

### Prioriteringer (rekkefølge — ikke omorganiser uten eksplisitt avvik)

1. Kontinuitet  
2. Skadefrihet  
3. Gradvis progresjon  
4. Aerob kapasitet  
5. Spesifisitet mot Lofoten  
6. Prestasjon  
7. Optimalisering  

## Historikk og volum

| Periode | Nøkkeltall | Notater |
|---------|------------|---------|
| 2019 (peak år) | **~1050 t** trening | Høyt strukturert volum |
| 2019 (test) | **FTP 410 W** (rulle innendørs) | Peak FTP-referanse — **ikke** dagens FTP |
| 2019 | **5 sek peak ~1300 W** | Neuromuskulær kapasitet historisk |
| 2026 hittil | **>50 t** trening | Re-etablering etter lang lav periode |
| Neste 12 mnd (mål) | **750–800 t** totalt | Se volumplan under — ikke lineær jump fra lav uke til snitt |

**Planleggingsimplikasjon:** Bruk **konservativ nå-FTP** til soner er re-testet (2026). Historisk 410 W er motivasjon og tak på potensial, ikke intensitetsgrunnlag før ny test.

### Volummål 12 måneder (750–800 t)

| | |
|---|---|
| **Årsmål** | 750–800 timer over rullerende 12 måneder |
| **Snitt ved jevn fordeling** | ~14,5–15,5 t/uke (750÷52 ≈ 14,4; 800÷52 ≈ 15,4) |
| **Sammenligning 2019** | ~1050 t (~20 t/uke) — 750–800 er lavere enn peak-år, fornuftig med MSK-oppbygging |
| **Hvordan nå målet** | Trapp opp uketimer over måneder (prioritet 3); recovery-uker; tri-fordeling — ikke maks sykkel bare fordi historikken er sykkel |

Agenten skal **planlegge faser** (f.eks. start der William er nå → stabil base → gradvis mot ~15 t/uke snitt), ikke fordele 750 t likt fra uke 1 hvis nåværende belastning er lavere.

## Praktisk treningsoppsett (utfyll)

| Felt | Verdi |
|------|--------|
| Typisk uke (timer) | **Mål-snitt ~14,5–15,5 t** på 12 mnd; nåværende uke TBD inntil kalender er satt |
| Treningsdager | Alle dager (7/7); uke 4 recovery med kortere økter |
| Planstart | **28.09.2026** — se `plans/2026-09-28-uke-01.md` |
| Innendørs / utendørs | Trondheim — vinter innendørs sykkel sannsynlig del av året |
| Utstyr | TBD (powermeter, smart trainer, pulsbelte) |

## Nåværende benchmarks (2026)

| Metrikk | Verdi | Dato | Notater |
|---------|--------|------|---------|
| FTP (W) | TBD — re-test | | Ikke planlegg intervaller fra 2019-tall |
| Threshold HR sykkel (bpm) | TBD | | |
| LTHR løp (bpm) | TBD | | |
| CSS svøm (per 100 m) | TBD | | Svakeste ben — prioritér frekvens og teknikk |
| Vekt (kg) | ~89 | | |

## Intensitetssoner løp (TrainingPeaks)

Sett i TP under **Zones → Run** når testet. Repo-økter bruker primært **% threshold pace** eller **% LTHR**.

| Sone | Navn | % LTHR (mal) | % threshold pace (mal) |
|------|------|--------------|-------------------------|
| Z1 | Recovery | &lt; 81% | &gt; 15s saktere enn terskel/km |
| Z2 | Easy / endurance | 81–89% | 6–15s saktere |
| Z3 | Tempo | 90–93% | 3–6s saktere |
| Z4 | Threshold | 94–99% | 0–3s fra terskel |
| Z5 | VO2 / hard | 100–106% | terskel til ~10s raskere |

**Threshold pace (min/km):** TBD  
**LTHR (bpm):** TBD  

Strukturert løp: Workout Builder med **% Threshold Pace** eller **% LTHR** — ikke watt. Se `docs/trainingpeaks/intensitet-svom-lop.md`.

## Intensitetssoner svøm (TrainingPeaks)

Sett **threshold swim pace** i TP = CSS / snitt per 100 m fra 1000 m test.

| Sone | Navn | % av T-pace (mal) |
|------|------|-------------------|
| WU / recovery | Lett | 89–90% |
| Aerob | Endurance | 92–94% |
| Tempo | | 95–98% |
| Threshold / CSS | | 99–106% |
| Hard | VO2-lignende | 106%+ |

**CSS / T-pace (per 100 m):** TBD  

Svøm: **distanse eller varighet** + **% threshold pace** i Builder; pause = recover-blokk. Se `docs/trainingpeaks/intensitet-svom-lop.md`.

## Intensitetssoner sykkel (power)

Fyll inn når FTP 2026 er kjent. Tabell under er **mal** (% av gjeldende FTP):

| Sone | Navn | % FTP |
|------|------|-------|
| Z1 | Restitusjon | &lt; 55% |
| Z2 | Utholdenhet | 56–75% |
| Z3 | Tempo | 76–90% |
| Z4 | Threshold | 91–105% |
| Z5 | VO2 | 106–120% |
| Z6 | Anaerob | &gt; 120% |

## Begrensninger

- **Skader / plager:** TBD
- **Regler:** Gradvis opptrapping; unngå tenåringsvolum på dekadent MSK-grunnlag (se utgangspunkt over)
- **Motivasjon:** Varier sykkel med løp der det gir mening; ikke «bare sykkel»-blokker uten mening for William

## Coaching notes (for agenten)

- **Coach-navn i Cursor:** Ole (William ønsker dette navnet på agenten).
- Erfaren syklist — forstår TSS, CTL, intervaller og periodisering; trenger ikke grunnleggende forklaring på sykkel.
- **Løp:** høy motivasjon — bruk det for kontinuitet og skadefri progresjon (viktigste prioritet 1–3).
- **Svøm:** lav erfaring — korte, hyppige økter beats hero-sessions; teknikk og vane.
- **Xtri / Lofoten:** se `goals.md` — ikke trene som for full Norseman ennå.
- TrainingPeaks: importer plan via **TrainingDojo** + `plans/csv/trainingdojo-4uker-2026-09-28.csv` (se `docs/trainingpeaks/importere-plan-norsk.md`).

## Datakilder

- TrainingPeaks — kalender og analyse
- Annet: TBD (Strava, Garmin, …)
