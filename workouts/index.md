# Treningsbibliotek — indeks

**Katalog (alle ID-er):** [`catalog.md`](catalog.md)  
**Full økttekst:** [`sessions/`](sessions/) (swim, run, bike, strength)  
**Analyse:** [`docs/workouts/bibliotek-analyse.md`](../docs/workouts/bibliotek-analyse.md)

## Sykkel — `zwo/bike/` (TP-import, % FTP)

Re-etab: **B01–B03** · Base: **B04, B06–B07, B14** · Build: **B08–B11, B15–B16** · Lang/spec: **B05, B12–B13** · Test: **B17** (`ftp-ramp-test.zwo`)

## Svøm — `zwo/swim/`

S01–S10 (inkl. **S03b** Plan B, **S10** pust)

## Løp — `zwo/run/`

R01–R14 (inkl. **R14** recovery 30 min)

## Brick — `zwo/brick/`

Sykkel: `BR*-bike-*.zwo` · Løp: `BR*-run-*.zwo`

## Styrke — `planned/strength/*.txt`

ST01-base, ST02-build, ST03-recovery — [styrke-import.md](../docs/trainingpeaks/styrke-import.md) · [sessions/strength.md](sessions/strength.md)

## Guider

- [importer-lop-svom-zwo.md](../docs/trainingpeaks/importer-lop-svom-zwo.md)
- [ftp-og-zwo.md](../docs/trainingpeaks/ftp-og-zwo.md)
- [zwo-kun-sykkel.md](../docs/trainingpeaks/zwo-kun-sykkel.md)

```bash
python3 scripts/build_zwo_library.py
./scripts/zip_zwo_library.sh
```
