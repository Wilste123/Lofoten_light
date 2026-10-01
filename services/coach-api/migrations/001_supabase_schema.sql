-- Lofoten Coach — Supabase / Postgres schema (1:1 with coach-api db.SCHEMA)
-- Two-tier: grovplan = plan_blocks; detaljplan = plan_windows + planned_sessions
-- Apply in Supabase SQL editor (or psql) as a privileged role, then enable RLS.

-- Optional Auth helper
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS athletes (
  id TEXT PRIMARY KEY,
  username TEXT UNIQUE,
  display_name TEXT NOT NULL,
  timezone TEXT DEFAULT 'Europe/Oslo',
  coach_display_name TEXT NOT NULL DEFAULT 'Rocky',
  coach_personality TEXT DEFAULT 'direkte',
  coach_style_note TEXT DEFAULT '',
  accent_color TEXT DEFAULT '#1a6b4a',
  goal_text TEXT DEFAULT '',
  injury_notes TEXT DEFAULT '',
  agreements_json TEXT DEFAULT '[]',
  weekly_focus TEXT DEFAULT '',
  ftp_tested DOUBLE PRECISION,
  ftp_tested_at TEXT,
  ftp_estimated DOUBLE PRECISION,
  vo2_estimate DOUBLE PRECISION,
  estimate_confidence TEXT,
  estimate_updated_at TEXT,
  estimate_source TEXT,
  weight_kg DOUBLE PRECISION,
  age_years INTEGER,
  sport TEXT DEFAULT 'triathlon',
  schedule_notes TEXT DEFAULT '',
  nutrition_ibs TEXT DEFAULT 'no',
  nutrition_gluten TEXT DEFAULT 'none',
  nutrition_lactose INTEGER DEFAULT 0,
  nutrition_other_restrictions TEXT DEFAULT '',
  nutrition_notes TEXT DEFAULT '',
  notes TEXT DEFAULT '',
  season_swim_hours_target DOUBLE PRECISION,
  season_bike_hours_target DOUBLE PRECISION,
  season_run_hours_target DOUBLE PRECISION,
  season_strength_hours_target DOUBLE PRECISION,
  season_start_date TEXT,
  goal_race_date TEXT,
  show_body_metrics INTEGER DEFAULT 0,
  setup_completed INTEGER DEFAULT 0,
  athlete_type TEXT DEFAULT '',
  athlete_type_notes TEXT DEFAULT '',
  allowed_disciplines TEXT DEFAULT '',
  sessions_per_week INTEGER,
  fitness_notes TEXT DEFAULT '',
  auth_user_id TEXT,
  detalj_roll_offered_at TEXT,
  detalj_roll_confirmed_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_completions (
  id TEXT PRIMARY KEY,
  athlete_id TEXT NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
  external_session_id TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'intervals',
  session_name TEXT DEFAULT '',
  session_date TEXT,
  discipline TEXT DEFAULT '',
  status TEXT NOT NULL,
  reason TEXT DEFAULT '',
  note TEXT DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (athlete_id, external_session_id)
);

-- GROVPLAN (macro / meso → goal)
CREATE TABLE IF NOT EXISTS plan_blocks (
  id TEXT PRIMARY KEY,
  athlete_id TEXT NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
  title TEXT NOT NULL DEFAULT '',
  theme TEXT DEFAULT '',
  start_date TEXT,
  end_date TEXT,
  weekly_hours DOUBLE PRECISION,
  hours_min DOUBLE PRECISION,
  hours_max DOUBLE PRECISION,
  session_types_json TEXT DEFAULT '{}',
  layer TEXT DEFAULT 'grov',
  sort_order INTEGER DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- DETALJPLAN window metadata (~4 weeks rolling)
CREATE TABLE IF NOT EXISTS plan_windows (
  id TEXT PRIMARY KEY,
  athlete_id TEXT NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
  kind TEXT NOT NULL DEFAULT 'detalj',
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  source TEXT NOT NULL DEFAULT 'setup',
  readiness_json TEXT DEFAULT '{}',
  block_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS planned_sessions (
  id TEXT PRIMARY KEY,
  athlete_id TEXT NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
  session_date TEXT NOT NULL,
  sport TEXT NOT NULL DEFAULT 'other',
  name TEXT NOT NULL DEFAULT '',
  description TEXT DEFAULT '',
  duration_minutes INTEGER,
  start_time TEXT DEFAULT '07:00',
  planned_path TEXT DEFAULT '',
  phase TEXT DEFAULT '',
  block_id TEXT,
  window_id TEXT,
  external_id TEXT,
  source TEXT NOT NULL DEFAULT 'plan',
  status TEXT NOT NULL DEFAULT 'planned',
  plan_tier TEXT NOT NULL DEFAULT 'detalj',
  session_type TEXT DEFAULT '',
  steps_json TEXT DEFAULT '[]',
  sort_order INTEGER DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS athlete_secrets (
  athlete_id TEXT PRIMARY KEY REFERENCES athletes(id) ON DELETE CASCADE,
  intervals_api_key TEXT,
  intervals_athlete_id TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  athlete_id TEXT NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invites (
  id TEXT PRIMARY KEY,
  token_hash TEXT NOT NULL,
  created_by TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  expires_at TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS training_pairs (
  id TEXT PRIMARY KEY,
  athlete_a_id TEXT NOT NULL REFERENCES athletes(id),
  athlete_b_id TEXT NOT NULL REFERENCES athletes(id),
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS coordinated_sessions (
  id TEXT PRIMARY KEY,
  pair_id TEXT NOT NULL REFERENCES training_pairs(id) ON DELETE CASCADE,
  starts_at TEXT NOT NULL,
  ends_at TEXT,
  venue TEXT,
  discipline TEXT,
  athlete_a_workout_note TEXT,
  athlete_b_workout_note TEXT,
  athlete_a_confirmed INTEGER DEFAULT 0,
  athlete_b_confirmed INTEGER DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pending_actions (
  id TEXT PRIMARY KEY,
  athlete_id TEXT NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL,
  expires_at TEXT,
  confirmed_at TEXT
);

-- Ticker stub (coach-ticker.md) — unread strip next slice; never auto-apply plans.
CREATE TABLE IF NOT EXISTS athlete_events (
  id TEXT PRIMARY KEY,
  athlete_id TEXT NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}',
  read_at TEXT,
  created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_athletes_username ON athletes(username);
CREATE UNIQUE INDEX IF NOT EXISTS idx_athletes_auth_user_id ON athletes(auth_user_id);
CREATE INDEX IF NOT EXISTS idx_messages_athlete ON messages(athlete_id, created_at);
CREATE INDEX IF NOT EXISTS idx_plan_blocks_athlete ON plan_blocks(athlete_id, start_date);
CREATE INDEX IF NOT EXISTS idx_plan_windows_athlete ON plan_windows(athlete_id, start_date);
CREATE INDEX IF NOT EXISTS idx_planned_sessions_athlete ON planned_sessions(athlete_id, session_date);
CREATE INDEX IF NOT EXISTS idx_pending_actions_athlete ON pending_actions(athlete_id, created_at);
CREATE INDEX IF NOT EXISTS idx_session_completions_athlete ON session_completions(athlete_id, session_date);
CREATE INDEX IF NOT EXISTS idx_athlete_events_athlete ON athlete_events(athlete_id, created_at);

-- ---------------------------------------------------------------------------
-- RLS (athlete isolation). coach-api uses DATABASE_URL / service_role (bypasses RLS).
-- Policies protect anon/authenticated direct access + optional app.current_athlete_id GUC.
-- ---------------------------------------------------------------------------

ALTER TABLE athletes ENABLE ROW LEVEL SECURITY;
ALTER TABLE plan_blocks ENABLE ROW LEVEL SECURITY;
ALTER TABLE plan_windows ENABLE ROW LEVEL SECURITY;
ALTER TABLE planned_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE athlete_secrets ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE session_completions ENABLE ROW LEVEL SECURITY;
ALTER TABLE pending_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE invites ENABLE ROW LEVEL SECURITY;
ALTER TABLE training_pairs ENABLE ROW LEVEL SECURITY;
ALTER TABLE coordinated_sessions ENABLE ROW LEVEL SECURITY;

-- Helper: own row via auth.uid() mapped to athletes.auth_user_id OR session GUC
CREATE OR REPLACE FUNCTION public.coach_athlete_allowed(p_athlete_id TEXT)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
AS $$
  SELECT
    (
      auth.uid() IS NOT NULL
      AND EXISTS (
        SELECT 1 FROM public.athletes a
        WHERE a.id = p_athlete_id AND a.auth_user_id = auth.uid()::text
      )
    )
    OR (
      NULLIF(current_setting('app.current_athlete_id', true), '') IS NOT NULL
      AND current_setting('app.current_athlete_id', true) = p_athlete_id
    );
$$;

DROP POLICY IF EXISTS athletes_isolation ON athletes;
CREATE POLICY athletes_isolation ON athletes
  FOR ALL USING (
    id = NULLIF(current_setting('app.current_athlete_id', true), '')
    OR (auth.uid() IS NOT NULL AND auth_user_id = auth.uid()::text)
  )
  WITH CHECK (
    id = NULLIF(current_setting('app.current_athlete_id', true), '')
    OR (auth.uid() IS NOT NULL AND auth_user_id = auth.uid()::text)
  );

DROP POLICY IF EXISTS plan_blocks_isolation ON plan_blocks;
CREATE POLICY plan_blocks_isolation ON plan_blocks
  FOR ALL USING (public.coach_athlete_allowed(athlete_id))
  WITH CHECK (public.coach_athlete_allowed(athlete_id));

DROP POLICY IF EXISTS plan_windows_isolation ON plan_windows;
CREATE POLICY plan_windows_isolation ON plan_windows
  FOR ALL USING (public.coach_athlete_allowed(athlete_id))
  WITH CHECK (public.coach_athlete_allowed(athlete_id));

DROP POLICY IF EXISTS planned_sessions_isolation ON planned_sessions;
CREATE POLICY planned_sessions_isolation ON planned_sessions
  FOR ALL USING (public.coach_athlete_allowed(athlete_id))
  WITH CHECK (public.coach_athlete_allowed(athlete_id));

DROP POLICY IF EXISTS athlete_secrets_isolation ON athlete_secrets;
CREATE POLICY athlete_secrets_isolation ON athlete_secrets
  FOR ALL USING (public.coach_athlete_allowed(athlete_id))
  WITH CHECK (public.coach_athlete_allowed(athlete_id));

DROP POLICY IF EXISTS messages_isolation ON messages;
CREATE POLICY messages_isolation ON messages
  FOR ALL USING (public.coach_athlete_allowed(athlete_id))
  WITH CHECK (public.coach_athlete_allowed(athlete_id));

DROP POLICY IF EXISTS session_completions_isolation ON session_completions;
CREATE POLICY session_completions_isolation ON session_completions
  FOR ALL USING (public.coach_athlete_allowed(athlete_id))
  WITH CHECK (public.coach_athlete_allowed(athlete_id));

DROP POLICY IF EXISTS pending_actions_isolation ON pending_actions;
CREATE POLICY pending_actions_isolation ON pending_actions
  FOR ALL USING (public.coach_athlete_allowed(athlete_id))
  WITH CHECK (public.coach_athlete_allowed(athlete_id));
