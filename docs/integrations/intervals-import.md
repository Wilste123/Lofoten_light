# Intervals.icu — import av plan (uke 8 → årsskifte 2026)

William: **Intervals.icu er primær kalender** for plan fra repo. Denne guiden dekker uke **8** (B1 recovery) gjennom uke **13** (B3 jul) plus **bolk-markører**.

Eksisterende verifisert flyt (API, secrets, soner): [`docs/trainingpeaks/intervals-push-verified.md`](../trainingpeaks/intervals-push-verified.md) og [`docs/trainingpeaks/integrasjon-intervals-icu.md`](../trainingpeaks/integrasjon-intervals-icu.md).

Makroplan og uke-tabeller: [`plans/2026-uke08-til-arsende.md`](../../plans/2026-uke08-til-arsende.md).

---

## 1. Forbered Intervals (én gang)

1. **Soner** (Settings → Zones): **FTP 210 W**, løp **6:20/km**, **LTHR 165** — [`docs/athlete/profile.md`](../athlete/profile.md).
2. **API-nøkkel:** Settings → **Developer settings** → Create API key.  
   Auth: HTTP Basic, brukernavn `API_KEY`, passord = nøkkelen ([Intervals API-tråd](https://forum.intervals.icu/t/api-access-to-intervals-icu/609)).
3. **Lokalt** (`.env`, ikke i git):

   ```bash
   cp .env.example .env
   # fyll inn:
   INTERVALS_API=din_nøkkel_her
   INTERVALS_ATHLETE_ID=0
   ```

   Alternativt env-navn: `INTERVALS_API_KEY`. GitHub/Cursor secret: **`INTERVALS_API`** (samme verdi).

4. **Garmin/Wahoo** (etter push): Settings → Connections → **Upload planned workouts** (~7 dager frem).

---

## 2. Hva som pushes (rekkefølge)

| Steg | Innhold | Kilde | Script |
|------|---------|--------|--------|
| **A** | B1 uke **5–8** (uke **8** = recovery 16.–22.11) | `plans/csv/trainingdojo-4uker-2026-10-26.csv` + sykkel-ZWO + UKENOTE | `intervals_push_calendar.py --start 2026-10-26` |
| **B** | B2/B3 uke **9–13** (til 27.12) | `plans/csv/trainingdojo-5uker-2026-11-23.csv` + tilhørende notater/ZWO | `--start 2026-11-23` |
| **C** | **Bolk-grenser** (B2 start, B2 slutt, B3 start) | `plans/calendar/2026-bolk-markers.ics` | `intervals_push_bolk.py --only-block-boundaries` |

**Ikke dupliser ukentlige bolk-sammendrag** hvis du allerede har UKENOTE søndag 19:00 fra steg A/B. Valgfritt: hele ICS (Google/Apple) eller `--ics` uten `--only-block-boundaries` for uke-all-day NOTER i Intervals.

### Idempotens

- Økter/notater: `external_id` `ll-agent-YYYYMMDD-dNNN` — re-push med `upsert=true` (standard).
- Bolk: `ll-agent-bolk-<uid>` fra ICS.

Fjern agent-plan uten å slette fullførte aktiviteter:

```bash
python3 scripts/intervals_delete_calendar.py --start 2026-10-26 \
  --plan plans/csv/trainingdojo-4uker-2026-10-26.csv \
  --notes plans/csv/trainingdojo-uke-notater-4uker-opv-2026-10-26.csv

python3 scripts/intervals_delete_calendar.py --start 2026-11-23 \
  --plan plans/csv/trainingdojo-5uker-2026-11-23.csv \
  --notes plans/csv/trainingdojo-uke-notater-5uker-opv-2026-11-23.csv
```

(Bolk-NOTE fjernes manuelt i Intervals eller ved å slette på `external_id`-prefiks `ll-agent-bolk-`.)

---

## 3. Kommandoer (William)

Fra repo-root, etter `export INTERVALS_API=…` (eller `source .env`):

```bash
# Test alt uten API
./scripts/intervals_push_uke8_arsende.sh --dry-run

# Live push (3 steg i ett)
./scripts/intervals_push_uke8_arsende.sh
```

Eller manuelt:

```bash
python3 scripts/intervals_push_calendar.py --start 2026-10-26 \
  --plan plans/csv/trainingdojo-4uker-2026-10-26.csv \
  --notes plans/csv/trainingdojo-uke-notater-4uker-opv-2026-10-26.csv \
  --bike-calendar plans/csv/sykkel-zwo-kalender-4uker-2026-10-26.csv \
  --dry-run

python3 scripts/intervals_push_calendar.py --start 2026-11-23 \
  --plan plans/csv/trainingdojo-5uker-2026-11-23.csv \
  --notes plans/csv/trainingdojo-uke-notater-5uker-opv-2026-11-23.csv \
  --bike-calendar plans/csv/sykkel-zwo-kalender-5uker-2026-11-23.csv \
  --dry-run

python3 scripts/intervals_push_bolk.py \
  --ics plans/calendar/2026-bolk-markers.ics \
  --only-block-boundaries \
  --dry-run
```

Fjern `--dry-run` når tall og datoer ser riktige ut.

**Forventet (dry-run):** ~35 hendelser (B1-blokk) + ~40 (uke 9–13) + **3** bolk-NOTE; sykkel med ZWO på datoer i `sykkel-zwo-kalender-*.csv`.

---

## 4. Bolk: API vs ICS vs notater

| Metode | Best for |
|--------|----------|
| **`intervals_push_bolk.py`** | Synlige **NOTE**-markører i Intervals (blokkgrenser); idempotent med `external_id`. |
| **ICS import** (`plans/calendar/2026-bolk-markers.ics`) | Google/Apple-kalender, all-day ukesammendrag; Intervals Settings → Import calendar hvis du vil ha hendelsene der uten script. |
| **`trainingdojo-uke-notater-*.csv`** | **Coach-UKENOTE** søndag 19:00 (OPV-tekst) — ikke bare bolk-kode. |
| **`2026-uke-bolk.csv`** | Oversikt i Excel; valgfritt `--bolk-csv` til script (mandag 06:00 NOTE — overlapper ICS uke-events). |

Kanonisk ICS: [`plans/calendar/2026-bolk-markers.ics`](../../plans/calendar/2026-bolk-markers.ics). Kopi/merknad: [`plans/calendar/intervals/README.md`](../../plans/calendar/intervals/README.md).

---

## 5. Teknisk (repo-kilde, ikke gjettet)

| Emne | Detalj |
|------|--------|
| Bulk kalender | `POST /api/v1/athlete/{id}/events/bulk?upsert=true` — [`scripts/intervals_lib.py`](../../scripts/intervals_lib.py) |
| Auth | `Authorization: Basic base64(API_KEY:<secret>)` |
| Athlete id | `0` = autentisert utøver (`INTERVALS_ATHLETE_ID`) |
| WORKOUT | Sykkel: ZWO i `file_contents`; løp/svøm: `workouts/planned/*/*.txt` med `---intervals---` |
| NOTE | UKENOTE + bolk-script (`category: NOTE`) |

---

## 6. Etter import

1. Sjekk Intervals-kalender uke 8–13: datoer, varighet, sykkel-struktur (Wahoo/Garmin sync).
2. Etter **CSS-test** (uke 10): oppdater profil/soner.
3. Ukentlig analyse: [`IMPORT-INTERVALS.md`](../../IMPORT-INTERVALS.md) (`fetch_intervals_activities.py`).

---

## Relatert

- [`plans/csv/README.md`](../../plans/csv/README.md) — CSV-inventar  
- [`knowledge/coach/intervals-tekst-opv.md`](../../knowledge/coach/intervals-tekst-opv.md) — tekststil i beskrivelser
