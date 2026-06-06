"""
book_picks.py — Weekly book-recommendation generator for Railway.
Schedule: every Sunday at 09:30 Israel time (07:30 UTC)  →  cron: 30 7 * * 0

Generates 3 fresh book recommendations tailored to Itay (senior backend
engineer, Tel Aviv) across engineering / leadership / fiction, deduped
against books already in Supabase, then:
  • upserts them into the Supabase `books` table
  • writes a markdown digest to educative/learning/
  • pushes the digest to GitHub (Vercel redeploys)

The dashboard's "✨ AI" button reuses the existing /api/summary type=book.

Required env vars:
  ANTHROPIC_API_KEY
  SUPABASE_URL, SUPABASE_SERVICE_KEY   (optional — skips persistence if absent)
  GITHUB_TOKEN, GITHUB_REPO            (optional — skips push if absent)
"""

import os
import json
import urllib.request
from datetime import date, datetime

INTERESTS = (
    "backend/distributed systems, AI/LLM engineering, software architecture, "
    "security, engineering leadership and career growth, plus a bit of "
    "high-quality fiction (sci-fi / literary) for enjoyment"
)

CATEGORIES = ["engineering", "leadership", "fiction"]


def _existing_titles() -> set[str]:
    """Titles already in Supabase, so we never recommend the same book twice."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not (url and key):
        return set()
    req = urllib.request.Request(
        f"{url}/rest/v1/books?select=title",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            rows = json.loads(resp.read())
        return {r["title"].strip().lower() for r in rows if r.get("title")}
    except Exception as exc:
        print(f"  Warning: could not read existing books: {exc}")
        return set()


def generate_picks(exclude: set[str]) -> list[dict]:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    avoid = ", ".join(sorted(exclude)) if exclude else "none yet"

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=900,
        messages=[{
            "role": "user",
            "content": (
                f"Recommend exactly 3 books for a 30-year-old senior backend engineer "
                f"in Tel Aviv. Interests: {INTERESTS}.\n"
                f"Pick one '{CATEGORIES[0]}', one '{CATEGORIES[1]}', one '{CATEGORIES[2]}'.\n"
                f"Do NOT recommend any of these already-suggested titles: {avoid}.\n\n"
                "Return ONLY a JSON array, no prose, each item:\n"
                '{"title": "...", "author": "...", "category": "engineering|leadership|fiction", '
                '"reason": "one sentence on why it fits him right now"}'
            ),
        }],
    )
    text = msg.content[0].text.strip()
    # Be tolerant of a fenced code block around the JSON.
    if text.startswith("```"):
        text = text.split("```")[1].lstrip("json").strip()
    return json.loads(text)


def upsert_supabase(picks: list[dict], week: date) -> None:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not (url and key):
        print("  Supabase not configured — skipping")
        return
    payload = [
        {
            "title": p["title"],
            "author": p.get("author"),
            "category": p.get("category"),
            "reason": p.get("reason"),
            "picked_week": str(week),
        }
        for p in picks
    ]
    req = urllib.request.Request(
        f"{url}/rest/v1/books",
        data=json.dumps(payload).encode(),
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        print(f"  ✓ Upserted {len(picks)} books into Supabase")
    except Exception as exc:
        print(f"  Warning: Supabase write: {exc}")


def save_markdown(picks: list[dict], week: date) -> str:
    lines = [
        f"# 📚 Book Picks — Week of {week.strftime('%B %-d, %Y')}",
        "",
        "*Auto-generated weekly. Mark status in the dashboard Reading page.*",
        "",
    ]
    for p in picks:
        lines += [
            f"## {p['title']} — *{p.get('author', 'Unknown')}*",
            f"**Category:** {p.get('category', '—')}",
            "",
            p.get("reason", ""),
            "",
        ]
    content = "\n".join(lines)
    os.makedirs("educative/learning", exist_ok=True)
    path = f"educative/learning/books_{week.strftime('%Y-%m-%d')}.md"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    print(f"  ✓ Wrote {path}")
    return path


def git_push(path: str, week: date) -> None:
    try:
        from github_push import push_file
    except ImportError:
        print("  github_push not available — skipping push")
        return
    with open(path, encoding="utf-8") as fh:
        push_file(path, fh.read(), f"auto: book picks {week}")


def main() -> None:
    week = date.today()
    print(f"[{datetime.now().isoformat()}] Generating book picks for week of {week}")
    picks = generate_picks(_existing_titles())
    if not picks:
        print("  No picks generated — done")
        return
    for p in picks:
        print(f"  • [{p.get('category')}] {p['title']} — {p.get('author')}")
    upsert_supabase(picks, week)
    path = save_markdown(picks, week)
    git_push(path, week)
    print("Done ✓")


if __name__ == "__main__":
    main()
