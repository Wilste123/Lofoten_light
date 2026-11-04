# Mengdeperioder (mesosykluser) — Half Extreme 2027

**Formål:** Eksplisitt **volum-periodisering** (timer/uke og TSS) i **3+1**-mønster, koblet til makroblokker.

| Lag | Fil | Hva |
|-----|-----|-----|
| **Makro** | [`blokker-periodisering-2026-2027.md`](blokker-periodisering-2026-2027.md) | B0–B10, fase og formål |
| **Mengde (meso)** | **Denne filen** + [`csv/mengdeperioder-2026-2027.csv`](csv/mengdeperioder-2026-2027.csv) | 4-ukers blokker: W1→W3 opp, W4 recovery |
| **Mikro** | `2026-*-uke-*.md` + `csv/trainingdojo-*.csv` | Dag-for-dag (kun der det finnes) |
| **Ukentlig TARGET** | [`csv/intervals-weekly-targets-2026-10-12-12-31.csv`](csv/intervals-weekly-targets-2026-10-12-12-31.csv) | Intervals planned load/time (**operativ**) |
| **Intensitet** | [`knowledge/triathlon/periodisering-mot-2027.md`](../knowledge/triathlon/periodisering-mot-2027.md) | Hvilken Q på sykkel/løp/svøm per fase — **ikke** samme tabell som mengde |

**Fryst (ikke mengde-meso):** Uke 12.–18. okt — [`FROZEN-til-deload-2026-10-25.md`](FROZEN-til-deload-2026-10-25.md). Uke 19.–25. = build (Lillehammer), ikke kalender-deload.

---

## Er det «ordentlig» periodisert?

| Ja | Delvis / mangler |
|----|------------------|
| Makro B0–B10 med 750–800 t og akkumulerte sjekkpunkter | **Des–jul 2027:** mengde-mesos er planlagt her, men **ikke alle** har uke-CSV/Intervals push ennå |
| 3+1 recovery-regel i blokker | **Intensitet** styres per fase, ikke uke-for-uke i samme CSV som timer |
| November→des **stigende** snitt (des > nov) | **Jan–apr 2027:** følg tabellen under; detaljuker skrives fortløpende |
| Årets **volumstopp** = B8 (jul 2027), ikke nov 2026 | |

---

## Mengde-mesosykluser (kalender)

Hver meso: **uke 1–3 progresjon**, **uke 4 −25–35 % timer** (lav intensitet).  
`week_start` = mandag (ISO). TSS er veiledende (~50–55 load/time i base).

### M1 — B1 kontakt II (ATP Base 1)

| Uke start | Timer **ATP** | TSS ca. | Merknad |
|-----------|---------------|---------|---------|
| 2026-10-26 | 12,0 *(Prep)* | 624 | [`uke-05`](2026-10-26-uke-05.md) |
| 2026-11-02 | **11,75** | 611 | Base 1 W1 FTP — [`uke-06`](2026-10-26-uke-06.md) |
| 2026-11-09 | **14,25** | 741 | Base 1 W2 — [`uke-07`](2026-10-26-uke-07.md) |
| 2026-11-16 | **16,0** | 832 | Base 1 W3 volum — [`uke-08`](2026-10-26-uke-08.md) |
| 2026-11-23 | **8,5** | 442 | Base 1 W4 recovery + FTP — [`uke-09`](2026-11-23-uke-09.md) |

### M2 — Base/build 2 (des, ATP)

| Uke start | Timer **ATP** | TSS ca. | Merknad |
|-----------|---------------|---------|---------|
| 2026-11-30 | **12,5** | 650 | Vo2 — [`2026-12-uke-10.md`](2026-12-uke-10.md) |
| 2026-12-07 | **15,0** | 780 | Vo2 — [`2026-12-uke-11.md`](2026-12-uke-11.md) |
| 2026-12-14 | **16,75** | 871 | Base 2 W3 — [`2026-12-uke-12.md`](2026-12-uke-12.md) |
| 2026-12-21 | **8,5** | 442 | Recovery + **FTP 275** — [`2026-12-uke-13.md`](2026-12-uke-13.md) |
| 2026-12-28 | **12,5** | 650 | Base 2 W1 — [`2026-12-uke-14.md`](2026-12-uke-14.md) |

