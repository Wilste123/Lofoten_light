# Intervals.icu exports (2026-10-26)

Athlete: `i303008` · exported: `2026-10-26T14:11:18.199816+00:00`

## Files

| File | Range | Contents |
|------|-------|----------|
| `wellness.csv` | 2025-10-27 … 2026-10-26 | Daily wellness (sleep, HRV, weight, readiness, CTL/ATL, …) — **365 dager** |
| `activities.csv` | **full history** (API) | Completed activities summary CSV (**840** rows; Intervals CSV endpoint ignores date filter) |
| `activities.json` | ~180 d | Date-filtered JSON (44 aktiviteter) — ids brukt til laps |
| `activities-365d.json` | ~365 d | Date-filtered JSON (61 aktiviteter) |
| `events.csv` / `events.json` | 2026-09-27 … 2026-12-25 | Kalender (WORKOUT/NOTE/TARGET/…) |
| `events-workouts.json` | same | Kun category=WORKOUT |
| `laps.csv` | aktiviteter ≥ 2026-07-29 | Alle `icu_intervals` (478 rader) |
| `laps/<activity_id>.csv` | same | Én fil per aktivitet (37 filer) |
| `streams-summary.csv` | ≥ 2026-07-29 | Kolonner/rader per streams.csv (ikke full streams) |
| `export-meta.json` | — | Ranges, stats, gaps |

## Laps-skjema

Fra `GET /api/v1/activity/{id}?intervals=true` → `icu_intervals[]`.

Nøkkelkolonner: `activity_id`, `interval_index`, `type` (WORK/REST/…), `label`, `start_time`/`end_time` (s), `moving_time`, `distance`, power (`average_watts`, `weighted_average_watts`, `intensity`, `zone`), HR, kadens, fart, `training_load`.

## Oppdater / refresh

```bash
export INTERVALS_ATHLETE_ID=i303008
export INTERVALS_API_KEY=…   # eller INTERVALS_API — aldri commit
python3 scripts/export_intervals_maximal.py
# valgfritt: --wellness-days 365 --activities-days 180 --laps-days 90
```

Context pack (bruker nyeste CSV under `exports/` / `latest/`):

```bash
python3 scripts/build_context_pack.py --days 14
# live fetch (pack-*.csv gitignored):
python3 scripts/build_context_pack.py --fetch-icu --days 14
```

## Gaps / merknader

- Full sekund-for-sekund `streams.csv` er **ikke** committed (størrelse); kun `streams-summary.csv`.
- Interval-/laps-detalj kun siste **90** dager; eldre økter ligger i `activities.csv`.
- `activities.csv` = full historikk fra Intervals; JSON-filene er datofiltrert.
- Ikke commit API-nøkler.
