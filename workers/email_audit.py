"""
email_audit.py — Daily Gmail audit worker for Railway.
Schedule: every day at 08:00 Israel time (06:00 UTC)

Fetches last 24h of Gmail threads → Claude Haiku analysis →
writes markdown to productive/emails/ → commits to GitHub →
stores structured data in Supabase.
"""

import os
import json
from datetime import date, datetime
import anthropic
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


# ── Auth ─────────────────────────────────────────────────
def get_gmail_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ['GMAIL_REFRESH_TOKEN'],
        client_id=os.environ['GMAIL_CLIENT_ID'],
        client_secret=os.environ['GMAIL_CLIENT_SECRET'],
        token_uri='https://oauth2.googleapis.com/token',
        scopes=['https://www.googleapis.com/auth/gmail.readonly'],
    )
    creds.refresh(Request())
    return build('gmail', 'v1', credentials=creds)


# ── Fetch ─────────────────────────────────────────────────
def fetch_emails(service, max_results=40):
    result = service.users().messages().list(
        userId='me', q='newer_than:1d', maxResults=max_results
    ).execute()
    messages = result.get('messages', [])
    emails = []
    for msg in messages:
        try:
            m = service.users().messages().get(
                userId='me', id=msg['id'], format='metadata',
                metadataHeaders=['From', 'Subject']
            ).execute()
            headers = {h['name']: h['value'] for h in m['payload']['headers']}
            emails.append({
                'from':    headers.get('From', ''),
                'subject': headers.get('Subject', ''),
                'snippet': m.get('snippet', '')[:200],
            })
        except Exception as e:
            print(f"  Warning: could not fetch message {msg['id']}: {e}")
    return emails


# ── Analyse ───────────────────────────────────────────────
def generate_audit(emails: list[dict]) -> str:
    client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
    today = date.today().strftime('%Y-%m-%d')
    email_text = '\n'.join(
        f"From: {e['from']}\nSubject: {e['subject']}\nSnippet: {e['snippet']}\n"
        for e in emails
    )
    msg = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=2500,
        messages=[{
            'role': 'user',
            'content': f"""Analyse these Gmail threads (last 24h) for Itay Osovlanski <itayosov@gmail.com>.

{email_text}

Write a daily audit in this exact markdown format:

# Daily Gmail Audit — {today}

**Inbox owner:** Itay Osovlanski (itayosov@gmail.com)
**Window:** Last 24 hours (`newer_than:1d`)
**Threads scanned:** {len(emails)}

---

## ⚠️ Action Required

These need a reply or decision within ~48h:

[numbered list — only items that genuinely need action]

---

## 💼 Job Offer / Recruiter

[numbered list]

---

## 💸 Bill / Invoice

[numbered list]

---

## 📰 Newsletter / Update

[numbered list]

---

## 🎉 Fun / Personal

[numbered list]

---

## 🗑️ Low Priority (safe to archive)

[numbered list]

---

## 🔧 Suggested cleanup

[Unsubscribe candidates and bulk-archive suggestions]

---

*Generated automatically by the daily Gmail audit task.*"""
        }]
    )
    return msg.content[0].text


# ── Save & Push ───────────────────────────────────────────
def save_markdown(content: str) -> str:
    today = date.today().strftime('%Y-%m-%d')
    path = f'productive/emails/audit_{today}.md'
    os.makedirs('productive/emails', exist_ok=True)
    with open(path, 'w') as f:
        f.write(content)
    print(f'  ✓ Wrote {path}')
    return path


def git_push(filepath: str, message: str):
    from github_push import push_file
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    push_file(filepath, content, message)


def classify_email(subject: str, snippet: str) -> tuple:
    """Return (category, priority) based on simple heuristics."""
    text = f"{subject} {snippet}".lower()
    if any(w in text for w in ['invoice', 'payment', 'bill', 'receipt', 'charge']):
        return 'bill', 'high'
    if any(w in text for w in ['recruiter', 'opportunity', 'role', 'hiring', 'position', 'job offer']):
        return 'recruiter', 'medium'
    if any(w in text for w in ['urgent', 'action required', 'asap', 'deadline', 'follow up']):
        return 'action', 'high'
    if any(w in text for w in ['unsubscribe', 'newsletter', 'weekly digest', 'digest', 'update']):
        return 'newsletter', 'low'
    return 'newsletter', 'low'


def store_in_supabase(today: str, emails: list[dict]):
    """Write individual emails to the `emails` table (matches dashboard schema)."""
    supabase_url = os.environ.get('SUPABASE_URL')
    supabase_key = os.environ.get('SUPABASE_SERVICE_KEY')
    if not (supabase_url and supabase_key):
        print('  Supabase not configured — skipping DB write')
        return
    import urllib.request
    stored = 0
    for email in emails:
        category, priority = classify_email(email.get('subject', ''), email.get('snippet', ''))
        payload = json.dumps({
            'sender':   email.get('from', ''),
            'subject':  email.get('subject', ''),
            'snippet':  email.get('snippet', ''),
            'date':     today,
            'priority': priority,
            'category': category,
        }).encode()
        req = urllib.request.Request(
            f'{supabase_url}/rest/v1/emails',
            data=payload,
            headers={
                'apikey':        supabase_key,
                'Authorization': f'Bearer {supabase_key}',
                'Content-Type':  'application/json',
                'Prefer':        'resolution=merge-duplicates',
            },
            method='POST',
        )
        try:
            urllib.request.urlopen(req, timeout=10)
            stored += 1
        except Exception as e:
            print(f'  Warning: Supabase write for "{email.get("subject", "?")}": {e}')
    print(f'  ✓ Stored {stored}/{len(emails)} emails in Supabase')


# ── Main ──────────────────────────────────────────────────
def main():
    today = date.today().strftime('%Y-%m-%d')
    print(f'[{datetime.now().isoformat()}] Starting daily email audit for {today}')

    service = get_gmail_service()
    print('  ✓ Gmail authenticated')

    emails = fetch_emails(service)
    print(f'  ✓ Fetched {len(emails)} emails')

    audit = generate_audit(emails)
    print('  ✓ Audit generated')

    filepath = save_markdown(audit)
    store_in_supabase(today, emails)
    git_push(filepath, f'auto: email audit {today}')

    print('Done ✓')


if __name__ == '__main__':
    main()
