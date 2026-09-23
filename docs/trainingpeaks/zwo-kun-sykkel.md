# TrainingPeaks: ZWO-import (løp og svøm som sykkel-format)

TP avviser `.zwo` med `sportType` run/swim. Løp og svøm i dette repoet er derfor **power-based cycling ZWO** (samme format som sykkel) med prefiks **RUN** / **SWIM**.

Steg-for-steg: [importer-lop-svom-zwo.md](importer-lop-svom-zwo.md)

| Idrett | Filer | Import |
|--------|-------|--------|
| Sykkel | `workouts/zwo/bike/*.zwo` | Library → Import |
| Løp | `workouts/zwo/run/*.zwo` | Samme import, deretter sport → **Run** + % threshold pace |
| Svøm | `workouts/zwo/swim/*.zwo` | Samme import, deretter sport → **Swim** + % T-pace |
| Styrke | ikke ZWO | [styrke-import.md](styrke-import.md) |
