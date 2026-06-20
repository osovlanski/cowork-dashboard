"""
telegram_briefing.py — Daily morning briefing via Telegram.
Schedule: every day at 04:30 UTC (07:30 Israel time)

Queries Supabase for today's data → Claude Haiku synthesis →
sends a concise, actionable Telegram message.

Env vars required:
  ANTHROPIC_API_KEY
  SUPABASE_URL
  SUPABASE_SERVICE_KEY
  TELEGRAM_BOT_TOKEN   (from @BotFather)
  TELEGRAM_CHAT_ID     (your personal chat ID — see SETUP.md)
"""

import os
import json
import urllib.request
import urllib.error
from datetime import date, datetime, timedelta
import anthropic

# ── Supabase helpers ──────────────────────────────────────────────────────────
def sb_get(path: str) -> list:
    url = os.environ['SUPABASE_URL']
    key = os.environ['SUPABASE_SERVICE_KEY']
    req = urllib.request.Request(
        f'{url}/rest/v1/{path}',
        headers={'apikey': key, 'Authorization': f'Bearer {key}'},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f'  ⚠ Supabase error ({path}): {e}')
        return []


# ── Data fetchers ─────────────────────────────────────────────────────────────
def get_action_emails(today: str) -> list[dict]:
    """High-priority or action-required emails from the last 2 days."""
    two_days_ago = str(date.today() - timedelta(days=2))
    rows = sb_get(
        f'emails?date=gte.{two_days_ago}&priority=in.(high,medium)'
        f'&order=date.desc&limit=10'
    )
    return rows


def get_todays_habits(today: str) -> tuple[list, list]:
    """Return (habits, completed_ids_today)."""
    habits = sb_get('habits?order=created_at.asc&limit=20')
    completions = sb_get(f'habit_completions?completed_date=eq.{today}&select=habit_id')
    done_ids = {c['habit_id'] for c in completions}
    return habits, done_ids


def get_current_plan() -> dict | None:
    """Latest weekly plan."""
    rows = sb_get('weekly_plans?order=week_start.desc&limit=1')
    return rows[0] if rows else None


def get_recent_diy() -> dict | None:
    """Most recent DIY log entry."""
    rows = sb_get('diy_log?order=date.desc&limit=1')
    return rows[0] if rows else None


def get_habit_streak(habits: list, done_ids: set) -> str:
    """Short streak summary string."""
    if not habits:
        return 'No habits set up yet'
    done = sum(1 for h in habits if h['id'] in done_ids)
    total = len(habits)
    return f'{done}/{total} habits done today'


# ── Claude briefing generator ─────────────────────────────────────────────────
def generate_briefing(
    today: str,
    emails: list[dict],
    habits: list,
    done_ids: set,
    plan: dict | None,
    diy: dict | None,
) -> str:
    client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

    # Summarise context for Claude
    email_text = '\n'.join(
        f'  - [{e.get("priority","?")}] {e.get("subject","?")} (from {e.get("sender","?")})'
        for e in emails[:6]
    ) or '  None — inbox clear ✓'

    habit_lines = '\n'.join(
        f'  - {"✅" if h["id"] in done_ids else "⬜"} {h["name"]}'
        for h in habits[:8]
    ) or '  No habits configured'

    plan_excerpt = ''
    if plan:
        # Pull first 400 chars of the plan for context
        plan_excerpt = (plan.get('plan') or '')[:400].strip()

    diy_text = ''
    if diy:
        diy_text = f"Project: {diy.get('project','')} | Last entry: {diy.get('date','')}"

    day_name = datetime.strptime(today, '%Y-%m-%d').strftime('%A')

    msg = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=500,
        messages=[{
            'role': 'user',
            'content': f"""Write a concise morning briefing Telegram message for Itay — 30yo senior backend engineer in Tel Aviv.
Today is {day_name}, {today}.

DATA:
Emails needing attention:
{email_text}

Habit tracker:
{habit_lines}

Weekly plan excerpt:
{plan_excerpt or "No plan this week yet"}

DIY:
{diy_text or "No recent DIY entry"}

RULES:
- Start with a one-line energetic greeting using the day name
- Max 5 bullet points total — only what genuinely needs attention
- End with ONE specific action for the next 2 hours (the most important thing)
- Keep it under 250 words
- Use Telegram markdown: *bold*, _italic_
- Do NOT use headers (no ## or ###)
- Friendly but crisp — engineer tone, not motivational-poster tone
""",
        }]
    )
    return msg.content[0].text


# ── Telegram sender ───────────────────────────────────────────────────────────
def send_telegram(text: str) -> bool:
    token   = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
    chat_id = os.environ.get('TELEGRAM_CHAT_ID', '').strip()

    if not token or not chat_id:
        print('  ⚠ TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — printing instead:\n')
        print(text)
        return False

    payload = json.dumps({
        'chat_id':    chat_id,
        'text':       text,
        'parse_mode': 'Markdown',
    }).encode()

    req = urllib.request.Request(
        f'https://api.telegram.org/bot{token}/sendMessage',
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            if result.get('ok'):
                print('  ✓ Telegram message sent')
                return True
            else:
                print(f'  ✗ Telegram error: {result}')
                return False
    except urllib.error.HTTPError as e:
        print(f'  ✗ Telegram HTTP error {e.code}: {e.read().decode()}')
        return False
    except Exception as e:
        print(f'  ✗ Telegram error: {e}')
        return False


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    today = str(date.today())
    print(f'[{datetime.now().isoformat()}] Generating morning briefing for {today}')

    emails          = get_action_emails(today)
    habits, done    = get_todays_habits(today)
    plan            = get_current_plan()
    diy             = get_recent_diy()

    print(f'  → {len(emails)} priority emails, {len(habits)} habits, plan: {"yes" if plan else "no"}')

    briefing = generate_briefing(today, emails, habits, done, plan, diy)
    print(f'  ✓ Briefing generated ({len(briefing)} chars)')

    send_telegram(briefing)
    print('Done ✓')


if __name__ == '__main__':
    main()
