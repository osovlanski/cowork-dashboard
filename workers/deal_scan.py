"""
deal_scan.py — Daily product-deal scanner for Railway.
Schedule: daily at 09:00 Israel time (07:00 UTC)  →  cron: 0 7 * * *

Runs each saved search against the eBay Browse API, keeps listings under the
search's price ceiling, asks Claude Haiku to score value-for-money (1-10) and
dedupe near-identical items, then:
  • upserts the best hits into the Supabase `deals` table
  • pushes nothing to git (deals are transient; the dashboard reads Supabase)

Saved searches: config/searches.json (committed, no secrets), e.g.
  [
    { "term": "mechanical keyboard hot-swap", "max_price": 80, "currency": "USD" },
    { "term": "anker usb-c hub",               "max_price": 40, "currency": "USD" }
  ]

eBay setup (free): create an app at developer.ebay.com → use the Production
Client ID / Client Secret. The Browse API uses an app (client-credentials)
token — no user login needed.

Required env vars:
  EBAY_CLIENT_ID, EBAY_CLIENT_SECRET
  ANTHROPIC_API_KEY                    (optional — skips scoring if absent)
  SUPABASE_URL, SUPABASE_SERVICE_KEY   (optional — prints results if absent)
"""

import os
import json
import base64
import urllib.request
import urllib.parse
from datetime import date, datetime

EBAY_OAUTH = "https://api.ebay.com/identity/v1/oauth2/token"
EBAY_SEARCH = "https://api.ebay.com/buy/browse/v1/item_summary/search"
SEARCHES_FILE = "config/searches.json"
MAX_PER_SEARCH = 10


def load_searches() -> list[dict]:
    raw = os.environ.get("EBAY_SEARCHES")
    if raw:
        return json.loads(raw)
    if os.path.exists(SEARCHES_FILE):
        with open(SEARCHES_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    print(f"  No searches configured ({SEARCHES_FILE} missing and EBAY_SEARCHES unset)")
    return []


def ebay_token() -> str:
    cid = os.environ["EBAY_CLIENT_ID"]
    secret = os.environ["EBAY_CLIENT_SECRET"]
    basic = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope",
    }).encode()
    req = urllib.request.Request(
        EBAY_OAUTH,
        data=data,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())["access_token"]


def search_ebay(token: str, term: str, max_price: float, currency: str) -> list[dict]:
    params = {
        "q": term,
        "limit": str(MAX_PER_SEARCH),
        "filter": f"price:[..{max_price}],priceCurrency:{currency},buyingOptions:{{FIXED_PRICE}}",
        "sort": "price",
    }
    url = f"{EBAY_SEARCH}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            items = json.loads(resp.read()).get("itemSummaries", [])
    except Exception as exc:
        print(f"  Warning: eBay search '{term}' failed: {exc}")
        return []

    out = []
    for it in items:
        price = it.get("price", {})
        out.append({
            "source": "ebay",
            "search_term": term,
            "title": it.get("title", ""),
            "price": float(price.get("value")) if price.get("value") else None,
            "currency": price.get("currency", currency),
            "url": it.get("itemWebUrl", ""),
            "image": (it.get("image") or {}).get("imageUrl"),
            "condition": it.get("condition"),
        })
    return out


def score_deals(deals: list[dict]) -> list[dict]:
    """Ask Claude to score value (1-10) and flag the keepers. No-op if no API key."""
    if not os.environ.get("ANTHROPIC_API_KEY") or not deals:
        return deals
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    listing = "\n".join(
        f"{i}. {d['title']} — {d['price']} {d['currency']}" for i, d in enumerate(deals)
    )
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{
                "role": "user",
                "content": (
                    "Score these product listings for value-for-money (1-10) and give a "
                    "one-line reason each. Drop obvious junk/duplicates.\n\n"
                    f"{listing}\n\n"
                    'Return ONLY a JSON array: [{"index": 0, "value_score": 8, '
                    '"reason": "..."}] for the ones worth keeping.'
                ),
            }],
        )
        text = msg.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        scored = json.loads(text)
    except Exception as exc:
        print(f"  Warning: scoring failed, keeping unscored: {exc}")
        return deals

    kept = []
    for s in scored:
        idx = s.get("index")
        if isinstance(idx, int) and 0 <= idx < len(deals):
            d = dict(deals[idx])
            d["value_score"] = s.get("value_score")
            d["reason"] = s.get("reason")
            kept.append(d)
    return kept or deals


def upsert_supabase(deals: list[dict]) -> None:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not (url and key):
        print("  Supabase not configured — printing results instead:")
        for d in deals:
            print(f"    [{d.get('value_score', '?')}] {d['title']} — {d['price']} {d['currency']}")
        return
    payload = [{**d, "found_date": str(date.today())} for d in deals]
    req = urllib.request.Request(
        f"{url}/rest/v1/deals",
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
        urllib.request.urlopen(req, timeout=15)
        print(f"  ✓ Upserted {len(deals)} deals into Supabase")
    except Exception as exc:
        print(f"  Warning: Supabase write: {exc}")


def main() -> None:
    print(f"[{datetime.now().isoformat()}] Scanning deals")
    searches = load_searches()
    if not searches:
        return
    token = ebay_token()
    all_hits: list[dict] = []
    for s in searches:
        hits = search_ebay(token, s["term"], s.get("max_price", 100), s.get("currency", "USD"))
        print(f"  • '{s['term']}': {len(hits)} hits")
        all_hits.extend(hits)
    if not all_hits:
        print("  No hits today — done")
        return
    best = score_deals(all_hits)
    upsert_supabase(best)
    print("Done ✓")


if __name__ == "__main__":
    main()
