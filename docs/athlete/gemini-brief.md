# Brief — William / Half Extreme Lofoten 2027 (for ekstern AI, f.eks. Gemini)

**Sist oppdatert:** 15. oktober 2026  
**Primær coach-kilde:** GitHub-repo `Lofoten_light` + Cursor Cloud Agent (trener som Ole Petter Vibekken-inspirert struktur, tri/comeback-tilpasset).  
**Språk:** Norsk i planer og coach-tekst; engelsk ok for teknisk.

---

## 1. Hvem og hva

| | |
|---|---|
| **Navn** | William, 24 år, ~187 cm, Trondheim |
| **Mål** | **Half Extreme Lofoten**, august **2027** |
| **Årsmål volum** | **750–800 t** trening på **12 rullerende måneder** (fra planstart **28.09.2026**) |
| **Race vekt** | **&lt;80 kg** (sweet spot 78–79); start ~**90 kg** (sep 2026) |
| **Bakgrunn** | NTG / landevei høyt nivå; **FTP 410 W @ ~74 kg (2019)** — **ikke** dagens intensitet |
| **Nå (okt 2026)** | Comeback etter 4–5 år lavt volum; **FTP plan ~210 W**; **svøm = limiter**; løp = motivasjon; sykkel = kan bli kjedelig uten variasjon |
| **Prioritering (rekkefølge)** | 1 Kontinuitet → 2 Skadefrihet → 3 Gradvis progresjon → 4 Aerob → 5 Lofoten-spesifikk → 6 Prestasjon |

---

## 2. Hva vi holder på med nå (okt 2026)

- **Fase:** Re-etablering / tidlig **base** (B0→B1), **ikke** 2019-volum.
- **Planstart:** `plans/` fra **28.09.2026**; operativ ukekalender pushes til **Intervals.icu**.
- **Typisk uke nå:** ~**8–10 t** (stiger mot ~10–12 t i nov–des), **én** hard løpøkt/uke (f.eks. **5×3**), **2–3 svøm**, sykkel **Z2**, **2× styrke** (prehab/kjerne, ikke bodybuilding).
- **Uke 12.–18.10.2026:** «Build»-uke (~9,5 t) — **fredag = anker** intervall; **mandag hvile** etter tung helg.
- **Uke 19.–25.10:** Build med **Lillehammer** (man–ons: løp, **ingen** sykkel/basseng der); **lør hytte** (ingen trening); **fre morgen** 5×3; **søn kveld** svøm mulig.
- **Fra 26.10:** M1-blokk i `plans/mengdeperioder-2026-2027.md` + `intervals-weekly-targets-2026-10-12-12-31.csv`.

**Styringspunkt volum (optimistisk kurve):** ~**160 t akkumulert** ved **31.12.2026** (korridor 152–168). William teller ofte **kun fra 28.9** → da er ~**25 t** ved **18.10** og ~**42 t** ved **31.10** realistisk på plan — ca. **«2 uker»** (~20–25 t) under optimistisk kurve ved nyttår er **akseptabelt**; ikke panikk-volum.

---

## 3. Beslutninger du bør kjenne til (okt 2026)

| Tema | Avtale |
|------|--------|
| **Deload** | Uke 12.–18 holdes som er (rolig nok); **uke 19.–25** er **build**, ikke kalender-deload. |
| **Svøm — timer i Intervals** | **Ignore velocity** på svøm (sport eller per økt) → **uketimer = tid i hallen** (elapsed), ikke bare moving. **Ikke** ekstra «tom» svøm-økt for å fylle tid. |
| **Svøm — pace/analyse** | **Garmin Connect** for lengder/sett/CSS-arbeid; **Intervals** for load, fitness, ukeplan. |
| **Vekt** | Smartvekt **morgen**, **7-dagers snitt**; BIA ~20 % trend; ikke reagere på 1 kg dagsving. |
| **Kickr** | Kjøpt brukt v4; klikk ved høy watt selger sier er ok; **12×142** thru-axle Basso. |
| **Checkpoints** | NOTE i Intervals: `plans/csv/intervals-volum-checkpoints-okt-des2026.csv` (optimistiske mål); William beholder dem som **stjerner**, ikke dom over planstart-telling. |

---

## 4. Data og verktøy

| System | Bruk |
|--------|------|
| **Intervals.icu** | Kalender, TSS, CTL/ATL, wellness (søvn, HRV, RHR, vekt), ukemål |
| **Garmin** | Aktiviteter, svøm laps/pace, søvn/HRV sync til Intervals |
| **Repo `Lofoten_light`** | Sannhet for plan, ZWO, coach-filosofi, scripts |

**Nøkkelfiler for kontekst:**

- `docs/athlete/profile.md`, `goals.md`, `kroppssammensetning-smartvekt.md`
- `knowledge/coach/coach-filosofi.md`, `ukemaler.md`
- `plans/mengdeperioder-2026-2027.md`, `blokker-periodisering-2026-2027.md`
- `AGENTS.md` — hvordan Cursor-coachen skal opptre

**Typiske kommandoer (agent):**

```bash
python3 scripts/fetch_intervals_wellness.py --days 14 -o data/intervals/exports/wellness-latest.csv
python3 scripts/fetch_intervals_activities.py --days 14 -o data/intervals/exports/uke.csv
python3 scripts/analyze_intervals_wellness.py data/intervals/exports/wellness-latest.csv
python3 scripts/intervals_push_calendar.py --start YYYY-MM-DD --plan plans/csv/....csv --notes ...
```

---

## 5. Hvordan coach skal svare (kort)

- **Full øktprescription** for kvalitetsøkter: oppvarming, main, cooldown, RPE/puls, Plan B, én setning risiko.
- **Utfordre** komfortsonen som sykkelcoach, men **beskytte** mot skade og 2019-volum-tank.
- **Ikke** medisinsk diagnose; **ikke** finne på Xtri-fakta uten `docs/xtri/`.
- **Historisk 410 W FTP** = motivasjon, **ikke** sonegrunnlag før ny test.

---

## 6. Nylig belastning / wellness (snapshot 15.10.2026)

- **CTL ~27, ATL ~77–83** — akutt tretthet &gt; «form»; typisk etter tung helg (løp **~173 TSS** søn 11.10).
- **HRV** ofte **~58–59**, dip til **~49** etter hard dag; **søvn** variabel (viktig for rebound).
- **14.10:** Sykkel ~1 t + løp ~1 t — løp **for hardt** (høy puls/Z4) vs planlagt easy; **15.10** plan: **60 min rolig svøm + lett kjerne/styrke**; **fre 16.10** = **5×3** anker (vurder **6×2** hvis stølhet 3 + lav HRV).

---

## 7. Hva Gemini kan hjelpe med (uten å overstyre coach)

- Research (utstyr, vær, generell fysiologi), tekst/redigering, kode i repo, Excel/CSV, oppsummering av logger brukeren limer inn.
- **Ikke** erstatte ukentlig periodisering eller øke volum aggressivt uten å lese `plans/` og `mengdeperioder`.
- Ved konflikt: **repo-plan + Intervals TARGET** &gt; generiske tri-råd.

---

## 8. Én setning til Gemini

*William trener mot Half Extreme Lofoten 2027 med konservativ comeback-ramp (~8–12 t/uke mot 750–800 t/år), svøm som limiter, Intervals for belastning og Garmin for svøm-fart, én hard løpøkt/uke, og checkpoints mot ~160 t ved nyttår som optimistisk styringslinje — ikke 2019-volum.*
