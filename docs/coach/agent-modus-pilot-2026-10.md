# Agent modus — test-pilot (oktober 2026)

**Utøver:** William Berg Steffenak  
**Repo:** [Wilste123/Lofoten_light](https://github.com/Wilste123/Lofoten_light)  
**Branch / PR:** `cursor/uke1-bakke-5x2-tor-634c` → [PR #17](https://github.com/Wilste123/Lofoten_light/pull/17)  
**Cursor-agent:** «Agent modus» (cloud run, okt 2026)  
**Mål med piloten:** Bruke Cursor Cloud Agent som **hovedtrener + teknisk hjelper** — plan, analyse, Intervals/TP, eksport — uten å erstatte William som beslutningstaker i kalenderen.

---

## 1. Hva ligger i GitHub (og hva gjør ikke)

### I repo (committet / pushet)

Alt **kode, dokumentasjon og committed eksportfiler** agenten har laget i denne piloten ligger på branch over. Typisk:

| Område | Innhold |
|--------|---------|
| **Coach-analyse** | `scripts/generate_coach_report.py`, `plot_readiness_report.py`, `plot_recent_hytte_dashboard.py`, `compute_readiness.py`, `readiness_total_load.py` |
| **TB-Score v2** | Tidspunkt-snapshot, komponenter (CTL/ATL, HRV, søvn, tid siden økt); subjektiv wellness default av |
| **Intervals → TP** | `scripts/export_intervals_plan_to_tp.py` |
| **Eksportpakke** | `exports/tp-from-intervals/` + `exports/tp-from-intervals.zip` (**22.–31. okt 2026**, fra Intervals-kalender) |
| **Dokumentasjon** | bl.a. livskontekst, totalbelastning i profil, snus/restitusjon (kunnskap), ukeplaner okt 2026 |
| **Denne rapporten** | `docs/coach/agent-modus-pilot-2026-10.md` |

Kjør lokalt (med `INTERVALS_API`):

```bash
python3 scripts/generate_coach_report.py --fetch --days 30
python3 scripts/export_intervals_plan_to_tp.py --start 2026-10-22 --end 2026-10-31 -o exports/tp-from-intervals
```

### Ikke i GitHub

| Innhold | Hvor det finnes |
|---------|------------------|
| **Hele chat-transkript** | Cursor agent-run (nettleser / Cursor historikk) |
| **Wellness/aktivitet CSV** (rå fetch) | `data/intervals/exports/` — **gitignored** |
| **Grafer generert på cloud VM** | `/opt/cursor/artifacts/` — lastes ned fra agent-run, ikke repo |
| **TrainingPeaks / Intervals innlogging** | Kun API-nøkkel lokalt / secrets — aldri i git |
| **Subjektive coaching-samtaler** (hytta, øl, bein, ukevalg) | Kun i chat + denne oppsummeringen |

**Konklusjon:** GitHub = **reproduiserbar verktøykasse + plan/docs**. Chat = **kontekst og beslutningshistorikk**.

---

## 2. Hva William brukte agenten til (pilot)

### A. Treningscoach (hovedrolle)

- **Uke 19–25 okt (Lillehammer):** build-uke, 6×5 / 5×3, sykkel Z2, ST04; justering når faktisk load og sykdom/helg kom inn.
- **TB-Score / wellness:** Henting fra Intervals, grafer, gul/grønn anbefaling (Plan B vs kvalitet).
- **TP vs Intervals CTL/ATL:** Forklaring av avvik (feil løp-TSS i TP før sonerettet).
- **Arbeidsmodell avklart:** William legger plan i **TP**; agent henter **ferdig trening + wellness fra Intervals** (Garmin-hub); ikke krav om auto-push til Intervals.
- **Hyttetur helg 24.–25. okt:** Analyse søvn/HRV/skritt vs logget TSS; mandag gul — **ikke** hard 6×5 terskel; presisering at **6×5 Z2/sub 150** er annet enn intervall.
- **Ukeplan i TP (skjermbilde):** Gjennomgang man–søn (SS tir, 6×3 fre, langtur+styrke) — forslag til flytting (myr vs SS, trimme styrke, volum ~10–11 t vs 12,5 t / 618 TSS).
- **Myr-løp:** Full øktprescription (stav, puls 134–147, Plan B).
- **Timing:** Trening etter jobb vs etter 19; styrke samme dag.

### B. Teknisk / TrainingPeaks

- **Eksport planlagte økter fra Intervals** (inkl. manuelle endringer), ikke bare repo-CSV.
- **TP import-begrensning:** Kun sykkel-`.zwo` i Library; løp/svøm som **sykkel-ZWO** + sportbytte i Builder; styrke via **TrainingDojo CSV**.
- **Leveranse:** Zip + mappe på GitHub; re-eksport med `--start` / `--end`.

### C. Faglige spørsmål (uten å logge skade)

- Lett iling fremside legg etter økt — differensiert fra krise, praktiske regler neste dag.

### D. Ikke i scope (ennå)

- Egen **hostet coach-app** (UI) — kun CLI/scripts i repo.
- Automatisk push til TP-kalender (API/token hos William).
- Garmin direkte API.

---

## 3. Viktige avklaringer under piloten

1. **«Ut oktober»** ble først misforstått som *fra* november; riktig eksport ble **22.–31. okt 2026**.
2. **Repo-uke 5** (26. okt) ≠ **TP-kalender** (SS tir, flere svøm, høyere TSS) — agent skal sparre mot **det du faktisk har i TP/Intervals**.
3. **Historisk FTP 410 W** er ikke intensitetsgrunnlag; swim limiter; sykkel tålmodighet.
4. **Subjektiv wellness** i TB-Score: default av (gaming-risiko).

---

## 4. Leveranser (sjekkliste)

- [x] `export_intervals_plan_to_tp.py` + README i eksportmappe  
- [x] `exports/tp-from-intervals` (okt-slutt 2026)  
- [x] Coach-rapport pipeline + TB-grafer  
- [x] 14-dagers hytte/belastning-dashboard script  
- [x] PR #17 med beskrivelse  
- [ ] Merge til `main` (William)  
- [ ] Ev. faste søndagsrapporter (cron / manuell rutine i `AGENTS.md`)

---

## 5. Evaluering av piloten

### Det som fungerte godt

- Rask **Intervals-fetch + TB + grafer** som beslutningsstøtte.
- **Eksport Intervals → TP** med riktig filformat (ZWO + Dojo).
- **Ærlig justering** (Plan B, hytte, gul score) uten krisemaksimering.
- **Norsk, OPV-inspirert** prescriptions når det gjaldt økter.

### Friksjon / læring

- Chat og **GitHub** er to spor — trenger **denne typen rapport** eller ukenotat i repo for kontinuitet.
- **Artifacts** (png) må enten committes (sjeldent) eller genereres på nytt med scripts.
- **TP-kalender** er sannhet for plan; repo `plans/` kan henge etter.

### Anbefaling neste fase («faktisk app»)

1. **Kort sikt:** Merge PR #17; legg inn i `AGENTS.md` rutine: søndag `generate_coach_report.py --fetch`.  
2. **Mellom sikt:** Lite **web/dashboard** (eller Streamlit) som kjører samme scripts — leser wellness/activities, viser TB + siste uke (ingen secrets i repo).  
3. **Lang sikt:** Valgfri TP `workouts/plan` API *hvis* William vil automatisere planlegging (token, scope, ikke default).

---

## 6. Referanser

| Ressurs | Lenke / sti |
|---------|-------------|
| PR | https://github.com/Wilste123/Lofoten_light/pull/17 |
| TP ZWO-import | `docs/trainingpeaks/importer-lop-svom-zwo.md`, `zwo-kun-sykkel.md` |
| Coach-regler | `AGENTS.md`, `knowledge/coach/` |
| Profil / mål | `docs/athlete/profile.md`, `goals.md` |
| Readiness | `docs/athlete/readiness-totalbelastning.md` |

---

*Generert som avslutning på Agent modus test-pilot, 26. okt 2026. Oppdater ved ny pilotperiode eller når app-arbeid starter.*
