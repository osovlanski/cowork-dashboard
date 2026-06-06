"""
market_brief.py — Daily capital-markets brief for Railway.
Schedule: weekdays at 08:30 Israel time (06:30 UTC)  →  cron: 30 6 * * 1-5

For each symbol on the watchlist it pulls recent daily closes from Stooq
(free, no API key), computes a simple trend snapshot (last price, 1-day %,
vs 20-day moving average), then asks Claude Haiku to write a concise,
INFORMATION-ONLY market brief. It then:
  • upserts the brief + structured data into Supabase `market_brief`
  • writes a markdown copy to finance/
  • pushes to GitHub (Vercel redeploys)

⚠️  This is market information and balanced context only — NOT personalized
    investment advice. Every output carries that disclaimer.

Watchlist: set WATCHLIST env (comma-separated Stooq symbols, e.g.
"aapl.us,msft.us,nvda.us,^spx,^ndq"). Falls back to a sensible default.

Required env vars:
  ANTHROPIC_API_KEY
  WATCHLIST                            (optional)
  SUPABASE_URL, SUPABASE_SERVICE_KEY   (optional)
  GITHUB_TOKEN, GITHUB_REPO            (optional)
"""

import os
import io
import csv
import json
import urllib.request
import urllib.parse
from datetime import date, datetime

DISCLAIMER = (
    "_Information and context only — not personalized investment advice. "
    "Do your own research and consult a licensed advisor before trading._"
)

DEFAULT_WATCHLIST = ["^spx", "^ndq", "aapl.us", "msft.us", "nvda.us", "googl.us"]


def watchlist() -> list[str]:
    raw = os.environ.get("WATCHLIST", "")
    return [s.strip() for s in raw.split(",") if s.strip()] or DEFAULT_WATCHLIST


def fetch_closes(symbol: str, days: int = 40) -> list[float]:
    """Return the last `days` daily closing prices for a Stooq symbol (oldest→newest)."""
    url = f"https://stooq.com/q/d/l/?s={urllib.parse.quote(symbol)}&i=d"
    req = urllib.request.Request(url, headers={"User-Agent": "cowork-dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        rows = list(csv.DictReader(io.StringIO(resp.read().decode())))
    closes = [float(r["Close"]) for r in rows if r.get("Close") not in (None, "", "N/D")]
    return closes[-days:]


def snapshot(symbol: str) -> dict | None:
    try:
        closes = fetch_closes(symbol)
        if len(closes) < 2:
            return None
        last, prev = closes[-1], closes[-2]
        window = closes[-20:] if len(closes) >= 20 else closes
        ma20 = sum(window) / len(window)
        chg_pct = (last - prev) / prev * 100 if prev else 0.0
        trend = "above 20-day avg" if last >= ma20 else "below 20-day avg"
        return {
            "symbol": symbol,
            "price": round(last, 2),
            "chg_pct": round(chg_pct, 2),
            "ma20": round(ma20, 2),
            "trend": trend,
        }
    except Exception as exc:
        print(f"  Warning: {symbol} snapshot failed: {exc}")
        return None


def build_brief(snapshots: list[dict], today: date) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    table = "\n".join(
        f"- {s['symbol']}: {s['price']} ({s['chg_pct']:+.2f}% d/d, {s['trend']})"
        for s in snapshots
    )
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=900,
        messages=[{
            "role": "user",
            "content": (
                f"Date: {today:%B %-d, %Y}. Here is today's watchlist snapshot:\n\n{table}\n\n"
                "Write a concise daily market brief (markdown) for a tech-savvy retail "
                "reader. Sections: '## Snapshot' (2-3 sentences on overall tone and notable "
                "movers from the data above), '## Themes to watch' (3 bullets on macro/sector "
                "trends a reader should be aware of). Be balanced — present context, not buy/sell "
                "calls. Do not invent precise numbers beyond what's given."
            ),
        }],
    )
    body = msg.content[0].text.strip()
    return (
        f"# 📈 Market Brief — {today:%B %-d, %Y}\n\n{DISCLAIMER}\n\n{body}\n"
    )


def upsert_supabase(today: date, brief: str, data: dict) -> None:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not (url and key):
        print("  Supabase not configured — skipping")
        return
    payload = json.dumps({"date": str(today), "brief": brief, "data": data}).encode()
    req = urllib.request.Request(
        f"{url}/rest/v1/market_brief",
        data=payload,
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
        print("  ✓ Stored in Supabase")
    except Exception as exc:
        print(f"  Warning: Supabase write: {exc}")


def save_markdown(today: date, brief: str) -> str:
    os.makedirs("finance", exist_ok=True)
    path = f"finance/brief_{today:%Y-%m-%d}.md"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(brief)
    print(f"  ✓ Wrote {path}")
    return path


def git_push(path: str, today: date) -> None:
    try:
        from github_push import push_file
    except ImportError:
        print("  github_push not available — skipping push")
        return
    with open(path, encoding="utf-8") as fh:
        push_file(path, fh.read(), f"auto: market brief {today}")


def main() -> None:
    today = date.today()
    print(f"[{datetime.now().isoformat()}] Building market brief for {today}")
    snaps = [s for s in (snapshot(sym) for sym in watchlist()) if s]
    if not snaps:
        print("  No market data fetched — aborting (no brief written)")
        return
    brief = build_brief(snaps, today)
    data = {s["symbol"]: s for s in snaps}
    upsert_supabase(today, brief, data)
    path = save_markdown(today, brief)
    git_push(path, today)
    print("Done ✓")


if __name__ == "__main__":
    main()
