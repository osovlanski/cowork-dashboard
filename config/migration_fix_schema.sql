-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- Cowork Dashboard — Schema Migration
-- Fixes mismatch between the original schema and what the workers/
-- dashboard actually use.  Safe to re-run (IF NOT EXISTS / IF EXISTS).
-- Run in: Supabase ➜ SQL Editor ➜ New query ➜ Run
-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

-- 1. emails table
--    Written by: email_audit.py worker
--    Read by:    dashboard emails page
CREATE TABLE IF NOT EXISTS emails (
  id          uuid         DEFAULT gen_random_uuid() PRIMARY KEY,
  sender      text,
  subject     text,
  snippet     text,
  date        date         NOT NULL,
  priority    text,        -- 'high' | 'medium' | 'low'
  category    text,        -- 'bill' | 'recruiter' | 'action' | 'newsletter'
  ai_summary  text,
  created_at  timestamptz  DEFAULT now(),
  UNIQUE (sender, subject, date)
);

CREATE INDEX IF NOT EXISTS emails_date_idx ON emails (date DESC);

-- 2. diy_log table
--    Written by: diy_log.py worker
--    Read by:    dashboard DIY page
CREATE TABLE IF NOT EXISTS diy_log (
  id          uuid         DEFAULT gen_random_uuid() PRIMARY KEY,
  date        date         NOT NULL UNIQUE,
  entry       text,
  project     text,
  created_at  timestamptz  DEFAULT now()
);

CREATE INDEX IF NOT EXISTS diy_log_date_idx ON diy_log (date DESC);

-- 3. weekly_plans — add 'plan' column
--    The worker stores the full markdown in 'plan';
--    the original schema had 'raw_markdown' instead.
ALTER TABLE weekly_plans ADD COLUMN IF NOT EXISTS plan text;

-- 4. habits — add 'name' column
--    Dashboard expects habits.name (simple list model).
--    Original schema had habit_name + week-based composite key.
ALTER TABLE habits ADD COLUMN IF NOT EXISTS name text;

-- 5. habit_completions table
--    Dashboard tracks per-day completions separately.
CREATE TABLE IF NOT EXISTS habit_completions (
  id             uuid         DEFAULT gen_random_uuid() PRIMARY KEY,
  habit_id       uuid         REFERENCES habits(id) ON DELETE CASCADE,
  completed_date date         NOT NULL,
  created_at     timestamptz  DEFAULT now(),
  UNIQUE (habit_id, completed_date)
);

-- 6. Row Level Security for new tables
ALTER TABLE emails             ENABLE ROW LEVEL SECURITY;
ALTER TABLE diy_log            ENABLE ROW LEVEL SECURITY;
ALTER TABLE habit_completions  ENABLE ROW LEVEL SECURITY;

-- Allow anon key full access (personal dashboard — no auth needed)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'emails' AND policyname = 'anon_all'
  ) THEN
    CREATE POLICY "anon_all" ON emails FOR ALL TO anon USING (true) WITH CHECK (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'diy_log' AND policyname = 'anon_all'
  ) THEN
    CREATE POLICY "anon_all" ON diy_log FOR ALL TO anon USING (true) WITH CHECK (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'habit_completions' AND policyname = 'anon_all'
  ) THEN
    CREATE POLICY "anon_all" ON habit_completions FOR ALL TO anon USING (true) WITH CHECK (true);
  END IF;
END $$;
