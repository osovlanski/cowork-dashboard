# New tools — setup guide

Three tools were added on top of the existing GitHub → Railway → Supabase → Vercel spine,
following the same pattern as `weekly_plan.py` / `diy_log.py`:

| Tool | Worker | Supabase table | Dashboard page | Cron (UTC) |
|---|---|---|---|---|
| Finance daily brief | `workers/market_brief.py` | `market_brief` | Markets | `30 6 * * 1-5` |
| Product deal scan | `workers/deal_scan.py` | `deals` | Deals | `0 7 * * *` |
| Book picks | `workers/book_picks.py` | `books` | Reading | `30 7 * * 0` |

## 1. Apply the database migration

Supabase → SQL Editor → New query → paste and run **`config/migration_add_tools.sql`**.
This creates `books`, `market_brief`, `deals` with the same `anon_all` RLS policy as the
existing tables. Safe to re-run.

## 2. Add Railway services

For each worker create a Railway service from this repo (the build is shared via
`railway.toml`/nixpacks) and set, under **Settings → Deploy**:

- **market-brief** — Start Command `python workers/market_brief.py`, cron `30 6 * * 1-5`
- **deal-scan** — Start Command `python workers/deal_scan.py`, cron `0 7 * * *`
- **book-picks** — Start Command `python workers/book_picks.py`, cron `30 7 * * 0`

## 3. Environment variables

Shared (already set for the other workers): `ANTHROPIC_API_KEY`, `SUPABASE_URL`,
`SUPABASE_SERVICE_KEY`, and (for git write-back) `GITHUB_TOKEN`, `GITHUB_REPO`.

Tool-specific:

- **market-brief** — optional `WATCHLIST` (comma-separated Stooq symbols, e.g.
  `^spx,^ndq,aapl.us,msft.us,nvda.us`). Quotes come from Stooq, no key required.
- **deal-scan** — `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET` (free Production keyset from
  developer.ebay.com; the Browse API uses an app token, no user login). Saved searches live
  in `config/searches.json` (committed, no secrets) — edit the terms / price ceilings there.
- **book-picks** — none beyond the shared set.

## 4. Notes / guardrails

- **Finance is information-only.** `market_brief.py` bakes a "not investment advice"
  disclaimer into every brief and prompts Claude for balanced context, not buy/sell calls.
- **Books reuse the existing AI endpoint.** The Reading page's ✨ button calls the existing
  `/api/summary` with `type: 'book'` (already supported) — no new serverless function.
- **Deals are transient.** `deal_scan.py` writes only to Supabase (no git push); the Deals
  page reads from Supabase. Old rows can be pruned with a periodic `delete` if it grows.
- **AliExpress** is intentionally not wired: it requires affiliate-API approval and scraping
  is brittle/ToS-sensitive. Add it as a second `source` in `deals` once you have API access.

## 5. Verify

After migration + first worker runs, open the dashboard:
`https://cowork-dashboard-itayosov-6518s-projects.vercel.app/` → Markets / Deals / Reading.
Empty pages with a "worker runs at …" message mean the table exists but hasn't been
populated yet — that's expected until the first cron fires (run a worker manually to seed).
