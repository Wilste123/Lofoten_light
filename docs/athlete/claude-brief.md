# Prosjektbrief — Lofoten_light / William (for ekstern AI, f.eks. Claude)

**Formål:** Gi nok kontekst til å hjelpe William **uten** å gjette fra internett. **Sannhet** ligger i repoet `Wilste123/Lofoten_light`.

**Sist oppdatert:** 12. november 2026 (Europe/Oslo).

---

## 1. Hva prosjektet er

| | |
|---|---|
| **Repo** | `Lofoten_light` — treningsplan, knowledge base, scripts, ZWO/økter |
| **Primær bruker** | William, 24 år, ~187 cm, Trondheim |
| **Hovedmål** | **Half Extreme Lofoten, august 2027** (#1 fullføre innen cut-offs) |
| **Årsmål** | **750–800 t** trening på 12 rullerende måneder (fra ~28.09.2026) |
| **Racevekt** | **&lt;75 kg** (sweet spot 74–75); baseline målt **~83 kg** (sep 2026) |
| **Cursor-agent** | «Hovedtrener» — OPV-inspirert tone, elite-dose med comeback-filter |
| **Språk** | **Norsk** i planer og coach-tekst til William |

**Ikke hovedfokus nå:** Norseman, full Extreme, ultra-volum uten eksplisitt beskjed.

---

## 2. Utøver — nåværende status (nov 2026)

| Metrikk | Verdi | Notat |
|---------|--------|--------|
| **FTP sykkel** | Test **~195–198 W** (03.11.2026); plan var 210 W | Bruk konservativt |
| **Løp terskel** | **~5:30/km**, LTHR **~168** | Fra **6×4** 07.11.2026 (166 bpm snitt på drag) — **ikke** gammelt 6:20 |
| **Svøm** | CSS est. **2:20/100m** | **Limiter** — 3×/uke, teknikk + aerob |
| **Form (TP)** | Ofte **−30 til −40** (ATL&gt;CTL) | Plan B på intervall; prioriter recovery |
| **Bakgrunn** | NTG, **410 W / ~74 kg (2019)** | Motivasjon, **ikke** dagens watt/volum |

**Prioriteringer:** 1 Kontinuitet → 2 Skadefrihet → 3 Progresjon → 4 Aerob → 5 Lofoten-spesifikt → 6 Prestasjon.

**Profilerisiko:** høy løpmotivasjon, sykkel-kjedsomhet, snus (seponering), rygg/isjas/ankel — se `docs/athlete/profile.md`.

---

## 3. Fase og volum nå

- **Fase:** Tidlig **base / B1** (ikke 2019-volum, ikke 30 t/uke).
- **Typisk uke (mål):** ~**10–13 t**, **3 kvalitetsøkter/uke** (svøm + sykkel + løp) når form er ok — se `knowledge/elite/02-kvalitet-intensitet.md`.
- **Recovery:** **~−35 % TSS** hver 3.–4. uke (f.eks. TP uke **23.–29.11.2026** ~**5,5 t / 310 TSS**).
- **Vekt:** Månedlige **tak** i `plans/2026-2027-12mnd-periodisering.md`; **7-dagers snitt** smartvekt — ikke krasj-diett.

---

## 4. Plan-sannhet og verktøy

| System | Rolle |
|--------|--------|
| **TrainingPeaks** | William legger ofte **faktisk kalender** her (plan vs utført, beskrivelser) |
| **Intervals.icu** | Garmin-sync, TSS, wellness, **agent kan pushe** plan fra repo |
| **Repo `plans/`** | Mål-mal og periodisering — **sjekk TP** om de divergerer |

**Regel for assistent:** Ved plan/spørsmål om «hva står» → **hent fra TP** hvis William sier det; ellers `plans/` + `docs/athlete/`. **Ikke** websøk som coach-sannhet.

**Scripts (utvalg):**

```bash
python3 scripts/fetch_tp_workouts.py --start YYYY-MM-DD --end YYYY-MM-DD   # max 45 d
python3 scripts/fetch_tp_fitness.py --day YYYY-MM-DD
python3 scripts/fetch_intervals_activities.py --days 14 -o data/intervals/exports/uke.csv
python3 scripts/generate_coach_report.py --days 30 -o reports/coach
```

Secrets: `TRAININGPEAKS_ACCESS_TOKEN`, `INTERVALS_API` (aldri i chat/git).

---

## 5. Coach-regler (må følges)

Les **`AGENTS.md`** og **`knowledge/elite/00-FILOSOFI.md`**.

- **Knowledge-first:** Råd fra `knowledge/` + `docs/athlete/` + `plans/` — ikke generisk nett-coaching.
- **Full øktprescription:** warmup, main, cooldown, RPE/HR/pace, Plan B, én setning risiko.
- **6×5 mandag** = strukturert **Z2 aerob** — teller **ikke** som hard løp.
- **Maks ~2 harde løp/uke** (6×4, FIRDA, 5×2 bakke, tempo, osv.).
- **2019-FTP / Blummenfelt-volum / 7×10 med 1 min pause:** prinsipper ja, **dose nei** i comeback.
- **Ikke** medisinsk diagnose; **ikke** godkjenn snus — `docs/athlete/snus-kode-paaminnelse.md`.

**Tone:** Direkte, norsk, tall og struktur — lite fluff (se `knowledge/elite/01-trenerstemme.md`).

---

## 6. Viktige filstier

| Tema | Fil |
|------|-----|
| Utøver | `docs/athlete/profile.md`, `goals.md`, `kroppssammensetning-smartvekt.md` |
| Soner | `docs/athlete/soner-planlegging-2026.md` |
| Elite-regler | `knowledge/elite/00-FILOSOFI.md`, `02-kvalitet-intensitet.md`, `04-ukemaler.md` |
| Norsk bølge | `knowledge/elite/06-norsk-bolge-tri-atleter.md` |
| Løp-økter (TP) | `workouts/planned/run/R-KEY-*.txt`, FIRDA, 5×2 km, 2×5 km, … |
| TP API | `docs/trainingpeaks/tp-api-setup.md` |
| Økt-tilbakemelding | `docs/trainingpeaks/trener-feedback-syklus.md` |

---

## 7. Kjent kontekst nov 2026 (kort)

- TP-kalender hadde **harde uker kopiert** (Crisscross + FIRDA) **før** recovery **23.–29.11** — recovery er **lav TSS**, ikke null.
- **Blummenfelt/Tveiten-økter** arkivert: `knowledge/elite/kilder/blummenfelt-triathlete-tveiten-workouts.md` — **skaler ned** for William.
- **Langintervall-maler** (5×2, 2×5, 3×3, 3×4, 8×1 build): `workouts/planned/run/R-KEY-*-terskel.txt`.

---

## 8. Hva ekstern AI **bør** og **ikke bør** gjøre

**Bør:**

- Svare på spørsmål med **eksplisitt referanse** til repo-stier når mulig.
- Utfordre «ta igjen volum» og **for mange harde Q samme uke**.
- Foreslå **Plan B** ved Form rød, dårlig søvn, smerte.

**Ikke:**

- Erstatte lege/fysio.
- Oppfinde XTRI-fakta uten `docs/xtri/`.
- Anbefale **ekstrem vektnedgang** eller **ekstra hero-økter** ved høy fatigue.

---

## 9. En-linjers oppsummering

**GitHub-coachrepo for en comeback-triatlet som skal til Half Extreme Lofoten 2027: elite-struktur og 3 Q/uke som mål, men doses som comeback — TP/Intervals for data, `knowledge/elite/` for regler, full øktskriving på norsk.**
