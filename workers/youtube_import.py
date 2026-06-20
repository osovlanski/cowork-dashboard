"""
youtube_import.py — Sync YouTube Watch Later + liked videos to Supabase.
Run manually or on a Railway cron (weekly is plenty).

Auth: reuses the same Google OAuth refresh token as email_audit.py.
      The token must have the YouTube readonly scope — re-run
      workers/setup_gmail_auth.py after adding youtube.readonly to SCOPES.

Env vars required:
  ANTHROPIC_API_KEY
  SUPABASE_URL
  SUPABASE_SERVICE_KEY
  GMAIL_CLIENT_ID       (reused for YouTube OAuth)
  GMAIL_CLIENT_SECRET
  GMAIL_REFRESH_TOKEN   (must include youtube.readonly scope)

Install:
  pip install google-api-python-client google-auth anthropic youtube-transcript-api
"""

import os
import json
import urllib.request
import urllib.error
from datetime import date, datetime
import anthropic
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# youtube-transcript-api is optional — skip transcript if not installed
try:
    from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
    HAS_TRANSCRIPTS = True
except ImportError:
    HAS_TRANSCRIPTS = False
    print('  ⚠ youtube-transcript-api not installed — skipping transcripts')
    print('    Install: pip install youtube-transcript-api')

MAX_PER_RUN    = 100   # cap to keep runs fast; increase as needed
TRANSCRIPT_CAP = 3000  # chars — cap transcript length sent to Claude

CATEGORIES = [
    'tutorial / how-to',
    'tech / coding',
    'system design / architecture',
    'career / productivity',
    'comedy / entertainment',
    'science / education',
    'fitness / health',
    'food / cooking',
    'travel / culture',
    'music / art',
    'news / politics',
    'other',
]


# ── Google auth ───────────────────────────────────────────────────────────────
def get_youtube_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ['GMAIL_REFRESH_TOKEN'],
        client_id=os.environ['GMAIL_CLIENT_ID'],
        client_secret=os.environ['GMAIL_CLIENT_SECRET'],
        token_uri='https://oauth2.googleapis.com/token',
        scopes=[
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/youtube.readonly',
        ],
    )
    creds.refresh(Request())
    return build('youtube', 'v3', credentials=creds)


# ── YouTube fetchers ──────────────────────────────────────────────────────────
def fetch_playlist_videos(yt, playlist_id: str, source_type: str) -> list[dict]:
    """Fetch all videos from a playlist (Watch Later = 'WL', Liked = 'LL')."""
    videos = []
    page_token = None

    while True:
        kwargs = dict(
            part='snippet,contentDetails',
            playlistId=playlist_id,
            maxResults=50,
        )
        if page_token:
            kwargs['pageToken'] = page_token

        try:
            resp = yt.playlistItems().list(**kwargs).execute()
        except Exception as e:
            print(f'  ⚠ Could not fetch playlist {playlist_id}: {e}')
            break

        for item in resp.get('items', []):
            snip   = item.get('snippet', {})
            res_id = snip.get('resourceId', {})
            vid_id = res_id.get('videoId', '')
            if not vid_id:
                continue

            thumb = snip.get('thumbnails', {})
            thumb_url = (
                thumb.get('high', {}).get('url') or
                thumb.get('medium', {}).get('url') or
                thumb.get('default', {}).get('url', '')
            )

            videos.append({
                'video_id':    vid_id,
                'source_type': source_type,
                'title':       snip.get('title', ''),
                'description': (snip.get('description') or '')[:1000],
                'creator':     snip.get('videoOwnerChannelTitle', ''),
                'thumbnail':   thumb_url,
                'saved_at':    (snip.get('publishedAt') or '')[:10],
            })

        page_token = resp.get('nextPageToken')
        if not page_token:
            break

    return videos


def get_video_durations(yt, video_ids: list[str]) -> dict[str, int]:
    """Batch-fetch duration in seconds for a list of video IDs."""
    durations = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        try:
            resp = yt.videos().list(part='contentDetails', id=','.join(batch)).execute()
            for item in resp.get('items', []):
                dur_str = item['contentDetails'].get('duration', 'PT0S')
                # Parse ISO 8601 duration (e.g. PT14M23S)
                import re
                h = int((re.findall(r'(\d+)H', dur_str) or ['0'])[0])
                m = int((re.findall(r'(\d+)M', dur_str) or ['0'])[0])
                s = int((re.findall(r'(\d+)S', dur_str) or ['0'])[0])
                durations[item['id']] = h*3600 + m*60 + s
        except Exception as e:
            print(f'  ⚠ Duration fetch failed: {e}')
    return durations


def get_transcript(video_id: str) -> str:
    """Try to get an English transcript; returns '' if unavailable."""
    if not HAS_TRANSCRIPTS:
        return ''
    try:
        parts = YouTubeTranscriptApi.get_transcript(video_id, languages=['en', 'en-US', 'he'])
        text = ' '.join(p['text'] for p in parts)
        return text[:TRANSCRIPT_CAP]
    except (NoTranscriptFound, TranscriptsDisabled):
        return ''
    except Exception:
        return ''


