# Intervals.icu plan-push — verifisert flyt (2026-09-24)

Dette er **den flyten som fungerte** første gang (William): 4 uker re-etablering på kalender, strukturerte sykkel-/løp-ZWO, søndags-UKENOTE, klar for Garmin/Wahoo-opplasting fra Intervals.

## Hemmeligheter

| Sted | Navn | Merk |
|------|------|------|
| **GitHub repo secrets** | `INTERVALS_API` | Rotert etter første test; **aldri** i git |
| Lokal utvikling | `.env` | `INTERVALS_API=` eller `INTERVALS_API_KEY=` |
| Cursor Cloud Agent | Miljø-secret | Samme navn `INTERVALS_API` |

Valgfritt: `INTERVALS_ATHLETE_ID=0` (anbefalt — API bruker «din» utøver; ikke nødvendig med `i303008` i URL).

## Soner i Intervals (før push)

Samme som TP: **FTP 210 W**, **løp 6:20/km**, **LTHR 165** — se `docs/athlete/profile.md`.

## Kommando (kilde til sannhet)

```bash
# Fra repo-root
python3 scripts/intervals_push_calendar.py --start 2026-09-28 --dry-run
python3 scripts/intervals_push_calendar.py --start 2026-09-28
```

**Resultat første kjøring:** 32 kalenderhendelser (28 økter + 4 UKENOTE), **14** med ZWO-struktur.

### Inputfiler (automatisk)

| Fil | Rolle |
|-----|--------|
| `plans/csv/trainingdojo-4uker-2026-09-28.csv` | Alle økter (dag 1–28) |
| `plans/csv/sykkel-zwo-kalender-4uker.csv` | Sykkel-ZWO på riktig **dato** |
| `plans/csv/trainingdojo-uke-notater-4uker-opv.csv` | Søndags **NOTE** kl. 19:00 |

### Idempotens

Hver økt får `external_id` `ll-agent-YYYYMMDD-dNNN`. Re-kjøring med `upsert=true` oppdaterer samme hendelser (ikke dupliser hele blokken uten grunn).

## Etter push — enheter

Intervals → **Settings** → **Connections**:

1. **Garmin** — *Upload planned workouts*
2. **Wahoo** — *Upload planned workouts*

Plan synkes typisk **~7 dager** frem til Connect/Wahoo Cloud, deretter til klokke/ELEMNT.

## Analyse / ukesopp (lesing)

```bash
python3 scripts/fetch_intervals_activities.py --days 7 \
  -o data/intervals/exports/uke.csv
python3 scripts/analyze_intervals_export.py data/intervals/exports/uke.csv
```

Send output + korte kommentarer til coach i Cursor (`docs/trainingpeaks/trener-feedback-syklus.md`).

## Teknisk (for vedlikehold)

- API: `POST /api/v1/athlete/0/events/bulk?upsert=true`, Basic auth `API_KEY:<secret>`
- Script: `scripts/intervals_lib.py`, `scripts/intervals_push_calendar.py`
- HTTP **User-Agent** er satt (uten den fikk cloud-miljø **403 / 1010** fra edge)
- ZWO: `file_contents` + `filename` på WORKOUT; `category: NOTE` for ukenotater

## Neste blokker

Ny plan-CSV + `--start <mandag>` → samme kommando. Agenten kan kjøre dette i cloud når `INTERVALS_API` er satt.

## Relatert

- [`integrasjon-intervals-icu.md`](integrasjon-intervals-icu.md) — helhet
- [`../athlete/profile.md`](../athlete/profile.md) — soner
