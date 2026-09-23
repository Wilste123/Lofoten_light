# Sykkel-ZWO og FTP i TrainingPeaks

Alle sykkeløkter i `workouts/zwo/bike/` bruker **`Power="0.xxxx"` = andel av FTP** (f.eks. `0.68` = 68 % FTP). Det står **ingen faste watt** i filene.

## Slik får øktene riktig watt for deg

1. **TrainingPeaks** → **Settings** → **Zones** → **FTP** (sykkel)  
2. Legg inn **din nåværende FTP** (W).  
3. **Workout Library** → Import → velg `.zwo` fra `workouts/zwo/bike/`.  
4. Når du legger økten på kalenderen, regner TP om hvert steg til watt:  
   **watt = ftp_fraction × FTP** (f.eks. 0,98 × 280 W ≈ 274 W).

Oppdaterer du FTP i TP senere, gjenbruker du **samme bibliotek-økter** — målene justeres automatisk (dynamiske soner).

Oppdater også `docs/athlete/profile.md` med samme FTP for agenten.

## Regenerere ZWO fra repo

Kilde: `workouts/bike/manifest.json` (% FTP per steg).

```bash
python3 scripts/export_bike_zwo.py
./scripts/zip_zwo_library.sh
```

## Svøm og løp

**Kan ikke** importeres som ZWO i TP (kun kraft-sykkel). Bruk `workouts/planned/` + pace/puls — se [intensitet-svom-lop.md](intensitet-svom-lop.md).

## Zwift / annet

Samme `.zwo`-filer bruker vanligvis **FTP satt i Zwift** (eller koblet til TP) på samme måte — ikke hardkodede watt i filen.
