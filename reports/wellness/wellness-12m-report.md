# Wellness 12 mnd + best-case prognose

**Kilde:** `wellness-12m.csv` (Intervals.icu wellness.csv)  
**Periode faktisk:** 2025-09-24 → 2026-09-24  
**Prognose:** 2026-09-25 → 2027-09-24  

## Datakvalitet (viktig)

| Metrikk | Dager med data | Merknad |
|---------|----------------|---------|
| CTL/ATL | 366 / 366 | Komplett — belastning fra økter |
| Søvn | 8 / 366 | Mange verdier **>10 t** (sannsynlig Garmin/«time in bed») — filtrert i grafer |
| Vekt | 11 | Svært få punkter — ikke bruk til harde mål |
| Hvilepuls | 21 | Begrenset |
| HRV / readiness | 0 | Ikke synket til Intervals |

**Konklusjon:** Grafer og prognose for søvn/vekt er **best-case antakelser** + det sparse som finnes. For OPV-oppfølging: få Garmin til å fylle Wellness daglig.

## Faktisk (12 mnd)

- **CTL nå:** 1.2 (topp i perioden 26.9)
- **ATL nå:** 0.0
- **Søvn (filtrert ≤10 t):** snitt 8.7 t, median 9.0 t på 8 dager
- **Vekt:** 81.9–84.0 kg (sist 82.8 kg)

## Best-case prognose neste 12 mnd (Half Extreme-grunnmur)

Dette er **ikke** statistisk ML — det er «hvis du gjør det riktige»:

| Område | Best-case mål | Begrunnelse |
|--------|---------------|-------------|
| **CTL** | ~55 ved sep 2027 | Jevn ~14–15 t/uke, skadefri opptrapping (ikke 2019) |
| **Søvn** | 7.8 t/snitt | `knowledge/restitusjon/sovn-stress.md` |
| **Vekt** | 87–90 kg | Vedlikehold styrke + volum |
| **Wellness-logging** | >300 dager/år med sønn+RHR | Nødvendig for OPV justering |

### Risiko hvis data forblir tom

Uten wellness i Intervals coach må fortsatt stole på **dine TP-kommentarer** — CTL alene skjuler dårlig søvn og stress.

## Grafer

- `ctl-atl-12m.png`
- `ctl-forecast-12m.png`
- `sleep-12m-forecast.png`
- `weight-12m-forecast.png`
- `rhr-12m-forecast.png`
