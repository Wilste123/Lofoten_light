# Importere plan og økter til TrainingPeaks (William)

TrainingPeaks har **ikke** bulk-import for vanlige utøvere. To realistiske veier:

1. **TrainingDojo** (anbefalt) — last opp CSV → planleggingsøkter på kalenderen  
2. **Manuelt + ZWO** — sykkel med struktur; svøm/løp/styrke som tekst i kalenderen  

---

## A. Hele 4-ukersplanen på én gang (TrainingDojo)

### 1. Forbered fil

Bruk ferdig fil (TrainingDojo-format):

`plans/csv/trainingdojo-4uker-2026-09-28.csv`

Kolonner: `day`, `sport`, `subtype`, `title`, `duration_minutes`, `tss`, `description`, `phase`  
- `day` = 1 på **28.09.2026**, 2 = 29.09, … 28 = 25.10.2026  

### 2. TrainingPeaks-token

TrainingDojo trenger **ditt** TP bearer token (samme type tilgang som nettleseren — behandle som passord).

- TrainingDojo har egen guide for hvordan du henter token (søk «TrainingDojo bearer token» på [trainingdojo.app](https://trainingdojo.app)).  
- Lim inn på [trainingdojo.app/import](https://trainingdojo.app/import)  
- Velg **TrainingPeaks** som plattform  

**Sikkerhet:** ikke del token i chat/git; roter hvis det lekker.

### 3. Import

1. Last opp `trainingdojo-4uker-2026-09-28.csv`  
2. **Plan start date:** `2026-09-28`  
3. Forhåndsvis — sjekk datoer, sport, varighet, beskrivelse  
4. **Import to TrainingPeaks**  
5. Oppdater kalenderen i TP (nett/app)  

### 4. Etter import

- **Sykkel med watt:** TrainingDojo gir **ikke** power-trinn. Bruk **hybrid** (anbefalt):
  1. Importer `trainingdojo-4uker-uten-sykkel.csv` til TrainingDojo **eller** slett sykkeløkter fra full import  
  2. Følg **[sykkel-watt-zwo.md](sykkel-watt-zwo.md)** + `plans/csv/sykkel-zwo-kalender-4uker.csv`  
  3. ZWO fra `workouts/zwo/bike/` → TP Workout Library → dra på kalenderdag  
- **Styrke:** TP viser ofte som «Other» / styrke — detaljer står i `description`.  
- **TSS** i CSV er estimat; juster i TP når du har FTP i profile.

### 5. Neste blokk (uke 5+)

- Be agent om ny CSV i samme format, eller kopier malen `trainingdojo-4uker-2026-09-28.csv`.  
- **Ikke** importer samme dager to ganger uten å slette gamle planlagte økter først.

---

## B. Sykkel med struktur (ZWO)

For økter med watt-trinn (B01, B02, B03, …):

Filer ligger ferdig i `workouts/zwo/` (sykkel: `zwo/bike/*.zwo`). Pakk alt: `./scripts/zip_zwo_library.sh`.

**TrainingPeaks (varierer med abonnement/versjon):**

1. **Workout Library** → Import / Upload workout (hvis tilgjengelig) → velg `.zwo`  
2. Dra fra biblioteket til kalenderdag  
3. Alternativ: kjør i **Zwift** (importer workout) → fullfør → sync Garmin/Wahoo → TP  

Svøm/løp/styrke: **ikke** ZWO-import — bruk TrainingDojo-CSV (beskrivelse på kalender) eller `workouts/planned/**/*.txt`. Les [zwo-kun-sykkel.md](zwo-kun-sykkel.md).

---

## C. Enkeltøkter manuelt (uten TrainingDojo)

1. TP → **Calendar** → klikk dag → **Create Workout**  
2. Velg sport (Swim / Bike / Run / Other)  
3. Importer `.zwo` fra `workouts/zwo/` eller lim inn beskrivelse fra `workouts/index.md`  
4. Sett varighet og planlagt TSS  

Bra for å rette enkeltdager; tungt for 28 dager.

---

## D. Grov 12-månedersplan (`12mnd-periodisering.csv`)

Denne filen er **ikke** en kalender-import — det er oversikt (fase, t/uke, milepæler).

- Bruk i Excel som veikart  
- Legg **ikke** forventning om at TrainingDojo importerer den som 365 dager  
- Når hver måned nærmer seg: lag ny **uke-CSV** (som 4-ukersfilen) og importer blokker

---

## E. Fullførte økter (etter trening)

Plan import = **planlagte** økter. Når du er ferdig:

- Klokke / Garmin / Wahoo → synk til TP, **eller**  
- Upload `.fit` / `.tcx` på aktiviteten  

Plan og logg matcher da automatisk hvis dato/tittel stemmer.

---

## Feilsøking

| Problem | Løsning |
|---------|---------|
| Token ugyldig | Hent nytt token; logg inn TP på nytt |
| Feil sport | Endre `bike`/`run`/`swim` i CSV (små bokstaver ok i TrainingDojo) |
| Doble økter | Slett planlagte i TP før re-import |
| Sykkel uten watt-steg | Last opp ZWO eller bygg i builder |
| 12-mnd CSV importerer ikke | Bruk kun `trainingdojo-4uker-*.csv` for kalender |

---

## Filer i repo

| Fil | Bruk |
|-----|------|
| `plans/csv/trainingdojo-4uker-2026-09-28.csv` | **TrainingDojo → TP** |
| `plans/csv/ukeplan-2026-09-28-4uker.csv` | Excel / arkivering |
| `plans/csv/12mnd-periodisering.csv` | Grovplan Excel |
| `workouts/zwo/bike/` · `zwo-bike.zip` | Sykkel (ZWO → TP library) |
| `workouts/planned/` · `planned-all.zip` | Svøm/løp/styrke (kalender) |

Mer bakgrunn: [import-workouts.md](import-workouts.md) · [api.md](api.md)
