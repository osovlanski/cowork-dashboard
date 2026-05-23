#!/usr/bin/env python3
"""
scripts/setup_db.py — Apply (or re-apply) the Supabase schema.

No extra packages needed — uses only Python stdlib.

Requirements
────────────
  SUPABASE_PROJECT_REF   The short ref in your project URL:
                         https://<REF>.supabase.co
  SUPABASE_ACCESS_TOKEN  Personal Access Token (NOT the service key).
                         Create one at:
                         https://supabase.com/dashboard/account/tokens

Usage
─────
  export SUPABASE_PROJECT_REF=abcdefghijklmnop
  export SUPABASE_ACCESS_TOKEN=sbp_xxxxxxxxxxxxxxxxxxxx
  python scripts/setup_db.py

  # or in one line:
  SUPABASE_PROJECT_REF=xxx SUPABASE_ACCESS_TOKEN=sbp_xxx python scripts/setup_db.py

What it does
────────────
  Reads config/supabase_schema.sql, splits it into individual statements,
  and executes each against your Supabase project via the Management API.
  Safe to re-run — all statements use CREATE TABLE IF NOT EXISTS / IF NOT EXISTS.
"""

import os
import json
import urllib.request
import urllib.error
import sys
from pathlib import Path

SCHEMA_FILE = Path(__file__).parent.parent / 'config' / 'supabase_schema.sql'
MGMT_API    = 'https://api.supabase.com'

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN  = '\033[92m'
RED    = '\033[91m'
YELLOW = '\033[93m'
RESET  = '\033[0m'
ok     = lambda s: print(f'  {GREEN}✓{RESET}  {s}')
fail   = lambda s: print(f'  {RED}✗{RESET}  {s}')
warn   = lambda s: print(f'  {YELLOW}⚠{RESET}  {s}')


def run_sql(project_ref: str, token: str, sql: str) -> dict:
    url     = f'{MGMT_API}/v1/projects/{project_ref}/database/query'
    payload = json.dumps({'query': sql}).encode()
    req     = urllib.request.Request(
        url, data=payload,
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return {'ok': True, 'body': json.loads(resp.read())}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return {'ok': False, 'status': e.code, 'body': body}
    except Exception as e:
        return {'ok': False, 'status': 0, 'body': str(e)}


def split_statements(sql: str) -> list[str]:
    """Split SQL file into individual statements, stripping comments and blanks."""
    stmts = []
    current = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith('--') or stripped == '':
            continue
        current.append(line)
        if stripped.endswith(';'):
            stmt = '\n'.join(current).strip()
            if stmt:
                stmts.append(stmt)
            current = []
    return stmts


def main():
    project_ref = os.environ.get('SUPABASE_PROJECT_REF', '').strip()
    token       = os.environ.get('SUPABASE_ACCESS_TOKEN', '').strip()

    print()
    print('  Cowork Dashboard — Supabase Schema Setup')
    print('  ─────────────────────────────────────────')

    if not project_ref:
        fail('SUPABASE_PROJECT_REF not set')
        print('       Your project ref is the part before .supabase.co in your project URL')
        sys.exit(1)
    if not token:
        fail('SUPABASE_ACCESS_TOKEN not set')
        print('       Create one at https://supabase.com/dashboard/account/tokens')
        sys.exit(1)
    if not SCHEMA_FILE.exists():
        fail(f'Schema file not found: {SCHEMA_FILE}')
        sys.exit(1)

    print(f'\n  Project : {project_ref}')
    print(f'  Schema  : {SCHEMA_FILE.name}\n')

    sql   = SCHEMA_FILE.read_text()
    stmts = split_statements(sql)
    print(f'  Found {len(stmts)} SQL statements to execute\n')

    errors = 0
    for i, stmt in enumerate(stmts, 1):
        # Extract a short label from the statement for display
        first_line = stmt.split('\n')[0][:72]
        result = run_sql(project_ref, token, stmt)
        if result['ok']:
            ok(first_line)
        else:
            # IF NOT EXISTS statements return 200 even if table exists — but
            # report anything that looks like a real error
            body = result.get('body', '')
            if 'already exists' in body:
                warn(f'{first_line}  [already exists, skipped]')
            else:
                fail(f'{first_line}')
                print(f'       Status {result["status"]}: {body[:200]}')
                errors += 1

    print()
    if errors == 0:
        ok(f'All done! Schema applied to project {project_ref}')
        print()
        print('  Next steps:')
        print('  1. Fill in dashboard.html → CONFIG block with your Supabase URL + anonKey')
        print('  2. Set Railway env vars (see config/.env.example)')
        print('  3. Set Vercel env vars (ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY)')
        print()
    else:
        fail(f'{errors} statement(s) failed. Check output above.')
        sys.exit(1)


if __name__ == '__main__':
    main()
