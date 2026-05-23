#!/usr/bin/env python3
"""
scripts/test_connections.py — Verify all env vars and external connections.

Run this before deploying to Railway/Vercel to catch missing config early.

Usage:
  # Copy config/.env.example → .env, fill in values, then:
  source .env && python scripts/test_connections.py

  # or export individually and run:
  python scripts/test_connections.py
"""

import os
import json
import urllib.request
import urllib.error
import sys
from datetime import datetime

GREEN  = '\033[92m'
RED    = '\033[91m'
YELLOW = '\033[93m'
BLUE   = '\033[94m'
RESET  = '\033[0m'

def ok(label, detail=''):   print(f'  {GREEN}✓{RESET}  {label:<40} {detail}')
def fail(label, detail=''): print(f'  {RED}✗{RESET}  {label:<40} {detail}')
def warn(label, detail=''): print(f'  {YELLOW}⚠{RESET}  {label:<40} {detail}')
def head(label):            print(f'\n  {BLUE}{label}{RESET}\n')


def check_env(var: str, required=True) -> str | None:
    val = os.environ.get(var, '').strip()
    if val:
        masked = val[:8] + '...' if len(val) > 8 else val
        ok(var, masked)
    elif required:
        fail(var, 'NOT SET')
    else:
        warn(var, 'not set (optional)')
    return val or None


def check_supabase(url: str, key: str):
    """Try a simple REST call to check Supabase is reachable."""
    try:
        req = urllib.request.Request(
            f'{url}/rest/v1/habits?limit=1',
            headers={'apikey': key, 'Authorization': f'Bearer {key}'},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok('Supabase REST API reachable', f'HTTP {resp.status}')
            return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # Table doesn't exist yet — that's fine, connection worked
            ok('Supabase REST API reachable', f'(schema not applied yet)')
            return True
        fail('Supabase REST API', f'HTTP {e.code}: {e.read().decode()[:80]}')
        return False
    except Exception as e:
        fail('Supabase REST API', str(e)[:80])
        return False


def check_anthropic(key: str):
    try:
        payload = json.dumps({
            'model': 'claude-haiku-4-5-20251001',
            'max_tokens': 10,
            'messages': [{'role': 'user', 'content': 'ping'}],
        }).encode()
        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=payload,
            headers={
                'x-api-key': key,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            },
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok('Anthropic API reachable', 'Claude Haiku responded')
    except urllib.error.HTTPError as e:
        if e.code == 401:
            fail('Anthropic API', 'Invalid API key')
        else:
            fail('Anthropic API', f'HTTP {e.code}')
    except Exception as e:
        fail('Anthropic API', str(e)[:80])


def check_gmail(refresh_token: str, client_id: str, client_secret: str):
    try:
        payload = urllib.parse.urlencode({
            'grant_type':    'refresh_token',
            'refresh_token': refresh_token,
            'client_id':     client_id,
            'client_secret': client_secret,
        }).encode()
        req = urllib.request.Request(
            'https://oauth2.googleapis.com/token',
            data=payload,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            if 'access_token' in data:
                ok('Gmail OAuth token refresh', 'access token obtained ✓')
            else:
                fail('Gmail OAuth token refresh', str(data)[:80])
    except urllib.error.HTTPError as e:
        body = json.loads(e.read())
        fail('Gmail OAuth token refresh', body.get('error_description', str(e))[:80])
    except Exception as e:
        fail('Gmail OAuth token refresh', str(e)[:80])


def main():
    import urllib.parse  # needed for gmail check

    print()
    print('  Cowork Dashboard — Connection Checker')
    print(f'  Run at: {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print('  ──────────────────────────────────────────────────')

    # ── Core credentials ──────────────────────────────────
    head('Core')
    anthropic_key  = check_env('ANTHROPIC_API_KEY')
    supabase_url   = check_env('SUPABASE_URL')
    supabase_anon  = check_env('SUPABASE_ANON_KEY', required=False)
    supabase_svc   = check_env('SUPABASE_SERVICE_KEY')

    # ── Gmail (Railway email worker) ──────────────────────
    head('Gmail (email-audit worker)')
    gmail_client_id     = check_env('GMAIL_CLIENT_ID')
    gmail_client_secret = check_env('GMAIL_CLIENT_SECRET')
    gmail_refresh       = check_env('GMAIL_REFRESH_TOKEN')

    # ── Git (Railway push-back) ───────────────────────────
    head('Git (Railway → GitHub push)')
    check_env('GIT_USER_NAME')
    check_env('GIT_USER_EMAIL')
    check_env('GITHUB_TOKEN')

    # ── Telegram (optional) ───────────────────────────────
    head('Telegram (morning briefing — optional)')
    telegram_token   = check_env('TELEGRAM_BOT_TOKEN', required=False)
    telegram_chat_id = check_env('TELEGRAM_CHAT_ID', required=False)

    # ── Live connection tests ─────────────────────────────
    head('Live connection tests')

    if anthropic_key:
        check_anthropic(anthropic_key)
    else:
        warn('Anthropic API', 'skipped (key not set)')

    if supabase_url and supabase_svc:
        check_supabase(supabase_url, supabase_svc)
    else:
        warn('Supabase REST API', 'skipped (URL or key not set)')

    if gmail_refresh and gmail_client_id and gmail_client_secret:
        check_gmail(gmail_refresh, gmail_client_id, gmail_client_secret)
    else:
        warn('Gmail OAuth', 'skipped (credentials not set)')

    print()
    print('  Done. Fix any ✗ items before deploying to Railway/Vercel.')
    print()


if __name__ == '__main__':
    main()
