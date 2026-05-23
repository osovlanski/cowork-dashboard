-- ══════════════════════════════════════════════════════════
-- Itay's Cowork Dashboard — Supabase Schema
-- Run this in: Supabase → SQL Editor → New query → Run
-- ══════════════════════════════════════════════════════════

-- ── Habits ──────────────────────────────────────────────
-- One row per habit (the habit definition list)
CREATE TABLE IF NOT EXISTS habits (
  id         uuid    DEFAULT gen_random_uuid() PRIMARY KEY,
  name       text    NOT NULL,
  created_at timestamptz DEFAULT now()
);

-- ── Habit Completions ────────────────────────────────────
-- One row per (habit, date) when the user checks off a habit
CREATE TABLE IF NOT EXISTS habit_completions (
  id             uuid  DEFAULT gen_random_uuid() PRIMARY KEY,
  habit_id       uuid  NOT NULL REFERENCES habits (id) ON DELETE CASCADE,
  completed_date date  NOT NULL,
  created_at     timestamptz DEFAULT now(),
  UNIQUE (habit_id, completed_date)
);

CREATE INDEX IF NOT EXISTS habit_completions_date_idx ON habit_completions (completed_date DESC);

-- ── Emails ───────────────────────────────────────────────
-- One row per email; written by the Railway email_audit worker
CREATE TABLE IF NOT EXISTS emails (
  id         uuid  DEFAULT gen_random_uuid() PRIMARY KEY,
  sender     text,
  subject    text,
  snippet    text,
  date       date  NOT NULL DEFAULT CURRENT_DATE,
  priority   text  CHECK (priority IN ('high', 'medium', 'low')),
  category   text, -- 'action' | 'recruiter' | 'bill' | 'newsletter' | 'fun' | 'archive'
  ai_summary text,
  created_at timestamptz DEFAULT now(),
  UNIQUE (sender, subject, date)
);

CREATE INDEX IF NOT EXISTS emails_date_idx ON emails (date DESC);

-- ── DIY Log ──────────────────────────────────────────────
-- One row per day; written by the Railway diy_log worker
CREATE TABLE IF NOT EXISTS diy_log (
  id         uuid  DEFAULT gen_random_uuid() PRIMARY KEY,
  date       date  NOT NULL UNIQUE DEFAULT CURRENT_DATE,
  entry      text  NOT NULL,
  project    text,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS diy_log_date_idx ON diy_log (date DESC);

-- ── Weekly Plans ─────────────────────────────────────────
-- One row per week; written by the Railway weekly_plan worker
CREATE TABLE IF NOT EXISTS weekly_plans (
  id         uuid  DEFAULT gen_random_uuid() PRIMARY KEY,
  week_start date  NOT NULL UNIQUE,
  plan       text  NOT NULL,  -- full markdown plan
  created_at timestamptz DEFAULT now()
);

-- ── Videos (TikTok + YouTube watch-later) ───────────────
-- Shared table for all saved/liked/watch-later video content
CREATE TABLE IF NOT EXISTS videos (
  id          uuid    DEFAULT gen_random_uuid() PRIMARY KEY,
  platform    text    NOT NULL CHECK (platform IN ('tiktok', 'youtube')),
  source_url  text    NOT NULL UNIQUE,
  source_type text,   -- 'favorite' | 'liked' | 'watched' | 'watch_later' | 'playlist'
  saved_at    date,
  title       text,
  description text,
  hashtags    jsonb   DEFAULT '[]',
  creator     text,
  duration_s  integer,              -- seconds (YouTube only)
  thumbnail   text,                 -- URL (YouTube only)
  transcript  text,                 -- full transcript if available (YouTube)
  summary     text,                 -- Claude-generated summary
  category    text,                 -- Claude-assigned category
  why_saved   text,                 -- Claude's guess at why you saved it
  created_at  timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS videos_platform_idx  ON videos (platform);
CREATE INDEX IF NOT EXISTS videos_category_idx  ON videos (category);
CREATE INDEX IF NOT EXISTS videos_saved_at_idx  ON videos (saved_at DESC);

-- ── AI Summaries Cache ───────────────────────────────────
-- Caches Claude Haiku results so repeat clicks cost $0
CREATE TABLE IF NOT EXISTS ai_summaries (
  id         uuid  DEFAULT gen_random_uuid() PRIMARY KEY,
  item_type  text  NOT NULL,  -- 'email' | 'diy' | 'overview'
  item_key   text  NOT NULL,
  item_name  text,
  summary    text  NOT NULL,
  model      text  DEFAULT 'claude-haiku-4-5-20251001',
  created_at timestamptz DEFAULT now(),
  UNIQUE (item_type, item_key)
);

-- ══════════════════════════════════════════════════════════
-- Row Level Security
-- The dashboard uses the anon key (public read/write for your
-- personal data). For a shared deployment, tighten these.
-- ══════════════════════════════════════════════════════════

ALTER TABLE videos             ENABLE ROW LEVEL SECURITY;
ALTER TABLE habits             ENABLE ROW LEVEL SECURITY;
ALTER TABLE habit_completions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE emails             ENABLE ROW LEVEL SECURITY;
ALTER TABLE diy_log            ENABLE ROW LEVEL SECURITY;
ALTER TABLE weekly_plans       ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_summaries       ENABLE ROW LEVEL SECURITY;

-- Allow anon key to read and write all rows (personal dashboard)
CREATE POLICY "anon_all" ON videos            FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all" ON habits            FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all" ON habit_completions FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all" ON emails            FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all" ON diy_log           FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all" ON weekly_plans      FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all" ON ai_summaries      FOR ALL TO anon USING (true) WITH CHECK (true);
