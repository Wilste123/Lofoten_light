# CSV / Excel

Åpne filene i Excel eller Google Sheets. For **TrainingPeaks**, se [importere-plan-norsk.md](../../docs/trainingpeaks/importere-plan-norsk.md).

## TrainingDojo → TrainingPeaks (kalender)

| Fil | Hva |
|-----|-----|
| **`trainingdojo-uke-notater-4uker-opv.csv`** | **4 ukentlige coach-notater (søndag)** — kun fokus/ukesopp, ikke økter. Start **2026-09-28**. |
| **`intervals-bia-daily.csv`** | Smartvekt **daglig** → `push_intervals_wellness.py` |
| **`intervals-bia-ukesnitt.csv`** | **7-dagers snitt** søndag + OPV-linje → `--weekly` push |
| **Intervals push** | `./scripts/intervals_push_uke8_arsende.sh` eller per-blokk — se **`docs/integrations/intervals-import.md`** og **`docs/trainingpeaks/intervals-push-verified.md`** (secret `INTERVALS_API`) |
| `trainingdojo-4uker-uten-sykkel.csv` | Økter svøm/løp/styrke (uten sykkel) — hybrid med ZWO |
| `trainingdojo-4uker-2026-09-28.csv` | B0 uke 1–4 (start 28.09) |
| **`trainingdojo-4uker-2026-10-26.csv`** | **B1 uke 5–8** (start 26.10) + OPV myr/elghufs/rest |
| `trainingdojo-uke-notater-4uker-opv-2026-10-26.csv` | B1 søndags-UKENOTE |
| **`trainingdojo-5uker-2026-11-23.csv`** | **B2/B3 uke 9–13** (start 23.11) |
| **`trainingdojo-uke-notater-5uker-opv-2026-11-23.csv`** | Uke 9–13 UKENOTE |
| **`sykkel-zwo-kalender-5uker-2026-11-23.csv`** | Sykkel-ZWO uke 9–13 |
| `sykkel-zwo-kalender-4uker-2026-10-26.csv` | Sykkel-ZWO datoer B1 |
| `trainingdojo-4uker-uten-sykkel-opv.csv` | Valgfritt: lange øktbeskrivelser uten sykkel |
| `trainingdojo-4uker-2026-09-28-opv.csv` | Valgfritt: alle økter med lang tekst |

**Sykkel watt:** `sykkel-zwo-kalender-4uker.csv` + `workouts/zwo/bike/*.zwo`

Lesbare ukenotater: [../uke-notater/2026-09-28-blokk-4uker.md](../uke-notater/2026-09-28-blokk-4uker.md)

## Ark / oversikt

| Fil | Innhold |
|-----|---------|
| `ukeplan-2026-09-28-4uker.csv` | Dag-for-dag uke 1–4 (flere kolonner) |
| `12mnd-periodisering.csv` | Grov 12-måneders plan (ikke kalender-import) |

Markdown: `plans/2026-09-28-uke-*.md`, `plans/blokker-periodisering-2026-2027.md`
