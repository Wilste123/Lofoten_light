# Treningsbibliotek

TrainingPeaks **importerer bare kraftbaserte sykkeløkter** som `.zwo`. Svøm, løp og styrke ligger som **planfiler** (`.txt`) for kalender / Workout Builder — ikke ZWO.

| Mappe | TP Workout Library import? | Innhold |
|-------|----------------------------|---------|
| `zwo/bike/` | **Ja** | Sykkel med watt (% FTP) |
| `zwo/brick/BR*-bike-*.zwo` | **Ja** | Sykkeldel av brick |
| `planned/swim/` | Nei — bruk TrainingDojo eller kalender | Steg + varighet |
| `planned/run/` | Nei | Steg + varighet |
| `planned/strength/` | Nei | Steg + varighet |
| `planned/brick/` | Nei (løp etter sykkel) | Løpedel av brick |

**Oversikt:** [index.md](index.md)  
**TP-feilmelding om ZWO:** [docs/trainingpeaks/zwo-kun-sykkel.md](../docs/trainingpeaks/zwo-kun-sykkel.md)

## Sykkel (ZWO)

Workout Library → Import → filer fra `zwo/bike/`.

## Svøm / løp / styrke

1. **Enklest:** `plans/csv/trainingdojo-4uker-2026-09-28.csv` → TrainingDojo → TrainingPeaks kalender.  
2. **Detaljer:** åpne `planned/<sport>/<id>.txt` og lim steg inn i økten, eller bygg i Workout Builder.

## Pakker

```bash
./scripts/zip_zwo_library.sh      # kun sykkel + brick-sykkel .zwo
./scripts/zip_planned_library.sh  # swim/run/strength/brick løp .txt
```

## Regenerere

```bash
python3 scripts/build_zwo_library.py
```

Sykkel-`.zwo` i `zwo/bike/` beholdes; `planned/` genereres på nytt.
