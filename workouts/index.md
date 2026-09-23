# Treningsbibliotek — indeks

## Sykkel — ZWO (`zwo/bike/`) → TrainingPeaks Library import

| Fil | Beskrivelse |
|-----|-------------|
| `endurance-90.zwo` | ~90 min Z2 |
| `endurance-120.zwo` | ~120 min Z2 |
| `endurance-180.zwo` | ~3 t Z2 |
| `endurance-300.zwo` | Lang Z2 |
| `recovery-spin-45.zwo` | Recovery |
| `tempo-3x10.zwo` | 3×10 tempo |
| `sweet-spot-2x20.zwo` | 2×20 sweet spot |
| `sweet-spot-3x15.zwo` | 3×15 sweet spot |
| `threshold-2x20.zwo` | 2×20 terskel |
| `threshold-5x10.zwo` | 5×10 terskel |
| `threshold-4x12.zwo` | 4×12 terskel |
| `over-under-3x12.zwo` | Over/under |
| `vo2-5x3.zwo` | 5×3 VO2 |
| `vo2-30-30-x10.zwo` | 30/30 |
| `progressive-long-240.zwo` | 4 t progressiv |
| `race-surges-long-270.zwo` | Race surges |

Brick sykkel (samme import): `zwo/brick/BR01-bike-90.zwo`, `BR02-bike-180.zwo`, `BR03-bike-240.zwo`

## Svøm — planned (`planned/swim/*.txt`) → TP: **% threshold swim pace** (CSS), ikke watt

Se [intensitet-svom-lop.md](../docs/trainingpeaks/intensitet-svom-lop.md).

S01 … S09 — filnavn `S01-teknikk-a.txt` osv.

## Løp — planned (`planned/run/*.txt`) → TP: **% threshold pace** eller **% LTHR**

R01 … R13 — f.eks. `R01-easy-40.txt`, `R11-6x8-threshold.txt`

## Styrke — planned (`planned/strength/*.txt`)

ST01-base, ST02-build, ST03-recovery

## Brick løp — planned (`planned/brick/`)

BR01-run-20, BR02-run-35, BR03-run-60 (etter tilhørende sykkel-ZWO)

## Første 4 uker

| Økt | Fil |
|-----|-----|
| Sykkel Z2 90 | `zwo/bike/endurance-90.zwo` |
| Svøm teknikk | `planned/swim/S01-teknikk-a.txt` + TrainingDojo rad |
| Løp easy | `planned/run/R01-easy-40.txt` + TrainingDojo rad |

Se [docs/trainingpeaks/zwo-kun-sykkel.md](../docs/trainingpeaks/zwo-kun-sykkel.md) hvis ZWO-import feiler for svøm/løp.
