-- ══════════════════════════════════════════════════════════
-- Migration: add tables for the new tools
--   • books        — book-recommendation worker (book_picks.py)
--   • market_brief — finance daily-brief worker (market_brief.py)
--   • deals        — product-deal scanner worker (deal_scan.py)
-- Run this in: Supabase → SQL Editor → New query → Run
-- Safe to re-run (IF NOT EXISTS / idempotent policies).
-- ══════════════════════════════════════════════════════════

-- ── Books ────────────────────────────────────────────────
-- One row per recommended book; written by the weekly book_picks worker.
CREATE TABLE IF NOT EXISTS books (
  id          uuid    DEFAULT gen_random_uuid() PRIMARY KEY,
  title       text    NOT NULL,
  author      text,
  category    text,   -- 'engineering' | 'leadership' | 'fiction' | 'finance' | ...
  reason      text,   -- why it was picked this week
  status      text    DEFAULT 'suggested'
                      CHECK (status IN ('suggested', 'reading', 'read', 'skipped')),
  rating      integer CHECK (rating BETWEEN 1 AND 5),
  picked_week date    NOT NULL DEFAULT CURRENT_DATE,
  created_at  timestamptz DEFAULT now(),
  UNIQUE (title, author)
);

CREATE INDEX IF NOT EXISTS books_picked_week_idx ON books (picked_week DESC);
CREATE INDEX IF NOT EXISTS books_status_idx      ON books (status);

-- ── Market Brief ─────────────────────────────────────────
-- One row per day; written by the market_brief worker.
-- `brief` is the full markdown; `data` holds the structured quote/trend snapshot.
CREATE TABLE IF NOT EXISTS market_brief (
  id         uuid  DEFAULT gen_random_uuid() PRIMARY KEY,
  date       date  NOT NULL UNIQUE DEFAULT CURRENT_DATE,
  brief      text  NOT NULL,
  data       jsonb DEFAULT '{}',   -- { "AAPL": { "price": .., "chg_pct": .., "trend": ".." }, ... }
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS market_brief_date_idx ON market_brief (date DESC);

-- ── Deals ────────────────────────────────────────────────
-- One row per matched product listing; written by the deal_scan worker.
CREATE TABLE IF NOT EXISTS deals (
  id            uuid    DEFAULT gen_random_uuid() PRIMARY KEY,
  source        text    NOT NULL CHECK (source IN ('ebay', 'aliexpress', 'amazon', 'other')),
  search_term   text    NOT NULL,
  title         text    NOT NULL,
  price         numeric,
  currency      text    DEFAULT 'USD',
  url           text    NOT NULL,
  image         text,
  condition     text,
  value_score   integer CHECK (value_score BETWEEN 1 AND 10),  -- Claude's value-for-money score
  reason        text,                                          -- why it's a good deal
  found_date    date    NOT NULL DEFAULT CURRENT_DATE,
  created_at    timestamptz DEFAULT now(),
  UNIQUE (source, url)
);

CREATE INDEX IF NOT EXISTS deals_found_date_idx ON deals (found_date DESC);
CREATE INDEX IF NOT EXISTS deals_score_idx      ON deals (value_score DESC);

-- ══════════════════════════════════════════════════════════
-- Row Level Security — match the existing "anon_all" pattern
-- (personal dashboard; tighten for a shared deployment).
-- ══════════════════════════════════════════════════════════

ALTER TABLE books        ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_brief ENABLE ROW LEVEL SECURITY;
ALTER TABLE deals        ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_all" ON books;
DROP POLICY IF EXISTS "anon_all" ON market_brief;
DROP POLICY IF EXISTS "anon_all" ON deals;

CREATE POLICY "anon_all" ON books        FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all" ON market_brief FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all" ON deals        FOR ALL TO anon USING (true) WITH CHECK (true);
