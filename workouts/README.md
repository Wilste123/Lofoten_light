# Treningsbibliotek

## ZWO for TrainingPeaks Library import

Alle `.zwo` er **power-based cycling XML** (`sportType=bike`) — det er det eneste TP Import Workout tar.

| Mappe | Prefiks i navn | Etter import |
|-------|----------------|--------------|
| `zwo/bike/` | (ingen) | La stå som Bike — watt fra **FTP** |
| `zwo/run/` | `RUN …` | Endre sport til **Run** + % threshold pace |
| `zwo/swim/` | `SWIM …` | Endre sport til **Swim** + % T-pace |
| `zwo/brick/` | sykkel + `RUN …` | Sykkel som bike; løp som over |

Guide: [docs/trainingpeaks/importer-lop-svom-zwo.md](../docs/trainingpeaks/importer-lop-svom-zwo.md)

Styrke: **ikke ZWO** — [styrke-import.md](../docs/trainingpeaks/styrke-import.md)

```bash
python3 scripts/build_zwo_library.py
./scripts/zip_zwo_library.sh
```
