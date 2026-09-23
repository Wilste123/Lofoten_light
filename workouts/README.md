# Treningsbibliotek

## Løp og svøm — kun `.zwo` (norsk)

`workouts/zwo/run/` og `workouts/zwo/swim/` — importer til TrainingPeaks Library som sykkel-ZWO, deretter bytt sport i Builder. Ingen `.txt` eller `.fit` for disse idrettene.

## Sykkel

`workouts/zwo/bike/` — watt fra **FTP** i TP.

## Styrke

`workouts/planned/strength/*.txt` + [styrke-import.md](../docs/trainingpeaks/styrke-import.md) — **ikke** ZWO/FIT.

```bash
python3 scripts/build_zwo_library.py
./scripts/zip_zwo_library.sh
```
