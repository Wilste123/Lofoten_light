# TrainingPeaks: ZWO er kun sykkel (watt)

Hvis du får:

> *We cannot process your workout. We currently only support power based cycling workouts in ZWO format.*

…så prøver du å importere **svøm, løp eller styrke** som `.zwo`. Det støttes ikke i TrainingPeaks.

Offisiell TP-hjelp: [Import Planned Workouts (.zwo)](https://help.trainingpeaks.com/hc/en-us/articles/32432105650573-Import-Planned-Workouts-into-TrainingPeaks) — **kun `.zwo`**, og i praksis **kun kraftbasert sykkel**.

## Hva du skal bruke

| Idrett | Repo | Slik får du det inn i TP |
|--------|------|---------------------------|
| **Sykkel** | `workouts/zwo/bike/*.zwo` | Workout Library → **Import Workout** → velg `.zwo` |
| **Brick (sykkeldel)** | `workouts/zwo/brick/BR*-bike-*.zwo` | Samme som sykkel |
| **Svøm / løp / styrke / løp etter brick** | `workouts/planned/<sport>/*.txt` | **TrainingDojo**-CSV (plan på kalender) **eller** manuelt: Calendar → Create Workout → lim inn steg fra `.txt` / Workout Builder |

## Anbefalt flyt for de første 4 ukene

1. Importer `plans/csv/trainingdojo-4uker-2026-09-28.csv` via [TrainingDojo](https://trainingdojo.app/import) (start **2026-09-28**) — da får svøm/løp/styrke **tittel, varighet og beskrivelse** på kalenderen.
2. Importer sykkel-`.zwo` fra `workouts/zwo/bike/` til biblioteket og **erstatt** tekst-sykkel på de dagene (eller bruk `trainingdojo-4uker-uten-sykkel.csv` + ZWO på sykkeldager). Se [sykkel-watt-zwo.md](sykkel-watt-zwo.md).

## Strukturert løp/svøm på klokke

Bruk **pace eller puls**, ikke watt: [intensitet-svom-lop.md](intensitet-svom-lop.md).

- **Løp:** % **threshold pace** eller % **LTHR** i Workout Builder  
- **Svøm:** % **threshold swim pace** (CSS/T-pace) + riktig bassenglengde  
- **Eksport til Garmin:** ofte **.fit**, ikke .zwo  

Bygg i TP → lagre i bibliotek → synk kalender. Eller TrainingDojo uten struktur (kun beskrivelse).
