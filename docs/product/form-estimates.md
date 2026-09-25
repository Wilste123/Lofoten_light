# Form-estimater (FTP, VO₂)

Mål: **nyttige, konservative** estimater i appen — samme idé som kraft–varighet (MMP), tydelige begrensninger. Ikke full Morton 3P i v1.

## Gate — når estimat vises

| Betingelse | Effekt |
|------------|--------|
| **&lt; 5 kvalifiserende økter** | Ingen auto-estimat. UI: «Estimat etter 5 sykkeløkter med watt (eller koble Intervals med historikk).» **Testet FTP** kan vises uansett. |
| **≥ 5 økter med power** | Kjør `form_estimates` → `ftp_estimated` + confidence. |
| **ICU koblet med historikk** | Ved sync: tell sykkel med power siste 90 d; ≥ 5 → gate åpnes. |

**Kvalifiserende økt (sykkel):** aktivitet med watt-data, varighet ≥ 20 min. Recovery-spin teller mot **volum-gate**, men er ikke max-effort-kilde alene.

## FTP-estimat (MMP)

Basert på 20-min ≈ 95 % FTP (Coggan/Allen) og at korte maksdrag overdriver uten lengre anker.

1. Fra aktiviteter siste **90 dager**: maks gjennomsnittlig power for vinduer **5, 8, 12, 20 min** (MMP).
2. Kandidater (konservative faktorer):
   - 20 min: `P_20 × 0.95`
   - 12 min: `P_12 × 0.90`
   - 8 min: `P_8 × 0.88`
   - 5 min: `P_5 × 0.85` — kun hvis ingen lengre vindu; confidence = **lav**
3. **Valgt:** `min(kandidater fra vinduer ≥ 8 min)` hvis noen; ellers `min(alle)` — heller lavt.
4. **Kvalitetsfilter:** power-CV (σ/mean) &lt; 12 % over vinduet, ellers lav confidence.
5. **Vs testet FTP:** estimat vises ikke høyere enn `ftp_tested × 1.05` uten badge; hvis estimat &gt; testet + 8 % → cap / «ta 20-min test».

**Confidence:** `høy` (20-min MMP), `medium` (8–12 min), `lav` (kun 5–8 min / tynt datasett).

## VO₂-estimat (strengere gate)

**Gate VO₂:** samme 5 økter + **kroppsvekt (kg)** + **alder** + minst ett jevnt sykkelsegment ≥ **6 min** med stabil HR (minutt 5–6 innen 5 slag) og power-CV &lt; 8 %.

Uten alder eller steady HR: **ikke vis VO₂**.

Formel (ACSM-inspirert submax → ekstrapolert; dokumenter enheter i kode):

- `%HRR = (HR_steady − HR_rest) / (HR_max_est − HR_rest)` med `HR_max_est = 220 − alder`
- VO₂max (ml/kg/min) fra steady power og %HRR / body mass (se `form_estimates.py`)

## API / lagring

- Modul: `services/coach-api/form_estimates.py` + `form_from_intervals.py` (ICU 90d + power-curve)
- Overview kaller `resolve_form_estimates` (ikke tom liste) og persisterer når gate ≥5
- `POST /v1/form/recompute` oppdaterer lagrede felter eksplisitt
- Overblikk/Compliance/chat leser **lagrede** estimater + disclaimer ved lav confidence

## Kilder

- [FTP uten test — Adapt Cycling](https://www.adaptcycling.com/guides/ftp-without-a-test)
- [Cycling Analytics — CP-modell](https://www.cyclinganalytics.com/blog/2020/01/power-model-and-other-new-things)
- [Intervals.icu — eFTP / Morton 3P](https://forum.intervals.icu/t/model-power-curve/1007)
- [Åstrand–Rhyming](https://www.topendsports.com/testing/tests/astrand.htm) — fremtidig submax-test, ikke MVP-beregning
