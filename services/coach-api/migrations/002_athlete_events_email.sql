-- Ticker + email opt-in delta (after 001_supabase_schema.sql)
-- Paste in Supabase SQL editor if schema already applied.
-- Safe / idempotent.

ALTER TABLE athletes ADD COLUMN IF NOT EXISTS email TEXT DEFAULT '';
ALTER TABLE athletes ADD COLUMN IF NOT EXISTS notify_email INTEGER DEFAULT 0;

CREATE TABLE IF NOT EXISTS athlete_events (
  id TEXT PRIMARY KEY,
  athlete_id TEXT NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}',
  read_at TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_athlete_events_athlete
  ON athlete_events(athlete_id, created_at);
CREATE INDEX IF NOT EXISTS idx_athlete_events_unread
  ON athlete_events(athlete_id, read_at, created_at);

ALTER TABLE athlete_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS athlete_events_isolation ON athlete_events;
CREATE POLICY athlete_events_isolation ON athlete_events
  FOR ALL USING (public.coach_athlete_allowed(athlete_id))
  WITH CHECK (public.coach_athlete_allowed(athlete_id));
