# CLAUDE.md — Cowork Dashboard

This file gives Claude agents working in this repo instant orientation. Read it before making any changes.

## What this repo is

`osovlanski/cowork-dashboard` is Itay's personal cowork monorepo. It serves two purposes:

1. **Infrastructure** — a pipeline that generates content automatically (Railway cron workers → Supabase → Vercel dashboard).
2. **Content store** — the generated output files (email audits, weekly plans, DIY logs, travel guides, learning notes) live here as Markdown.

It is the **single home** for all cowork outputs. Do not create parallel repos for new features — add a worker + a Supabase table + a dashboard section instead.

## Architecture

```
Railway (Python cron workers)
    ↓ writes to
Supabase (5 tables: emails, habits, habit_completions, diy_log, weekly_plans)
    ↓ read by
Vercel (dashboard.html + api/chat.js + api/summary.js)
    ↑ dashboard.html is the homepage — served at /
```

Workers also commit generated Markdown back to GitHub via the GitHub Contents API (`workers/github_push.py`).

## Folder structure

```
api/                  Vercel serverless functions (chat.js, summary.js)
config/               Supabase schema SQL + migrations + .env.example
deploy/nanoclaw-ec2/  EC2 bootstrap kit for the NanoClaw assistant
docs/                 ROADMAP.md, TOOLS.md, REPO-SCAN.md
educative/learning/   Course notes and Udemy trackers
fun/
  diy/                DIY project log (daily_log.md) + project ideas
  stories/            Reading recommendations
  travel/             Travel guides (Israel, Europe, Africa)
outputs/              Ephemeral agent output files — gitignored
plugins/              Local Claude Code plugins (cowork-ai-starter)
productive/
  cv/emails/          Job application email audits
  emails/             Daily Gmail inbox audits (audit_YYYY-MM-DD.md)
recurring/
  plans/              Weekly plans (week_YYYY-MM-DD.md) + template
scripts/              One-time setup scripts (seed_supabase.py, etc.)
workers/              Railway cron workers (Python)
```

## Workers and cron schedules

| Worker | File | Schedule (Israel time) | What it does |
|--------|------|------------------------|--------------|
| Email audit | `workers/email_audit.py` | Daily 08:00 | Gmail → Claude → `productive/emails/audit_YYYY-MM-DD.md` |
| DIY log | `workers/diy_log.py` | Daily 07:00 | Generates daily DIY entry → `fun/diy/daily_log.md` |
| Weekly plan | `workers/weekly_plan.py` | Sunday 18:00 | Generates full week plan → `recurring/plans/week_YYYY-MM-DD.md` |
| Market brief | `workers/market_brief.py` | Daily 07:30 | Market + capital-markets brief → Supabase |
| Deal scan | `workers/deal_scan.py` | Daily 09:00 | eBay deal scan → Supabase |
| Book picks | `workers/book_picks.py` | Weekly Sunday | Book recommendations → Supabase |
| Telegram briefing | `workers/telegram_briefing.py` | On-demand | Sends briefing to Telegram via NanoClaw |
| TikTok import | `workers/tiktok_import.py` | On-demand | Imports TikTok saves |
| YouTube import | `workers/youtube_import.py` | On-demand | Imports YouTube watch-later |

## Key conventions

- **One domain, one folder.** Generated files go in their domain folder, not the root.
- **File naming:** `audit_YYYY-MM-DD.md`, `week_YYYY-MM-DD.md` — always ISO date suffixes.
- **Never commit secrets.** `.env`, `workers/credentials.json`, `workers/token.json` are gitignored. Use env vars on Railway/Vercel.
- **`outputs/` is ephemeral.** Agent scratch files go there — it is gitignored and not deployed.
- **Dashboard is a single HTML file.** `dashboard.html` is the entire frontend. No build step. Add new sections directly in that file.
- **Vercel root route** is `dashboard.html` (rewritten in `vercel.json`). Do not rename it to `index.html`.

## Environment variables

Set in Railway (workers) and Vercel (api functions):

| Variable | Used by |
|----------|---------|
| `ANTHROPIC_API_KEY` | All workers, Vercel api |
| `SUPABASE_URL` | All workers, dashboard, Vercel api |
| `SUPABASE_SERVICE_KEY` | Workers, Vercel api |
| `SUPABASE_ANON_KEY` | Dashboard (client-side) |
| `GMAIL_CLIENT_ID/SECRET/REFRESH_TOKEN` | email_audit.py |
| `GITHUB_TOKEN` | github_push.py |
| `GIT_USER_NAME`, `GIT_USER_EMAIL` | github_push.py |

## Adding a new tool — checklist

1. `workers/<tool>.py` — the Railway cron worker
2. `config/migration_<tool>.sql` — new Supabase table(s)
3. `api/<tool>.js` (optional) — Vercel AI endpoint if on-demand AI is needed
4. Add a section to `dashboard.html`
5. Add the cron to `railway.toml`
6. Document in `docs/ROADMAP.md`

## Memory

See `memory.md` in this folder for persistent facts about Itay — profile, habits, learning path, preferences.
