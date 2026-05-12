-- ══════════════════════════════════════════════════════════
-- Itay's Cowork Dashboard — Supabase Schema
-- Run this in: Supabase → SQL Editor → New query → Run
-- ══════════════════════════════════════════════════════════

-- ── Habits ──────────────────────────────────────────────
-- One row per habit per day per week
CREATE TABLE IF NOT EXISTS habits (
  id           uuid        DEFAULT gen_random_uuid() PRIMARY KEY,
  week_start   date        NOT NULL,          -- e.g. '2026-05-04'
  habit_index  integer     NOT NULL,          -- 0–7 (matches DATA.habits array order)
  day_index    integer     NOT NULL,          -- 0=Mon … 6=Sun
  habit_name   text        NOT NULL,
  checked      boolean     DEFAULT false,
  updated_at   timestamptz DEFAULT now(),
  UNIQUE (week_start, habit_index, day_index)
);

CREATE INDEX IF NOT EXISTS habits_week_idx ON habits (week_start);

-- ── Reflections ─────────────────────────────────────────
-- One row per week
CREATE TABLE IF NOT EXISTS reflections (
  id           uuid        DEFAULT gen_random_uuid() PRIMARY KEY,
  week_start   date        NOT NULL UNIQUE,
  r1           text,   -- "What did I accomplish?"
  r2           text,   -- "What got in the way?"
  r3           text,   -- "One thing I'm proud of"
  r4           text,   -- "One thing to do differently"
  energy       integer CHECK (energy BETWEEN 1 AND 10),
  mood         integer CHECK (mood   BETWEEN 1 AND 10),
  updated_at   timestamptz DEFAULT now()
);

-- ── Email Audits ─────────────────────────────────────────
-- One row per day; written by the Railway email_audit worker
CREATE TABLE IF NOT EXISTS email_audits (
  id           uuid        DEFAULT gen_random_uuid() PRIMARY KEY,
  audit_date   date        NOT NULL UNIQUE,
  threads_scanned integer,
  action_items jsonb       DEFAULT '[]',  -- [{from, subject, desc}]
  sections     jsonb       DEFAULT '{}',  -- {jobs:[...], bills:[...], ...}
  raw_markdown text,
  created_at   timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS email_audits_date_idx ON email_audits (audit_date DESC);

-- ── Weekly Plans ─────────────────────────────────────────
-- One row per week; written by the Railway weekly_plan worker
CREATE TABLE IF NOT EXISTS weekly_plans (
  id              uuid  DEFAULT gen_random_uuid() PRIMARY KEY,
  week_start      date  NOT NULL UNIQUE,
  goals           jsonb DEFAULT '[]',   -- ["goal 1", "goal 2", "goal 3"]
  learning_focus  text,
  diy_project     text,
  trip_idea       text,
  raw_markdown    text,
  created_at      timestamptz DEFAULT now()
);

-- ── AI Summaries Cache ───────────────────────────────────
-- Caches Claude Haiku results so repeat clicks cost $0
CREATE TABLE IF NOT EXISTS ai_summaries (
  id          uuid  DEFAULT gen_random_uuid() PRIMARY KEY,
  item_type   text  NOT NULL,  -- 'course' | 'book' | 'travel' | 'diy'
  item_key    text  NOT NULL,  -- matches id from DATA objects in dashboard.html
  item_name   text,
  summary     text  NOT NULL,
  model       text  DEFAULT 'claude-haiku-4-5-20251001',
  created_at  timestamptz DEFAULT now(),
  UNIQUE (item_type, item_key)
);

-- ══════════════════════════════════════════════════════════
-- Row Level Security
-- The dashboard uses the anon key (public read/write for your
-- personal data). For a shared deployment, tighten these.
-- ══════════════════════════════════════════════════════════

ALTER TABLE habits         ENABLE ROW LEVEL SECURITY;
ALTER TABLE reflections    ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_audits   ENABLE ROW LEVEL SECURITY;
ALTER TABLE weekly_plans   ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_summaries   ENABLE ROW LEVEL SECURITY;

-- Allow anon key to read and write all rows (personal dashboard)
CREATE POLICY "anon_all" ON habits         FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all" ON reflections    FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all" ON email_audits   FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all" ON weekly_plans   FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all" ON ai_summaries   FOR ALL TO anon USING (true) WITH CHECK (true);
