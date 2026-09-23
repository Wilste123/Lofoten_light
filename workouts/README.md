# Øktbibliotek

Strukturerte økter for William (Half Extreme 2027). **Sykkel** = YAML → ZWO. **Svøm, løp, styrke, brick** = markdown med YAML frontmatter (TrainingPeaks-beskrivelse / TrainingDojo).

## Katalog

Se **[index.md](index.md)** — søkbar oversikt med fase, varighet og formål.

## Sykkel (YAML → ZWO eller FIT)

TrainingPeaks: **ZWO** (prosent FTP). Garmin/Wahoo: **FIT** (krever `--ftp` watt).

```bash
pip install -r scripts/requirements.txt
./scripts/export_all_zwo.sh
export FTP=280 && ./scripts/export_all_fit.sh
python3 scripts/export_fit.py workouts/bike/endurance-90.yaml --ftp 280
```

Se [docs/trainingpeaks/fit-vs-zwo.md](../docs/trainingpeaks/fit-vs-zwo.md).

Felter:

| Felt | Beskrivelse |
|------|-------------|
| `sport` | `bike` |
| `phase` | `re-etablering`, `base`, `build`, `spesifikk`, `recovery` |
| `duration_min` | Ca. total |
| `tss_estimate` | Veiledende (krever riktig FTP i TP) |
| `steps` | `duration_min`, `power_pct_ftp`, `note` |

## Svøm / løp / styrke / brick (Markdown)

Filen starter med frontmatter (`---`). Resten er **coach-tekst** du limer i TP eller TrainingDojo `description`.

Importer til kalender: agent eller `docs/trainingpeaks/import-workouts.md`.

## Fase-veiledning

| Fase | Sykkel | Svøm | Løp |
|------|--------|------|-----|
| Re-etablering | recovery, endurance 60–90 | teknikk, aerob kort | easy, strides |
| Base | endurance 120–180, SS | aerob, CSS intro | long easy, tempo lett |
| Build | SS, THR, VO2, lang 240+ | CSS, 1500+ | intervaller, bakke |
| Spesifikk | race sim, surges | 1900, OWS | brick-løp, terreng |

## Soner

Bruk **gjeldende FTP / CSS / LTHR** fra `docs/athlete/profile.md` — ikke 2019-FTP.
