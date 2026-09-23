# Sykkel med watt i TrainingPeaks (ZWO fra repoet)

TrainingDojo-CSV legger sykkel på kalenderen som **tekst + varighet**, ikke watt-trinn. For **% FTP / watt på rulle, Garmin eller Wahoo** bruker du **.zwo** fra dette repoet.

Offisiell TP-hjelp: [Import Planned Workouts (.zwo)](https://help.trainingpeaks.com/hc/en-us/articles/32432105650573-Import-Planned-Workouts-into-TrainingPeaks)

---

## Steg 0 — FTP i TrainingPeaks (obligatorisk)

Uten riktig FTP blir ZWO feil watt.

1. TP → **Settings** → **Zones** → **FTP** (sykkel)  
2. Legg inn **nåværende FTP** (etter test — ikke 410 W fra 2019)  
3. Oppdater også `docs/athlete/profile.md`  

Alle filer i `workouts/bike/*.yaml` bruker **% FTP** — TP regner om til watt.

---

## Steg 1 — Generer ZWO lokalt

```bash
cd <repo>
./scripts/export_all_zwo.sh
```

Eller en fil:

```bash
python3 scripts/export_zwo.py workouts/bike/endurance-90.yaml
```

Output: `workouts/generated/*.zwo`

---

## Steg 2 — Importer til Workout Library (bulk)

1. TP → **Library** → **Workout Library** (egen mappe, f.eks. «Lofoten coach»)  
2. Klikk **⋮** på mappen → **Import Workout**  
3. Velg alle relevante `.zwo` (minst for startblokken):
   - `endurance-90.zwo`
   - `endurance-120.zwo`
   - `recovery-45.zwo`
4. **Open** — TP konverterer til strukturerte trinn med power  

Du trenger ikke importere alle 15 filer med én gang — start med de tre over.

---

## Steg 3 — Legg strukturert økt på kalender (watt)

For hver sykkeldag i planen:

1. **Calendar** → riktig dato  
2. Dra økt fra **Library** inn på dagen **eller** Create Workout → velg fra library  
3. Sjekk i **Workout Builder** at trinn viser **% FTP / watt**  

**Kalender for dine første 4 uker:** se `plans/csv/sykkel-zwo-kalender-4uker.csv`

| Dato | ZWO-fil |
|------|---------|
| 2026-09-30 | endurance-90.zwo |
| 2026-10-03 | recovery-45.zwo |
| 2026-10-07 | endurance-90.zwo |
| 2026-10-10 | endurance-120.zwo |
| … | (full liste i CSV) |

### Unngå doble sykkeløkter

Hvis du allerede importerte **hele** TrainingDojo-CSV (inkl. sykkel):

- **Slett** den planlagte «tekst»-sykkeløkten den dagen  
- Legg inn **strukturert** økt fra library (ZWO) i stedet  

**Alternativ:** importer `trainingdojo-4uker-uten-sykkel.csv` (kun svøm/løp/styrke) + ZWO på sykkeldager.

---

## Steg 4 — Kjør økten med watt

| Platform | Hvordan |
|----------|---------|
| **Zwift** | Importer `.zwo` til Zwift Custom Workouts → kjør → aktivitet til Garmin/TP |
| **TrainerRoad** | Ofte enklere å bygge/kopiere; ZWO kan importeres der også |
| **Wahoo / Garmin** | Planlagt strukturert økt fra TP-kalender → **sync** til sykkelcomputer (krever kompatibel enhet + TP-kobling) |
| **Rulle + app** | Zwift, TrainerRoad, Rouvy, etc. med ZWO/ERG |

TP-hjelp: [Structured Workout sync](https://help.trainingpeaks.com/hc/en-us/articles/115000325647-Structured-Workout-sync-and-Manual-Export)

Etter kjøring: fullført aktivitet med power synker til TP og matcher (eller erstatter) planlagt økt.

---

## Senere: threshold / 5×10 osv.

Når du er i build-fase:

```bash
python3 scripts/export_zwo.py workouts/bike/threshold-5x10.yaml
python3 scripts/export_zwo.py workouts/bike/sweet-spot-2x20.yaml
```

Importer nye `.zwo` til library → planlegg på kalender.

---

## Svøm og løp — «struktur» i TP

- **Svøm:** TP Structured Swim (avhengig av abonnement) — ellers beskrivelse fra `workouts/swim/*.md`  
- **Løp:** Workout Builder med **pace eller HR**, ikke watt — bruk tekst fra `workouts/run/*.md`  

TrainingDojo er fortsatt best for **å fylle kalenderen** på svøm/løp/styrke.

---

## Sjekkliste første gang

- [ ] FTP satt i TP  
- [ ] `./scripts/export_all_zwo.sh` kjørt  
- [ ] ZWO importert til library  
- [ ] Sykkeldager fra `sykkel-zwo-kalender-4uker.csv` lagt på kalender  
- [ ] TrainingDojo for resten (eller full CSV minus sykkel)  
- [ ] Én testøkt på rulle — watt matcher forventning (~68 % FTP på B02)
