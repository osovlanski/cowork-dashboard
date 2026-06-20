#!/usr/bin/env python3
"""
workers/tiktok_import.py — Process a TikTok data export and store summarised videos.

How to get your TikTok export:
  1. TikTok app → Profile → ☰ Settings → Privacy → Download your data
  2. Select "JSON" format, request the file
  3. Wait for the email (~24h), download the ZIP
  4. Unzip and copy user_data.json here:  tiktok_data/user_data.json

Then run:
  ANTHROPIC_API_KEY=... SUPABASE_URL=... SUPABASE_SERVICE_KEY=...
  python workers/tiktok_import.py

What it processes:
  - Activity.Favorite Videos
  - Activity.Like List  (liked videos)
  - Activity.Watch History (recent watches)

For each video it:
  1. Fetches the TikTok page to extract creator, description, hashtags
  2. Asks Claude Haiku to summarise and categorise the content
  3. Stores everything in the Supabase `videos` table (upsert — safe to re-run)

Requires: anthropic (pip install anthropic)
"""

import os
import re
import json
import time
import urllib.request
import urllib.error
from datetime import datetime, date
from pathlib import Path
import anthropic

# ── Config ────────────────────────────────────────────────────────────────────
DATA_FILE    = Path('tiktok_data/user_data.json')
DELAY_S      = 1.5   # seconds between TikTok page fetches (be polite)
MAX_PER_RUN  = 200   # cap to avoid very long runs; increase if needed

CATEGORIES = [
    'tutorial / how-to',
    'comedy / entertainment',
    'tech / coding',
    'food / recipe',
    'fitness / health',
    'travel / places',
    'news / politics',
    'design / art / DIY',
    'productivity / self-improvement',
    'music / dance',
    'other',
]


# ── TikTok page scraper ───────────────────────────────────────────────────────
def fetch_tiktok_meta(url: str) -> dict:
    """
    Fetch a TikTok video page and extract the JSON-LD / __NEXT_DATA__ metadata.
    Returns a dict with keys: description, creator, hashtags, title.
    Falls back to empty strings if scraping fails.
    """
    try:
        req = urllib.request.Request(
            url,
            headers={
                # Mobile UA to get simpler page
                'User-Agent': (
                    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) '
                    'AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'
                ),
                'Accept-Language': 'en-US,en;q=0.9',
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f'    ⚠ Could not fetch {url}: {e}')
        return {}

    meta = {}

    # Try to find description from og:description or JSON-LD
    og_desc = re.search(r'<meta[^>]+property="og:description"[^>]+content="([^"]*)"', html)
    if og_desc:
        meta['description'] = og_desc.group(1)

    # Creator from og:title or title tag
    og_title = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', html)
    if og_title:
        meta['title'] = og_title.group(1)

    # Hashtags
    hashtags = re.findall(r'#(\w+)', meta.get('description', '') + meta.get('title', ''))
    meta['hashtags'] = list(dict.fromkeys(hashtags))  # deduplicate, preserve order

    return meta


# ── Claude summariser ─────────────────────────────────────────────────────────
def summarise(client: anthropic.Anthropic, url: str, meta: dict) -> dict:
    """Ask Claude Haiku to categorise and summarise the video."""
    description = meta.get('description', '')
    title       = meta.get('title', '')
    hashtags    = ' '.join('#' + h for h in meta.get('hashtags', []))
    context     = f'Title: {title}\nDescription: {description}\nHashtags: {hashtags}\nURL: {url}'

    if not (description or title):
        # Nothing to summarise — just log the URL
        return {
            'summary':  '(no metadata available)',
            'category': 'other',
            'why_saved': '',
        }

    try:
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=300,
            messages=[{
                'role': 'user',
                'content': f"""Analyse this saved TikTok video for Itay — 30yo software engineer in Tel Aviv.

{context}

Reply with ONLY a JSON object (no markdown), exactly this shape:
{{
  "summary": "2 sentence description of what this video is about",
  "category": "one of: {', '.join(CATEGORIES)}",
  "why_saved": "one sentence on why an engineer might have saved this"
}}"""
            }]
        )
        return json.loads(msg.content[0].text)
    except Exception as e:
        print(f'    ⚠ Claude error: {e}')
        return {'summary': description[:200], 'category': 'other', 'why_saved': ''}


