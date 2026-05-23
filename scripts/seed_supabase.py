#!/usr/bin/env python3
"""
scripts/seed_supabase.py — Seed Supabase from existing local files.

Loads:
  • recurring/plans/week_*.md     → weekly_plans table
  • fun/diy/daily_log.md          → diy_log table

Emails are NOT seeded here — the audit markdown files don't contain
the raw per-email data needed by the dashboard. Those rows populate
automatically when the email_audit worker runs on Railway.

Usage
─────
  export SUPABASE_URL=https://xxxx.supabase.co
  export SUPABASE_SERVICE_KEY=eyJ...
  python scripts/seed_supabase.py

  # or in one line:
  SUPABASE_URL=https://xxxx.supabase.co SUPABASE_SERVICE_KEY=eyJ... python scripts/seed_supabase.py
"""

import os
import re
import json
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN = '\033[92m'; RED = '\033[91m'; YELLOW = '\033[93m'; RESET = '\033[0m'
ok   = lambda s: print(f'  {GREEN}✓{RESET}  {s}')
fail = lambda s: print(f'  {RED}✗{RESET}  {s}')
warn = lambda s: print(f'  {YELLOW}⚠{RESET}  {s}')

REPO_ROOT = Path(__file__).parent.parent


def sb_upsert(url: str, key: str, table: str, payload: dict) -> bool:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f'{url}/rest/v1/{table}',
        data=data,
        headers={
            'apikey':        key,
            'Authorization': f'Bearer {key}',
            'Content-Type':  'application/json',
            'Prefer':        'resolution=merge-duplicates',
        },
        method='POST',
    )
    try:
        urllib.request.urlopen(req, timeout=15)
        return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        fail(f'HTTP {e.code} upserting to {table}: {body}')
        return False
    except Exception as e:
        fail(f'Error upserting to {table}: {e}')
        return False


# ── Weekly Plans ──────────────────────────────────────────────────────────────
def seed_weekly_plans(url: str, key: str) -> int:
    plans_dir = REPO_ROOT / 'recurring' / 'plans'
    files = sorted(plans_dir.glob('week_*.md'))
    if not files:
        warn('No weekly plan files found in recurring/plans/')
        return 0

    seeded = 0
    for f in files:
        # Extract date from filename: week_2026-05-25.md → 2026-05-25
        match = re.search(r'week_(\d{4}-\d{2}-\d{2})\.md', f.name)
        if not match:
            warn(f'Skipping {f.name} — cannot parse date from filename')
            continue
        week_start = match.group(1)
        plan_text = f.read_text(encoding='utf-8').strip()

        success = sb_upsert(url, key, 'weekly_plans', {
            'week_start': week_start,
            'plan':       plan_text,
        })
        if success:
            ok(f'weekly_plans: {week_start}')
            seeded += 1
    return seeded


# ── DIY Log ───────────────────────────────────────────────────────────────────
def seed_diy_log(url: str, key: str) -> int:
    log_file = REPO_ROOT / 'fun' / 'diy' / 'daily_log.md'
    if not log_file.exists():
        warn('fun/diy/daily_log.md not found — skipping DIY log')
        return 0

    content = log_file.read_text(encoding='utf-8')

    # Split on ## YYYY-MM-DD headers — each block is one entry
    pattern = re.compile(r'(?=^## \d{4}-\d{2}-\d{2})', re.MULTILINE)
    blocks = [b.strip() for b in pattern.split(content) if b.strip()]

    seeded = 0
    for block in blocks:
        # Extract date from the ## header line
        date_match = re.match(r'^## (\d{4}-\d{2}-\d{2})', block)
        if not date_match:
            continue
        entry_date = date_match.group(1)

        # Extract a project name from the header title if present
        title_match = re.match(r'^## \d{4}-\d{2}-\d{2}[^—]*—\s*(.+)', block)
        project = title_match.group(1).strip() if title_match else ''

        # Remove trailing --- separator lines
        entry_text = re.sub(r'\n---\s*$', '', block).strip()

        success = sb_upsert(url, key, 'diy_log', {
            'date':    entry_date,
            'entry':   entry_text,
            'project': project,
        })
        if success:
            ok(f'diy_log: {entry_date}  ({project[:50]})')
            seeded += 1
    return seeded


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    supabase_url = os.environ.get('SUPABASE_URL', '').rstrip('/')
    supabase_key = os.environ.get('SUPABASE_SERVICE_KEY', '')

    print()
    print('  Cowork Dashboard — Supabase Seeder')
    print('  ────────────────────────────────────')

    if not supabase_url:
        fail('SUPABASE_URL not set')
        raise SystemExit(1)
    if not supabase_key:
        fail('SUPABASE_SERVICE_KEY not set')
        raise SystemExit(1)

    print(f'\n  Target: {supabase_url}\n')

    print('  ── Weekly Plans ─────────────────────')
    plans = seed_weekly_plans(supabase_url, supabase_key)

    print('\n  ── DIY Log ──────────────────────────')
    diy = seed_diy_log(supabase_url, supabase_key)

    print(f'\n  Done — seeded {plans} weekly plan(s) and {diy} DIY log entry/entries.')
    print()
    print('  NOTE: Email rows populate automatically when the email_audit')
    print('        Railway worker runs (it writes individual emails to the')
    print('        `emails` table with sender/subject/priority data).')
    print()


if __name__ == '__main__':
    main()
