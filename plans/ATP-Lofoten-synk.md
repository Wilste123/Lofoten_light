# ATP Lofoten — synk med repo-planer

**Kilde (sannhet for timer/faser):** [`ATP_Lofoten.xlsx`](../ATP_Lofoten.xlsx) (TrainingPeaks Annual Training Plan)  
**Eksportert CSV:** [`plans/csv/atp-lofoten-weekly.csv`](csv/atp-lofoten-weekly.csv) — kjør `python3 scripts/export_atp_lofoten_csv.py` etter ATP-endring  
**Operativ TARGET (Intervals):** [`plans/csv/intervals-weekly-targets-atp-lofoten.csv`](csv/intervals-weekly-targets-atp-lofoten.csv)

**Race:** Half Extreme Lofoten — uke start **2027-08-16** (`Race`, 8,5 t taper-uke i ATP)

---

## Standard uke-mal (sykkel + tri)

Fra arket **Standard Base uke** i ATP (schematic — **timer styres av hoved-ATP**, ikke bare 9–12,5 t i malen):

| Dag | Uke 1 (mal) | Uke 2 (mal) |
|-----|-------------|-------------|
| Man | Svøm teknikk | Svøm |
| Tir | **Sykkel SS/FTP** | **Sykkel SS/FTP** |
| Ons | Svøm + styrke | Svøm |
| Tor | Løp (terskel / 10×1 km) | Løp hardere |
| Fre | Svøm | Sykkel lang Z2 / løp |
| Lør | Løp **6×4** | Løp **6×4** |
| Søn | Sykkel langtur (+ Z2 økt 2) | Sykkel lang Z2 |

**Økt 2:** styrke ons, ekstra sykkel Z2 søn — se Excel-mal.

Repo-Q (FIRDA, S12, ST04) **mapper inn** i denne rammen; detalj i uke-`.md`-filer.

---

## Avvik fra gammel repo-meso (viktig)

| Uke start | Gammel plan | **ATP** |
|-----------|-------------|---------|
| **2026-11-16** | M1 recovery 7,5 t | **Base 1 W3 — 16,0 t** (volumtopp) |
| **2026-11-23** | M2 CSS 10 t | **Base 1 W4 — 8,5 t recovery + FTP** |
| **2026-12-21** | Des-topp 12 t | **Base 2 W4 — 8,5 t recovery + FTP (275 W)** |
| **2027-06-07** | Build 1 ~mai | **Build 1 starter juni** i ATP |
| **2027-04-26** | Leksvik uke 2 | **21,5 t** (ATP «Leksvik-samling») |

**FTP-test uker (X i ATP):** ca. hver **4. uke** i base + Base 1 W1 (nov 2026). Etter **3. nov 2026** (200 W): neste planlagte **2026-11-23**, **2026-12-21** (275 mål).

---

## Meso → ukefiler (nov 2026 – des 2026)

| Week start | ATP periode | Timer | Repo ukefil |
|------------|-------------|------:|-------------|
| 2026-11-02 | Base 1 W1 | 11,75 | [`2026-10-26-uke-06.md`](2026-10-26-uke-06.md) |
| 2026-11-09 | Base 1 W2 | 14,25 | [`2026-10-26-uke-07.md`](2026-10-26-uke-07.md) |
| 2026-11-16 | Base 1 W3 | 16,0 | [`2026-10-26-uke-08.md`](2026-10-26-uke-08.md) |
| 2026-11-23 | Base 1 W4 | 8,5 | [`2026-11-23-uke-09.md`](2026-11-23-uke-09.md) |
| 2026-11-30 | Base/build 2 W1 (Vo2) | 12,5 | [`2026-12-uke-10.md`](2026-12-uke-10.md) |
| 2026-12-07 | Base/build 2 W2 (Vo2) | 15,0 | [`2026-12-uke-11.md`](2026-12-uke-11.md) |
| 2026-12-14 | Base 2 W3 | 16,75 | [`2026-12-uke-12.md`](2026-12-uke-12.md) |
| 2026-12-21 | Base 2 W4 + FTP | 8,5 | [`2026-12-uke-13.md`](2026-12-uke-13.md) |
| 2026-12-28 | Base 2 W1 | 12,5 | [`2026-12-uke-14.md`](2026-12-uke-14.md) |

Jan 2027 → ukefiler **skrives 2–4 uker før** (samme ATP CSV).

---

## Intensitet (ATP «Details»)

Gjennomgående limiter: **Endurance, Speed Skill** (+ **Muscular Endurance** fra base 2).  
**Vo2** merket kolonne G uke **2026-11-30** og **2026-12-07**.

Sykkel-rotasjon mot 275 W: [`docs/athlete/sykkel-opv-2018-build-rotasjon.xlsx`](../docs/athlete/sykkel-opv-2018-build-rotasjon.xlsx) + [`notater/tp-2018-okt-des-sykkel-opv.md`](notater/tp-2018-okt-des-sykkel-opv.md).

---

## Agent / scripts

```bash
python3 scripts/export_atp_lofoten_csv.py
# Sammenlign uke faktisk vs TARGET:
# plans/csv/intervals-weekly-targets-atp-lofoten.csv
```

Ved ATP-endring i TP: **eksporter/lagre xlsx på nytt** → kjør export → oppdater denne filen + uke-`.md` headers.