# ── Supabase upsert ───────────────────────────────────────────────────────────
def upsert_video(sb_url: str, sb_key: str, row: dict) -> bool:
    payload = json.dumps(row).encode()
    req = urllib.request.Request(
        f'{sb_url}/rest/v1/videos',
        data=payload,
        headers={
            'apikey': sb_key, 'Authorization': f'Bearer {sb_key}',
            'Content-Type': 'application/json',
            'Prefer': 'resolution=merge-duplicates',
        },
        method='POST',
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f'    ⚠ Supabase write failed: {e}')
        return False


def already_processed(sb_url: str, sb_key: str, url: str) -> bool:
    """Check if this video URL is already in Supabase."""
    encoded = urllib.parse.quote(url)
    req = urllib.request.Request(
        f'{sb_url}/rest/v1/videos?source_url=eq.{encoded}&select=id&limit=1',
        headers={'apikey': sb_key, 'Authorization': f'Bearer {sb_key}'},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return len(json.loads(resp.read())) > 0
    except Exception:
        return False


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    import urllib.parse

    api_key  = os.environ['ANTHROPIC_API_KEY']
    sb_url   = os.environ['SUPABASE_URL']
    sb_key   = os.environ['SUPABASE_SERVICE_KEY']

    if not DATA_FILE.exists():
        print(f'❌  Data file not found: {DATA_FILE}')
        print()
        print('    Steps to get your TikTok data:')
        print('    1. TikTok app → Profile → ☰ → Settings → Privacy → Download your data')
        print('    2. Choose JSON format → Request data')
        print('    3. Wait for email, download ZIP, extract user_data.json')
        print(f'    4. Place it at: {DATA_FILE}')
        return

    client = anthropic.Anthropic(api_key=api_key)
    data   = json.loads(DATA_FILE.read_text())
    activity = data.get('Activity', {})

    # Collect all saved/liked/watched videos
    sources: list[tuple[str, str, str]] = []  # (url, date_str, source_type)

    for item in activity.get('Favorite Videos', {}).get('FavoriteVideoList', []):
        sources.append((item.get('Link', ''), item.get('Date', ''), 'favorite'))

    for item in activity.get('Like List', {}).get('ItemFavoriteList', []):
        sources.append((item.get('link', ''), item.get('date', ''), 'liked'))

    for item in activity.get('Video Browsing History', {}).get('VideoList', []):
        sources.append((item.get('VideoLink', ''), item.get('Date', ''), 'watched'))

    # Deduplicate by URL
    seen = {}
    for url, dt, source in sources:
        if url and url not in seen:
            seen[url] = (dt, source)

    all_videos = [(url, dt, src) for url, (dt, src) in seen.items()]
    print(f'[{datetime.now().isoformat()}] Found {len(all_videos)} unique videos in export')
    print(f'  Processing up to {MAX_PER_RUN} (change MAX_PER_RUN to increase)\n')

    processed = skipped = errors = 0

    for url, dt, source in all_videos[:MAX_PER_RUN]:
        if already_processed(sb_url, sb_key, url):
            skipped += 1
            continue

        print(f'  → [{source}] {url[:60]}')

        meta = fetch_tiktok_meta(url)
        time.sleep(DELAY_S)

        analysis = summarise(client, url, meta)

        # Parse saved_at date
        try:
            saved_at = str(date.fromisoformat(dt[:10]))
        except Exception:
            saved_at = str(date.today())

        row = {
            'platform':    'tiktok',
            'source_url':  url,
            'source_type': source,        # 'favorite' | 'liked' | 'watched'
            'saved_at':    saved_at,
            'title':       meta.get('title', '')[:500],
            'description': meta.get('description', '')[:1000],
            'hashtags':    meta.get('hashtags', []),
            'summary':     analysis.get('summary', ''),
            'category':    analysis.get('category', 'other'),
            'why_saved':   analysis.get('why_saved', ''),
            'creator':     meta.get('creator', ''),
        }

        if upsert_video(sb_url, sb_key, row):
            processed += 1
            print(f'    ✓ [{analysis.get("category","?")}] {analysis.get("summary","")[:80]}')
        else:
            errors += 1

    print()
    print(f'Done. Processed: {processed}  Skipped (already in DB): {skipped}  Errors: {errors}')
    print()
    if len(all_videos) > MAX_PER_RUN:
        remaining = len(all_videos) - MAX_PER_RUN
        print(f'Note: {remaining} videos remain. Increase MAX_PER_RUN and re-run.')


if __name__ == '__main__':
    main()