> Full kalender → race: [`ATP-Lofoten-synk.md`](ATP-Lofoten-synk.md) + [`csv/atp-lofoten-weekly.csv`](csv/atp-lofoten-weekly.csv)

### M4 — B3 (jan–feb) — timer fra ATP CSV

| Uke start | Timer | TSS ca. |
|-----------|-------|---------|
| 2027-01-18 | 11,5 | 540 |
| 2027-01-25 | 12,0 | 560 |
| 2027-02-01 | 12,0 | 560 |
| 2027-02-08 | 9,0 | 420 | Recovery |

### M5 — B4 vinter solid

| Uke start | Timer | TSS ca. |
|-----------|-------|---------|
| 2027-02-15 | 12,0 | 560 |
| 2027-02-22 | 12,5 | 590 |
| 2027-03-01 | 13,0 | 620 |
| 2027-03-08 | 9,5 | 450 | Recovery |

### M6 — B5 base peak → build bro

| Uke start | Timer | TSS ca. |
|-----------|-------|---------|
| 2027-03-15 | 13,0 | 620 |
| 2027-03-22 | 13,5 | 650 |
| 2027-03-29 | 14,0 | 680 |
| 2027-04-05 | 10,0 | 480 | Recovery |
| 2027-04-12 | 15,0 | 700 | **Leksvik camp** uke 1 (~15 t) — [`2027-04-12-uke-leksvik.md`](2027-04-12-uke-leksvik.md) |
| 2027-04-19 | 18,5 | 800 | **Leksvik camp** uke 2 (**17–20 t**) — [`2027-04-19-uke-leksvik.md`](2027-04-19-uke-leksvik.md) |

### M7–M9 — Build (mai–jul 2027) · **årets mengdetopp**

| Meso | Uke-start ca. | Snitt timer (W1–W3) | Recovery W4 |
|------|---------------|---------------------|-------------|
| M7 B6 | mai 2027 | 14–15 | ~10,5 |
| M8 B7 | jun 2027 | 15–16 | ~11 |
| M9 B8 | jul 2027 | **15,5–16** | ~11,5 |

Detaljukesplaner + CSV for M3→M9: **lages 2–4 uker før** meso-start (eller på forespørsel).

### M10 — B9 spesifikk + B10 taper

Spesifikk: hold **15–16 t** med høy andel Lofoten-spesifikk tid; taper: −40 % → race (se blokker).

---

## Kobling 750–800 t

| Dato | Akkumulert (ca.) | Kilde |
|------|------------------|--------|
| 31. des 2026 | ~160 t | blokker |
| 31. mar 2027 | ~320 t | blokker |
| 30. jun 2027 | ~500 t | blokker |
| Pre-race aug 2027 | 620–680 t | 12mnd-tabell |

Mengde-mesos over **stiger** mot M7–M9; panikk-volum i én uke er forbudt (+10 % regel i `12mnd-periodisering.md`).

---

## Operativt for deg nå

1. **Kjør** fryst build/deload til 25. okt.  
2. **M1** er skrevet og pushet fra 26. okt (`trainingdojo-2026-10-26-nov30.csv`).  
3. **M2** timer ligger i TARGET CSV; **des-ukefiler** kommer etter nov (eller si «push des»).  
4. Spørsmål «ligger jeg riktig?» → sammenlign **faktisk uke** med `intervals-weekly-targets` + denne tabellen.
5. **Volum-checkpoints** (NOTE i Intervals): [`csv/intervals-volum-checkpoints-okt-des2026.csv`](csv/intervals-volum-checkpoints-okt-des2026.csv) — push med `intervals_push_calendar.py --notes-only`.

---

## Relatert

- [`2026-post-deload-ramp.md`](2026-post-deload-ramp.md) — kort narrativ etter deload  
- [`2026-2027-12mnd-periodisering.md`](2026-2027-12mnd-periodisering.md) — månedssnitt  
- [`csv/12mnd-periodisering.csv`](csv/12mnd-periodisering.csv) — måned min/max timer (Excel)
