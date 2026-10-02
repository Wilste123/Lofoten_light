-- Beta: optional TrainingPeaks calendar mirror (unofficial tpapi + session cookie).
-- Run after 001_supabase_schema.sql on Postgres/Supabase.

ALTER TABLE athlete_secrets
  ADD COLUMN IF NOT EXISTS tp_auth_cookie TEXT,
  ADD COLUMN IF NOT EXISTS tp_user_id TEXT,
  ADD COLUMN IF NOT EXISTS tp_sync_enabled BOOLEAN NOT NULL DEFAULT FALSE;
