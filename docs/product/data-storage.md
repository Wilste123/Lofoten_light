# Datalagring — coach-web MVP

## Kort svar

**SQLite + Fly volume** (eller lokal fil) er eneste datastore i MVP.  
**Ikke Supabase** før eksplisitte scale-triggere.

## Hva lagres hvor

| Data | Hvor i MVP | Hvorfor |
|------|------------|---------|
| `athlete_context` (navn, trener, farge, mål, avtaler, skade, **ernæring/GI**, test-FTP, vekt/alder, **sesongmål**) | SQLite | Appens SoT — ikke Intervals |
| `plan_blocks` (grovplan / bulk) | SQLite | Makro/meso — se [periodization-overview.md](periodization-overview.md) |
| Profilfil markdown | `data/athletes/{id}/profile.md` | Cursor-coach + LLM leser person, ikke bare William |
| Chat-historikk (siste N turner) | SQLite | Kort minne for én LLM-tur |
| Intervals API-nøkkel + athlete-id | SQLite (`athlete_secrets`) via **Du**-fane / `PUT /v1/athlete/me/intervals` | Kun server; aldri `localStorage` eller `.env` for web |
| `OPENAI_API_KEY` | `services/coach-api/.env` | Server-wide chat — ikke per utøver |
| Form-estimater | SQLite (felter på athlete) | Resultat av `form_estimates` |
| Aktivitets-cache (90 d power) | SQLite eller fil under `data/athletes/{id}/` | Unngå full ICU-refetch |
| Kunnskap / ukeplaner | Git (`knowledge/`, `plans/`) | Uendret |
| Økter / kalenderdetaljer | Intervals.icu | Uendret |
| `training_pairs` + `coordinated_sessions` | SQLite | Fase 3 — schema klar, tom i fase 1–2 |

Klient: kun `athlete_id` (+ evt. invite-token) i `localStorage`.

## Stack

```
Browser → coach-api → SQLite (volume)
                   → Intervals.icu (fase 2+)
                   → knowledge/ (git, trimmet i prompt)
```

- Fil: `data/coach.db` (gitignore) bak `DATABASE_PATH`.
- Deploy: Fly volume på `/data`, `DATABASE_PATH=/data/coach.db`.
- Backup: `sqlite3 .backup` i runbook — ikke CDC.

## Schema (skisse)

```sql
-- athletes: id (uuid), display_name, timezone, coach_display_name,
--   coach_personality, coach_style_note, accent_color,
--   goal_text, injury_notes, agreements_json, weekly_focus,
--   ftp_tested, ftp_tested_at, ftp_estimated, vo2_estimate,
--   estimate_confidence, estimate_updated_at, estimate_source,
--   weight_kg, age_years, notes,
--   season_swim_hours_target, season_bike_hours_target,
--   season_run_hours_target, season_strength_hours_target,
--   season_start_date, goal_race_date,
--   created_at, updated_at

-- plan_blocks: id, athlete_id, title, theme, start_date, end_date,
--   weekly_hours, sort_order, created_at, updated_at

-- athlete_secrets: athlete_id, intervals_api_key, intervals_athlete_id, updated_at

-- messages: id, athlete_id, role (user|assistant|system), content, created_at

-- invites: id, token_hash, created_by, status, expires_at

-- training_pairs (fase 3): id, athlete_a_id, athlete_b_id, status, created_at

-- coordinated_sessions (fase 3): id, pair_id, starts_at, ends_at, venue,
--   discipline, athlete_a_workout_note, athlete_b_workout_note,
--   athlete_a_confirmed, athlete_b_confirmed
```

## Når bytte til Supabase

Bytt **først når** én av disse er sann:

1. Samme utøver på flere enheter trenger server-login uten ny invite.
2. ≥ 2 API-instanser (horisontal scale).
3. Team-admin / RLS for flere coach-tenants.

Oppgraderingssti: samme SQL-skjema → Postgres; bytt connection string; behold API-kontrakt. Ingen Supabase Realtime/Edge i MVP-kode.

## Sikkerhet (minimal)

- Intervals-nøkler kun server; krypter med `SECRETS_KEY` før flere utenfor vennegjengen.
- Invite-tokens: hash i DB.
- Rate limit på `/v1/chat`.
- Ingen offentlig signup uten token.