# ── Claude summariser ─────────────────────────────────────────────────────────
def summarise(client: anthropic.Anthropic, video: dict) -> dict:
    title       = video.get('title', '')
    description = video.get('description', '')[:400]
    transcript  = video.get('transcript', '')[:TRANSCRIPT_CAP]
    creator     = video.get('creator', '')
    duration_s  = video.get('duration_s', 0)
    duration_str = f'{duration_s // 60}m {duration_s % 60}s' if duration_s else 'unknown'

    content_block = f'Title: {title}\nChannel: {creator}\nDuration: {duration_str}\n'
    if transcript:
        content_block += f'Transcript excerpt:\n{transcript}'
    elif description:
        content_block += f'Description: {description}'

    if not title:
        return {'summary': '(no metadata)', 'category': 'other', 'why_saved': ''}

    try:
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=300,
            messages=[{
                'role': 'user',
                'content': f"""Analyse this saved YouTube video for Itay — 30yo senior backend engineer in Tel Aviv.

{content_block}

Reply with ONLY a JSON object (no markdown):
{{
  "summary": "2 sentences: what the video covers and the key takeaway",
  "category": "one of: {', '.join(CATEGORIES)}",
  "why_saved": "one sentence on why an engineer would save this"
}}""",
            }]
        )
        return json.loads(msg.content[0].text)
    except Exception as e:
        print(f'    ⚠ Claude error: {e}')
        return {'summary': title, 'category': 'other', 'why_saved': ''}


# ── Supabase helpers ──────────────────────────────────────────────────────────
def already_in_db(sb_url: str, sb_key: str, video_id: str) -> bool:
    import urllib.parse
    url = f'{sb_url}/rest/v1/videos?source_url=eq.{urllib.parse.quote("https://youtube.com/watch?v=" + video_id)}&select=id&limit=1'
    req = urllib.request.Request(url, headers={'apikey': sb_key, 'Authorization': f'Bearer {sb_key}'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return len(json.loads(resp.read())) > 0
    except Exception:
        return False


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


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    sb_url = os.environ['SUPABASE_URL']
    sb_key = os.environ['SUPABASE_SERVICE_KEY']

    print(f'[{datetime.now().isoformat()}] YouTube import starting')

    yt     = get_youtube_service()
    print('  ✓ YouTube authenticated')

    client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

    # Fetch Watch Later (WL) and Liked Videos (LL)
    all_videos: list[dict] = []
    for playlist_id, source_type in [('WL', 'watch_later'), ('LL', 'liked')]:
        items = fetch_playlist_videos(yt, playlist_id, source_type)
        print(f'  → {source_type}: {len(items)} videos')
        all_videos.extend(items)

    # Deduplicate by video_id
    seen = {}
    for v in all_videos:
        if v['video_id'] not in seen:
            seen[v['video_id']] = v
    unique = list(seen.values())
    print(f'  → {len(unique)} unique videos total (capped at {MAX_PER_RUN})\n')

    # Batch-fetch durations
    ids = [v['video_id'] for v in unique[:MAX_PER_RUN]]
    durations = get_video_durations(yt, ids)

    processed = skipped = errors = 0
    for video in unique[:MAX_PER_RUN]:
        vid_id = video['video_id']
        url    = f'https://youtube.com/watch?v={vid_id}'

        if already_in_db(sb_url, sb_key, vid_id):
            skipped += 1
            continue

        print(f'  → {video["source_type"]} | {video["title"][:60]}')

        video['duration_s']  = durations.get(vid_id, 0)
        video['transcript']  = get_transcript(vid_id)

        analysis = summarise(client, video)

        row = {
            'platform':    'youtube',
            'source_url':  url,
            'source_type': video['source_type'],
            'saved_at':    video['saved_at'] or str(date.today()),
            'title':       video['title'][:500],
            'description': video['description'][:1000],
            'hashtags':    [],
            'creator':     video['creator'][:200],
            'duration_s':  video['duration_s'],
            'thumbnail':   video['thumbnail'],
            'transcript':  video['transcript'][:3000] if video['transcript'] else None,
            'summary':     analysis.get('summary', ''),
            'category':    analysis.get('category', 'other'),
            'why_saved':   analysis.get('why_saved', ''),
        }

        if upsert_video(sb_url, sb_key, row):
            processed += 1
            cat = analysis.get('category', '?')
            print(f'    ✓ [{cat}] {analysis.get("summary","")[:80]}')
        else:
            errors += 1

    print()
    print(f'Done. Processed: {processed}  Skipped: {skipped}  Errors: {errors}')
    if len(unique) > MAX_PER_RUN:
        print(f'Note: {len(unique)-MAX_PER_RUN} remaining — increase MAX_PER_RUN')


if __name__ == '__main__':
    main()
