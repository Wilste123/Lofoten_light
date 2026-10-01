# Datalagring — coach-web MVP

## Kort svar

**Branch `supabase`:** Postgres via `DATABASE_URL` / Supabase when set; otherwise SQLite + Fly volume.  
Two-tier SoT: **grovplan** (`plan_blocks`) + **detaljplan** (`plan_windows` + `planned_sessions`).  
Full recipe: [supabase.md](supabase.md). William opened an explicit Supabase try (2026-10-01).

## Hva lagres hvor

| Data | Hvor i MVP | Hvorfor |
|------|------------|---------|
| `athlete_context` (navn, trener, farge, mål, avtaler, skade, **ernæring/GI**, test-FTP, vekt/alder, **sesongmål**, **`show_body_metrics`**) | DB `athletes` | Appens SoT — ikke Intervals |
| **Grovplan** (`plan_blocks`, `layer=grov`) | DB | Makro/meso → mål; hours band + session-type mix |
| **Detaljplan** (`plan_windows` + `planned_sessions`) | DB | ~4 uker konkrete økter; ICU sync near window |
| Visual builder steps (`steps_json`) | DB `planned_sessions` | Warmup/work/recover/cooldown |
| Roll-forward timestamps | `athletes.detalj_roll_*` | Cooldown for neste detaljvindu |
| `session_completions` (øktlogg status/grunn) | DB | App-only — se [dashboard-okter.md](dashboard-okter.md) |
| Profilfil markdown | `data/athletes/{id}/profile.md` | Cursor-coach + LLM leser person, ikke bare William |
| Chat-historikk (siste N turner) | DB `messages` | Kort minne for én LLM-tur |
| Intervals API-nøkkel + athlete-id | DB `athlete_secrets` via **Du**-fane / `PUT /v1/athlete/me/intervals` | Kun server; aldri `localStorage` eller `.env` for web |
| `OPENAI_API_KEY` | `services/coach-api/.env` / Fly secrets | Server-wide chat — ikke per utøver |
| Form-estimater | DB (felter på athlete) | Resultat av `form_estimates` |
| Charts gjennomført / CTL/ATL | Intervals activities / wellness | Real data only |
| Charts planlagt volum | DB `planned_sessions` | Labeled *planlagt* |
| Kunnskap / ukeplaner | Git (`knowledge/`, `plans/`) | Uendret |
| `training_pairs` + `coordinated_sessions` | DB | Fase 3 — schema klar, tom i fase 1–2 |

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
