# Importer løp og svøm som ZWO i TrainingPeaks

TrainingPeaks Library-import godtar **bare** `.zwo` som **kraftbasert sykkel** (`sportType=bike` + `Power=` > 0). Derfor er løp- og svøm-filene i `workouts/zwo/run/` og `workouts/zwo/swim/` bygd **identisk med sykkel-ZWO**, med navn `RUN …` / `SWIM …`.

Offisiell begrensning: [Import Planned Workouts (.zwo)](https://help.trainingpeaks.com/hc/en-us/articles/32432105650573-Import-Planned-Workouts-into-TrainingPeaks).

## Import (samme som sykkel)

1. TP → **Library** → **Workout Library** → mappe (f.eks. Lofoten run / Lofoten swim)  
2. **⋮** → **Import Workout**  
3. Velg alle `.zwo` i `workouts/zwo/run/` og/eller `workouts/zwo/swim/`  
4. De lander som **Bike** med %-trinn (det er meningen)

Ikke bruk `sportType=run` / `swim` i filen — da får du: *We currently only support power based cycling workouts in ZWO format.*

## Etter import (gjør strukturen til løp/svøm)

For **hver** økt (eller én mal, deretter dupliser):

1. Åpne økten → **Build** (Workout Builder)  
2. Endre **sport** til **Run** eller **Swim**  
3. Endre intensitet til **% Threshold Pace** (løp) eller **% Threshold Pace** for svøm (T-pace)  
4. TP konverterer de samme %-tallene (f.eks. 78 % easy, 100 % terskel)  
5. **Save** til biblioteket  
6. Sett **run threshold pace** / **swim T-pace** i **Settings → Zones** (ikke bike FTP)

Da følger målene **dine** TP-soner, ikke faste watt.

## FTP vs terskel

- **Sykkel-ZWO** (`zwo/bike/`): `Power` × **bike FTP**  
- **RUN/SWIM-ZWO** (importert som sykkel først): samme XML; etter sport-bytte: `Power` × **threshold pace** for den idretten  

Ikke la løp-økter ligge som Bike på kalenderen — da bruker de **sykkel-FTP** og feil watt.

## Styrke

Styrke har fortsatt **ingen** ZWO-import. Se [styrke-import.md](styrke-import.md).
