# TP-analyse — sykkel okt–des 2018 (OPV / NTG)

**Kilde:** `fetch_tp_workouts.py` / tpapi fitness/v6, athlete `1884639`, **2018-10-01 – 2018-12-31**. Rådata: `data/trainingpeaks/exports/tp-2018-oct-dec.json` (lokal, gitignored). Intervalluttrekk: `tp-2018-bike-intervals.md`.

**William:** 16 år, NTG. FTP **250 W (5. nov)** → **325 W (18. des)** — se `docs/athlete/profile.md`.

---

## Volum (sykkel, fullførte timer der TP har `TotalTime`)

| Måned | Sykkel-timer (ca.) | Kommentar |
|-------|-------------------|-----------|
| Okt 2018 | **~14 h** | Lav start (høstferie, terreng, få planlagte |
| Nov 2018 | **~22 h** | FTP 5. nov, terskel-uker |
| Des 2018 | **~33 h** | Tett kvalitet + langtur + FTP 18. des |

**46 sykkeløkter** på 3 mnd (~**69 h** med data). Mye **NTG-felles** (beskrivelser «klasse 1/2+3», PerfPro).

---

## Mønster (des — der FTP hopper)

Typisk uke **des 2018** (grovt):

| Rolle | Økt-type | Frekvens |
|-------|----------|-----------|
| **Hard 1** | Terskel **6×8 + 7×8 min** @ 95–102 % FTP | Gjentatt (19., 26. nov, 3. des) |
| **Hard 2** | **18×3′** (8× @ 95 %, 10× @ 100 %) eller **8–9×6 min** terskel | 10., 15., 23. des |
| **Hard 3** | **Sweet spot** (pauser **40 %**) eller **crisscross 6×10′** 45/15 | 1., 8., 28. des |
| **Test** | **FTP** | 5. nov, **18. des** |
| **VO2** | **30-15** sykkel (eller 4×8 ski/løp) | 31. des |
| **Grunnmur** | Langtur 2–3,5 h, «sykkel etter styrke» 1 h, teknikk | Mellom harddager |

**OPV-prinsipp synlig i tekst:** «klarer dere ikke intervalløktene — snakk, juster mengde», «søndag bedre for volum enn fredag», nedkjøring **50 W** «sitte uten hender».

---

## Intervalløkter — rene sykkel-Q (kopierbar liste)

Preskripsjon som står i **TP Description** (Watt i 2018 = **% av din FTP den høsten** — skaler til **200 W nå** med samme %, eller re-beregn når FTP oppdateres).

### 1. Kapasitet / raske føtter (rulle)

**2018-10-02** — *4×12 × (30 s hard / 15 s lett)*, **5 min** pause mellom serier.  
30 min oppvarming, 20 min nedkjøring.  
→ 2026: f.eks. 30 s @ **120–125 % FTP**, 15 s @ **50 %**.

### 2. FTP-test

**2018-11-05** — 30 min opp + **30 min FTP-test** (gruppe-delt).  
**2018-12-18** — FTP test (~1,5 h total, TSS ~80).  
→ 2026: ramp som `workouts/zwo/bike/ftp-ramp-test.zwo`; **én** max-test per 4–6 uker.

### 3. Crisscross terskel / sweet spot (OPV-signatur)

**2018-11-13** — **6×10′** mønster **45 s «terskel» / 15 s sweet spot** (~**100 % / 85–95 % FTP** i tekst), **2 min** pause; etterpå **5×8″** spurter, 2 min pause.  
**2018-12-28** (i langtur 2 h) — **6×10′ 45/15** @ **93 % / 83 %**, 2 min pause + spurter.  
→ Repo-mal: `knowledge/coach/opv-nokkelokter.md` **crisscross 6×10** (93/83 % eller 45/15 s).

### 4. Terskel blokker **6×8 + 7×8 min**

**2018-11-19, 11-26, 12-03** — 20 min opp; **6×8 min** + **7×8 min** @ **95–102 % FTP** (OPV forklarer FTP/terskel); 20 min ned @ ~50 W.  
→ Tilsvarer **lang terskel** / **4×8-utvidelse** — i 2026: **4×8 @ 90 %** eller **5×10 @ 98 %** når TSB grønn; ikke begge samme uke som VO2.

### 5. Sweet spot (struktur i PerfPro)

**2018-12-01, 12-08** — tittel *Sweetspot (pauser 40 %)*, TSS **91–123**. Beskrivelse: kan kjøres ute med puls/RPE.  
→ 2026: **2×20 @ 88–92 % FTP** eller **3×15 @ 90 %** (`opv-nokkelokter` SS); pauser **40 % FTP**.

### 6. **18×3′** (VO2/terskel OPV)

**2018-12-10** — **16–20×3′** (yngre 8+8): **10× @ 95 %**, 1 min pause → **10× @ 100 %**, 1,5 min pause.  
**2018-12-23** — **18×3′** samme mal.  
→ Direkte match `opv-nokkelokter.md` **18×3′** — build-fase, ikke Base 1 uke 1.

### 7. **8–9×6 min** terskel

**2018-12-15** — **8–9×6 min**, **2 min** pause; annenhvert drag **93–96 %** / **96–98 %**.  
→ 2026: **5×6 @ 95 %** comeback-versjon før full 8×6.

### 8. VO2 (kort)

**2018-12-13** (alternativ til løp) — **4–5×6 min** med **110–115 %** topper.  
**2018-12-31** — **30-15** sykkel (OPV: «30-15 sykkel eller 4×8»).  
→ 2026: **5×3 @ 106–112 %** eller **30/15 × 12–15** når FTP ≥ 250.

### 9. Ikke intervall (men viktig i blokken)

- **Langtur** 2–3,5 h (nov/des), ofte **rolig** før neste Q.  
- **1 h sykkel etter styrke** + ev. **5×8 s** spurt (eldre).  
- **Teknikk** 29. des (ettbein, no-hands st tråkk) — lav intensitet.

---

## Forslag: rotasjon des 2026 → 275 W (tri-tilpasset)

**Ikke** kopier **69 h sykkel/3 mnd + 3 harde Q/uke** — du har svøm/løp og MSK-comeback.

**Sykkel-Q rotasjon (4 uker, gjenta til nyttår)** — én hard sykkel/dag, SS eller terskel:

| Uke | Hard sykkel (velg én) | Støtte sykkel |
|-----|------------------------|---------------|
| 1 | **2×20 sweet spot** (40 % pause) | 2× **90–120 min Z2** |
| 2 | **6×10 crisscross** 45/15 @ 93/83 % | Z2 + ev. kapasitet **3×10×30/15** |
| 3 | **4×8 @ 90 % FTP** (OPV 4×8) | Z2 lang **2 h** |
| 4 | **FTP ramp** eller **18×3′** (kun hvis TSB ≥ −25) | Recovery spin |

Roter **18×3** og **8×6 terskel** inn fra **uke 3–4 des** når du ligger **≥240 W** testet — som 2018, men **max 2** harde sykkeløkter/14 dager, ikke 3.

---

## Filreferanser repo

| OPV-økt | Fil / kunnskap |
|---------|----------------|
| Crisscross | `knowledge/coach/opv-nokkelokter.md` |
| 18×3 | samme |
| SS 2×20 | `knowledge/sykkel/intervaller-og-sonearbeid.md` |
| FTP ramp | `workouts/zwo/bike/ftp-ramp-test.zwo` |

**Neste steg:** William «roterer etterpå» — agent kan mappe tabellen over til `workouts/planned/bike/` + ZWO @ **% FTP 200→275** når du ber om konkret des-kalender.

**Excel (sykkel-only + build 3+1):** [`docs/athlete/sykkel-opv-2018-build-rotasjon.xlsx`](../athlete/sykkel-opv-2018-build-rotasjon.xlsx) — regenerer med `python3 scripts/generate_sykkel_opv_workbook.py`.
