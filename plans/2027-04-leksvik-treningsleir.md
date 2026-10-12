# Treningsleir Leksvik — 16.–25. april 2027 (tentativ)

**Format:** **Fredag 16. apr → søndag 25. apr** (10 dager) · **med samboer** på hytta/leilighet  
**Plassering i planen:** Rett etter **M6-W4 recovery** (5.–11. apr) · **B5 base → build-bro** · **før** mai-build (M7).  
**Hvorfor da:** Kyst/Leksvik er normalt **snøfri og kjørbart** fra midt april — **camp-volum** utendørs, ikke mai-topp (M7).

---

## Styring — camp = **15–20 t**

| | |
|---|---|
| **Timer på hytta 16.–25. apr** | **~18–20 t** (målband for **hele oppholdet**) |
| **Kalenderuke 12.–18. apr** | **~15 t** (hjemme man–tor + første hyttedager) |
| **Kalenderuke 19.–25. apr** | **~17–20 t** (ren camp-uke til avreise) |
| **TSS (uke 19–25)** | ~**750–850** (mye Z2; ikke jage TSS med korte intervaller) |
| **Kvalitet** | **1× SS** (ons 14. hjemme *eller* ons 21. på hytta — **ikke begge**) |
| **Risiko** | 15–20 t uten **man 19.** ro + fueling → sykdom; samboer føler seg nr. 2 |
| **Plan B** | 15 t gulv: kutt **30 min** på tirs/fre før du kutter søn/lør; under 15 t → ekstra **45 min Z2** tir eller tor |

**Mikro:** [`2027-04-12-uke-leksvik.md`](2027-04-12-uke-leksvik.md) · [`2027-04-19-uke-leksvik.md`](2027-04-19-uke-leksvik.md)

**Volum-sjekk:** Tell timer **søndag 25. kveld** — skal stå **≥ 18 t** fra fre 16. (eller **≥ 15 t** hvis Plan B-uke).

---

## Før avreise (hjemme 12.–15. apr) — ~7 t

| Dag | Fokus | Varighet ca. |
|-----|--------|----------------|
| **Man 12** | Svøm S05 + ST04 | 95 min |
| **Tir 13** | Løp R03 | 70 min |
| **Ons 14** | **SS 2×20** | 95 min |
| **Tor 15** | Svøm S01 + styrke lett | 85 min |

---

## På hytta 16.–25. — dag for dag (~18–20 t sum)

| Dag | Økt | Varighet | Kommentar |
|-----|-----|----------|-----------|
| **Fre 16** | Lett sykkel / jogg med samboer | **90 min** | Ankomst |
| **Lør 17** | **Lang sykkel Z2** | **3:45–4:00** | Hoveddag 1 · CHO 60–90 g/t |
| **Søn 18** | Long easy løp | **90 min** | Etter sykkel |
| **Man 19** | Lett sykkel Z1 eller gåtur | **75 min** | **Påkrevet** ro — ikke fri hvis du jager 20 t |
| **Tir 20** | Sykkel Z2 steady | **2:45** | Felles tur, pauser OK |
| **Ons 21** | **Q:** løp 5×3 *eller* SS 2×15 (se under) | **85–95 min** | Én hard |
| **Tor 22** | Svøm (tur Trondheim) *eller* sykkel Z1 | **75–90 min** | Avlastende teknikk |
| **Fre 23** | **Lang sykkel Z2** | **3:30–4:00** | Hoveddag 2 — annen rute enn lør 17 |
| **Lør 24** | **Brick:** sykkel Z2 + løp easy | **3:15–3:30** (ca. 2:45 + 25–30 løp) | B5-intro |
| **Søn 25** | Shakeout + avreise | **60–75 min** | |

**Sum hytta:** ca. **19–20,5 t** (juster tirs 20. eller fre 23. ned **15 min** hvis du er sliten).

### Ons 21 — hard økt
- **SS 14. apr kjørt:** løp **5×3 min** (R06) **eller** sykkel **3×8 min SS** — totalt **~85 min**.  
- **SS ikke kjørt 14. apr:** **SS 2×15** sykkel **~90 min**.

---

## Samboer-regler (ved 15–20 t)

- **Lør 17. og fre 23.:** én kafé/lunsj-stopp — ikke «stå og vente i veikanten».  
- **Man 19. og kvelden tor 22.:** ingen treningsmoral — det er **del av planen**.  
- **Tir 20.:** kort felles tur **før** eller **etter** hovedøkt, ikke erstatt sosial tid.

---

## Etter 25. april

- **26. apr – 2. mai:** **~11–12 t** recovery-uke (svøm, lett sykkel, **ingen** ny 4 t-sykkel).  
- **Mai (M7):** build som tabell — camp er **ikke** grunn til å starte mai på 18 t uten recovery.

---

## Praktisk

- **10 netter** 16.–25. · sykkel + medhaling · værforbehold → skyv hele blokken, ikke mai.

## Intervals.icu

```bash
python3 scripts/intervals_push_calendar.py --start 2027-04-12 \
  --plan plans/csv/trainingdojo-2027-04-leksvik.csv \
  --notes plans/csv/trainingdojo-uke-notater-2027-04-leksvik.csv \
  --bike-calendar plans/csv/sykkel-zwo-kalender-2027-04-leksvik.csv
```

`external_id` bruker planstart **2027-04-12** — påvirker ikke Q4-planen (2026-10-26).

## Koblinger

- [`mengdeperioder-2026-2027.md`](mengdeperioder-2026-2027.md) · [`blokker-periodisering-2026-2027.md`](blokker-periodisering-2026-2027.md)  
- Leksvik-load historikk: [`2026-10-analyse-siste-uker.md`](2026-10-analyse-siste-uker.md) — **fordel** load over **to** langsykkeldager, ikke én monsterdag.
