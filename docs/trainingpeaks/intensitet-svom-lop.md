# Svøm og løp i TrainingPeaks — hva du bruker i stedet for watt

Sykkel i TP kan være **% FTP (watt)** og importeres som **.zwo**. Svøm og løp bruker **andre intensitetsmodeller** i **Structured Workout Builder** — ikke power, og ikke ZWO-import.

Kilde: [Structured Workout Builder](https://help.trainingpeaks.com/hc/en-us/articles/235164967-Structured-Workout-Builder) · [Structured Swim FAQ](https://help.trainingpeaks.com/hc/en-us/articles/9121983425421-Structured-Swim-Workouts-FAQ) · [Export/sync](https://help.trainingpeaks.com/hc/en-us/articles/115000325647-Structured-Workout-sync-and-Manual-Export)

---

## Oversikt

| Idrett | Primær anbefaling (strukturert) | Alternativ | Ikke bruk |
|--------|----------------------------------|------------|-----------|
| **Løp** | **% Threshold Pace** (når du har løpsterskel-pace) | **% LTHR** (laktat-/terskelpuls) | % FTP, ZWO-import |
| **Svøm** | **% Threshold Pace** (T-pace / CSS som terskel i TP) | **RPE** på teknikkøkter | Watt, ZWO-import |
| **Styrke** | Varighet + beskrivelse (sport **Other**) | RPE per blokk | Strukturert watt |

**RPE (0–10)** fungerer i Builder for alle idretter, men synk til klokke er begrenset (TP: RPE-workouts støttes ikke overalt på enheter). Bruk RPE når du **mangler tester**, eller som tekst i tillegg til pace/HR.

---

## Løp — sett dette i TP først

1. **Settings → Zones → Run**
2. Fyll inn minst én av:
   - **Threshold pace** (f.eks. fra 30 min TT, 5 km race, eller Cooper-estimat) — **anbefalt for intervaller**
   - **LTHR** (løpsterskelpuls) — bra for easy og trail når pace varierer
3. I Workout Builder: velg intensitet **% Threshold Pace** eller **% Threshold Heart Rate**

### Typisk mapping (repo-økter → TP)

| Økttype (repo) | TP-intensitet | Ca. sone |
|----------------|---------------|----------|
| Easy / long (R01–R05, R10) | % LTHR **80–89%** eller pace **Z2** | Samtale |
| Tempo (R06) | % threshold pace **88–94%** eller LTHR Z3 | Kontrollert hard |
| 5×1k, fartlek, hills (R07–R09) | % threshold pace **102–115%** eller RPE 7–9 | VO2 / hard |
| Threshold cruise (R11–R13) | % threshold pace **95–105%** | Terskel |
| Recovery (korte easy) | LTHR Z1 eller RPE 3–4 | |

`workouts/planned/run/*.txt` har linjen `tp_intensity:` og per-steg `tp_target:` for Builder.

### Klokke (Garmin m.m.)

Bygg økten i TP → legg på kalender → synk. Pace/HR-økter eksporteres ofte som **.fit** (ikke .zwo). Aktiver TrainingPeaks-kalender i Garmin Connect.

---

## Svøm — sett dette i TP først

1. **CSS / terskel:** Gjør **1000 m (eller 400+200+200) test** → gjennomsnittlig pace per 100 = **threshold swim pace** (samme idé som CSS).
2. I TP: **Settings → Zones → Swim** → sett **threshold pace** (per 100 m eller 100 yd — vær konsekvent med basseng).
3. **Equipment:** riktig **bassenglengde** på planlagt svøm (25 m vs 50 m) — ellers feil distanse på klokke ([Swim FAQ](https://help.trainingpeaks.com/hc/en-us/articles/9121983425421-Structured-Swim-Workouts-FAQ)).

### Intensitet på sett

| Økttype (repo) | TP-intensitet | Ca. % av T-pace |
|----------------|---------------|-----------------|
| Teknikk (S01–S02) | RPE eller lav % T-pace | 89–92% |
| Aerob (S03–S04) | % threshold pace | 92–94% (endurance) |
| CSS-sett (S05–S06) | % threshold pace på reps | ~100% (+ pause) |
| Race sim (S07) | % threshold pace kontinuerlig | 99–106% |
| Recovery (S09) | Lav % T-pace eller RPE 2–4 | 89–90% |

**Pause:** legg inn **duration**-blokk, type **Recover**, target pace **0** (offisiell TP-metode for svøm-pause).

**Drill:** TP har ikke eget drill-steg — bruk **tittel på steget** (f.eks. «catch-up drill»).

Strukturerte svømøkter sync til **Pool Swim / Lap Swim** på Garmin/Suunto/Wahoo — ikke åpent vann i samme modus.

---

## Praktisk workflow (anbefalt)

### A — Kalender uten struktur (rask start)

**TrainingDojo** + `plans/csv/trainingdojo-4uker-2026-09-28.csv` → svøm/løp med beskrivelse. Intensitet står i tekst (RPE). Ingen klokke-steg.

### B — Strukturert (klokke / graf i TP)

1. Åpne `workouts/planned/<sport>/<fil>.txt`
2. Calendar → **Build** (Workout Builder)
3. Velg sport **Run** eller **Swim**
4. Velg intensitetstype som i filen (`tp_intensity:`)
5. Dra inn **Warm up / Active / Rest / Cool down** — sett varighet eller **distanse** (svøm)
6. Sett **zone** eller **% threshold pace** per steg (`tp_target:`)
7. **Save to library** → gjenbruk senere

Tips: TP kan generere struktur fra tekst, f.eks.  
`20min warmup, 6x8min @ threshold w/ 2min recovery, 12min cooldown`  
(se [Workout Builder intro](https://www.trainingpeaks.com/learn/articles/introducing-trainingpeaks-workout-builder/)).

### C — Sykkel fortsatt ZWO

`workouts/zwo/bike/` — uendret. Se [zwo-kun-sykkel.md](zwo-kun-sykkel.md).

---

## William — fyll inn i `docs/athlete/profile.md`

Uten disse tallene: bruk **RPE** i Builder og tekst i TrainingDojo. Når testet:

- **Løp threshold pace** (min/km)
- **LTHR** (bpm)
- **Svøm T-pace / CSS** (sek per 100 m)

Da kan alle `tp_target`-linjer i `planned/` oversettes automatisk til watt-lignende presisjon — med **pace eller puls**, ikke watt.
