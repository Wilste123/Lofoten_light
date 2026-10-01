# Supabase / Postgres — coach-api

Branch: **`supabase`**. App SoT moves from SQLite Fly volume → Postgres when `DATABASE_URL` (or `SUPABASE_DB_URL`) is set.

## Two-tier plan model (baked in)

| Layer | Storage | Horizon |
|-------|---------|---------|
| **Grovplan** | `plan_blocks` (`layer=grov`, hours band, `session_types_json`) | ~to goal / ~12m meso |
| **Detaljplan** | `plan_windows` + `planned_sessions` (`plan_tier=detalj`) | ~`DETAIL_WEEKS` (4) rolling |
| **ICU sync** | From stored detalj / near window only | `ICU_SYNC_WEEKS` (2) |

Human Coach only: forslag → preview → confirm → lagre → sync. **Never** silent year rewrite or silent Intervals write.

### Roll-forward constants

| Constant | Default | Meaning |
|----------|---------|---------|
| `DETAIL_WEEKS` | 4 | Detalj window length |
| `ROLL_TRIGGER_DAYS_LEFT` | 14 | Offer when ≤14d left in current detalj |
| `ROLL_TRIGGER_BLOCK_ELAPSED_DAYS` | 14 | Or ≥14d into current meso block without coverage |
| `ROLL_COOLDOWN_DAYS` | 5 | No re-offer within 5d of last offer/confirm |
| Explicit «neste måned / rull» | — | Bypasses cooldown |

Timestamps: `athletes.detalj_roll_offered_at` / `detalj_roll_confirmed_at`.

Endpoints: `GET /v1/athlete/me/plan/roll/check`, `POST /v1/athlete/me/plan/roll/confirm`, chat attaches `plan_roll` card.

## What William creates in Supabase dashboard

1. New project (region close to Fly `ams` if possible).
2. **Project Settings → Database → Connection string** (URI). Prefer **Session mode** pooler or direct `postgresql://…` for the API (long-lived FastAPI process).
3. Paste into Fly / local env as `DATABASE_URL` (or `SUPABASE_DB_URL`).
4. Optional: **Settings → API** → copy `SUPABASE_URL`, `anon` key, `service_role` key (API uses Postgres URL primarily; keys reserved for future Auth / client).
5. Run SQL: `services/coach-api/migrations/001_supabase_schema.sql` in SQL editor (schema + RLS).  
   Alternatively boot API once with `DATABASE_URL` set — `init_db()` creates tables (RLS still needs the SQL file).
6. Map Auth users later via `athletes.auth_user_id` (UUID text). Until then API continues `X-Athlete-Id` + service connection (bypasses RLS).

## Env vars

| Var | Required | Purpose |
|-----|----------|---------|
| `DATABASE_URL` | for Postgres | Primary connection string (wins over SQLite) |
| `SUPABASE_DB_URL` | alias | Same as DATABASE_URL |
| `SUPABASE_URL` | optional | Project URL metadata |
| `SUPABASE_ANON_KEY` | optional | Future client Auth |
| `SUPABASE_SERVICE_ROLE_KEY` | optional | Future admin / bypass patterns |
| `DATABASE_PATH` | SQLite fallback | Used when no DATABASE_URL |

Never invent secrets — leave empty until William pastes real values.

### Fly

```bash
fly secrets set DATABASE_URL='postgresql://…' --app lofoten-coach
# After cutover, SQLite volume is unused for plan rows (profile.md still on /data/athletes).
fly deploy --app lofoten-coach
```

`fly.toml` still mounts `/data` for `ATHLETES_DATA_DIR` (profile.md). Volume is not required for plan DB once on Supabase.

## Local / tests

```bash
# SQLite (default unit tests)
cd services/coach-api && python3 -m pytest tests/ -q

# Postgres integration (optional)
export DATABASE_URL='postgresql://coach:coach@127.0.0.1:5432/coach_test'
python3 -m pytest tests/test_supabase_postgres.py tests/test_two_tier_plan.py -q
```

## Charts (real data only)

| Series | Source | Label |
|--------|--------|-------|
| Past volume / compliance | Intervals **activities** | gjennomført |
| CTL / ATL | Intervals **wellness** | never LLM-invented |
| Future volume | DB `planned_sessions` | **planlagt** |

Dashboard attaches `charts.volume` (executed) + `charts.volume_planned` + `charts.truth`. Chat must not invent CTL/ATL that disagree with these sources.
