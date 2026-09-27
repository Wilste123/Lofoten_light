# Importer William fra repo til coach-web

Seed speiler det som allerede er avtalt i **lofoten_light** git (`docs/athlete/`, `plans/`) inn i runtime: SQLite + `data/athletes/{id}/profile.md` + `plan_blocks`. Så ser app-coachen samme kontekst som Cursor-coachen.

**Branch:** `cursor/web-coach-mvp-42ac` · CLI er nok for MVP; admin-API er valgfritt.

## Kjør seed

Fra repo-root (anbefalt):

```bash
python3 services/coach-api/scripts/seed_william_from_repo.py
# eller:
cd services/coach-api && python3 seed_from_repo.py
```

Dry-run (ingen skriving):

```bash
python3 services/coach-api/scripts/seed_william_from_repo.py --dry-run
```

Nyttige flagg:

| Flagg | Default | Betydning |
|-------|---------|-----------|
| `--display-name` | William | Idempotent oppslag (eller fast `--seed-id`) |
| `--coach-name` | Ole | App-trenernavn (produkt-onboarding default er Rocky for nye) |
| `--seed-id` | `william-lofoten` | Fast athlete id |
| `--db` | `data/coach.db` | SQLite |
| `--athletes-dir` | `data/athletes` | Profilfil-rot |
| `--athlete-docs` | `docs/athlete` | Override (tester) |
| `--plans-dir` | `plans` | Override (tester) |

Scriptet printer `athlete_id` og en invite-vennlig bootstrap-hint. Re-kjør er trygt: samme utøver oppdateres.

### Valgfri admin-API

Sett `ADMIN_SEED_TOKEN` i `services/coach-api/.env`, deretter:

```bash
curl -s -X POST http://127.0.0.1:8000/v1/admin/seed-from-repo \
  -H "Content-Type: application/json" \
  -H "X-Admin-Seed-Token: $ADMIN_SEED_TOKEN" \
  -d '{"dry_run": false}'
```

Uten token → 503 (bruk CLI).

## Hva importeres

| Kilde (git) | Runtime |
|-------------|---------|
| `docs/athlete/profile.md` (+ goals, soner, plager, kropp-pekere) | Rik `data/athletes/{id}/profile.md` + SQLite-felt |
| Mål / race | `goal_text`, `goal_race_date` (default **2027-08-20**) |
| Skade (`plager-rygg-isjas.md`) | `injury_notes` |
| Avtaler (utledet + evt. ## Avtaler) | `agreements` / `agreements_json` |
| Uke-notater B0 | `weekly_focus` |
| Soner FTP 210 W | `ftp_tested` / `ftp_tested_at` — **ikke** 410 W |
| `plans/blokker-periodisering-2026-2027.md` | `plan_blocks` B0–B10 (datoer der de finnes / sekvensielt) |
| Årsmål 750–800 t | `season_*_hours_target` (se antakelser under) |

Chat leser **on-disk** `profile.md` via `load_profile_md` (avtaler + speil-seksjoner), med fallback til SQLite-mal.

## Hva blir igjen kun i git

- Hele `knowledge/` (chat får kun trimmet `knowledge_ctx`)
- `workouts/zwo/` og øvrig øktbibliotek
- `plans/csv/`, detaljerte ukeplaner, TrainingDojo-import
- Intervals-nøkler / `.env` (aldri seedet)
- Pondus (ikke i scope)

## Antakelser (sesongtimer)

Midtpunkt **775 t** av 750–800. Fordeling fra `plans/2026-2027-12mnd-periodisering.md` (% snitt år):

| Disiplin | % | Timer (seed) |
|----------|---|--------------|
| Sykkel | ~50 % | ~388 |
| Løp | ~30 % | ~232 |
| Svøm | ~16 % | ~124 |
| Styrke | rest | ~31 |

`season_start_date` = **2026-09-28** (B0). Juster i Du-fanen ved behov.

## Idempotens

1. Finn `william-lofoten` i DB, ellers `display_name=William`, ellers opprett med seed-id.
2. **Første seed:** opprett felter + upsert `plan_blocks` (`{athlete_id}-b0` … `-b10`) + rik `profile.md`, sett `setup_completed=1`.
3. **Re-seed / boot** når `setup_completed=1`: **bevar** goals, plan_blocks, runtime `profile.md` og `athlete_secrets` (Intervals). Kun sikre username + flagget. Slik overskriver ikke Fly-redeploy en tilpasset William-profil.
4. Uten `setup_completed` (f.eks. etter Du → SLETT): full import fra repo igjen.

## Etter seed — sjekk i app

1. Bootstrap / lim inn `athlete_id` i session.
2. Overblikk: grovplan B0, dager til race, sesongmål.
3. Chat: spør om avtaler / rygg — svaret skal speile profilfilen (ikke generisk onboarding).
