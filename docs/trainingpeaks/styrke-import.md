# Styrke i TrainingPeaks — import (ikke ZWO)

TrainingPeaks har **ikke** filimport for styrke på samme måte som sykkel-ZWO.

Kilder: [Strength Workout Builder FAQs](https://help.trainingpeaks.com/hc/en-us/articles/23361947242381-Strength-Workout-Builder-FAQs) · [Logging strength](https://help.trainingpeaks.com/hc/en-us/articles/23969404961421-Logging-your-Strength-Training-Session)

## Hva som fungerer

| Metode | Hvem | Resultat |
|--------|------|----------|
| **TrainingDojo + CSV** | Alle | Planlagt styrke på **kalender** med tittel, varighet, tekstbeskrivelse (`sport=strength`) |
| **Strength Builder** (desktop, Premium) | Premium utøver / coach | Strukturert økt med øvelser, sett, reps, video — lagres i **Workout Library** |
| **Mobilapp** | Basic kan **kjøre** coach-plan; Premium kan planlegge eget | Start økt → logg sett |
| **ZWO / FIT import** | — | **Nei** — ikke for planlagt styrke |
| **Eksport til Garmin** | — | **Nei** (per TP i dag) |

Repo-filer: `workouts/planned/strength/ST01-base.txt` osv. + `workouts/strength/trainingpeaks/` (sjekkliste for Builder).

## Anbefalt for William (uke 1–4)

1. Importer `plans/csv/trainingdojo-4uker-2026-09-28.csv` — torsdager med **Styrke A / recovery** er allerede med.
2. Når du vil ha **sett/reps i appen**: bygg ST01 én gang i **Strength Builder** (web) og lagre i biblioteket. Bruk `workouts/strength/trainingpeaks/ST01-base.md` som sjekkliste.
3. Ikke prøv å importere `.zwo` for styrke — TP avviser eller ignorerer det som sykkel.

## Abonnement

- **Basic:** kan utføre styrkeøkter planlagt av coach/plan på mobil.
- **Premium:** kan bytte og bygge egne styrkeøkter i Strength Builder på desktop.
