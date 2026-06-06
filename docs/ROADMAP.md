# Cowork Enhancements — Roadmap

**Owner:** Itay Osovlanski (itayosov@gmail.com)
**Date:** 2026-06-06
**Status:** Plan / roadmap only — no code changes made yet.
**Destination:** intended to live in `osovlanski/cowork-dashboard` (e.g. `docs/ROADMAP.md`).

This document covers the seven enhancements requested, grounded in what was actually
found by inspecting the live Vercel project, the cloned `cowork-dashboard` repo, and the
two local company repos (`nano-personal-assistant`, `dotfiles-ai`). Where access was
missing, it is called out explicitly under **Access gaps** at the end.

---

## 0. Context discovered (so the plan is grounded, not guessed)

**`cowork-dashboard` is effectively a small monorepo, not just a dashboard.** The repo
holds the dashboard app *and* the cowork output content. Layout:

- `dashboard.html` — single-file static dashboard (Supabase REST client, no build step).
- `api/chat.js`, `api/summary.js` — Vercel serverless functions (Anthropic + Supabase).
- `workers/*.py` — Railway cron workers: `email_audit.py` (08:00 IL), `diy_log.py`
  (07:00 IL), `weekly_plan.py` (Sun 18:00 IL), plus `github_push.py` (writes back via the
  GitHub Contents API), `setup_gmail_auth.py`.
- `config/` — `supabase_schema.sql`, migrations, `.env.example`.
- `scripts/` — `seed_supabase.py`, `setup_db.py`, `test_connections.py`.
- Content folders — `educative/learning`, `productive/{emails,receipts,cv}`,
  `recurring/plans`, `fun/{travel,stories,diy}`.

**Architecture:** GitHub → Railway (Python cron workers) → Supabase (storage) → Vercel
(dashboard + AI API). This is the spine that every new "tool" below should plug into,
rather than inventing a new stack each time.

**So: yes, treat `cowork-dashboard` as the monorepo** for all cowork outputs and tools.
Recommended convention going forward, so it doesn't become a junk drawer:

```
/workers/<tool>.py        # the scheduled producer (Railway cron)
/api/<tool>.js            # any on-demand AI endpoint (Vercel)
/config/                  # schema + migrations (one file per feature)
/<domain>/                # generated content (finance/, shopping/, books/ ...)
dashboard.html            # add a nav section + page per tool
docs/ROADMAP.md           # this file
```

---

## 1. Finance tool — capital-market analysis, trends, investment ideas

**Good news: you already have most of the building blocks installed.** The `sp-global`
plugin is present with four relevant skills:

- `sp-global:tear-sheet` — company one-pager from S&P Capital IQ data.
- `sp-global:earnings-preview-beta` — 4–5 page equity-research preview.
- `sp-global:funding-digest` — capital-markets / deal-flow briefing slide.
- `sp-global:sp-capital-iq-excel-pro` — live-data Excel models (DCF, comps, peers).

Plus the registry has `PitchBook Premium`, `Morningstar Credit Analytics`, and `Kpler`
(commodities) if you want deeper coverage later.

**Recommended approach (phased):**

1. **Phase 1 — use what's there.** Wire a `finance/` folder + a `workers/market_brief.py`
   Railway cron that runs each morning, calls `WebSearch` for market-moving headlines and
   the `sp-global` skills for any tickers on a watchlist, and writes a daily brief into
   Supabase. Surface it as a "Markets" page in `dashboard.html`.
2. **Phase 2 — watchlist + trends.** Store a watchlist table in Supabase; compute simple
   trend signals (50/200-day moving averages, % moves, sector rotation) in the worker.
3. **Phase 3 — "ideas," not "advice."** Generate a *research-style* summary (bull/bear
   case, catalysts, valuation context) per watchlist name.

**Hard guardrail:** the tool must present *information and balanced cases*, never
personalized buy/sell recommendations. Label every output "not financial advice." This is
both the right call and what keeps the feature safe to ship.

**Effort:** S–M (Phase 1 is a day; skills already do the heavy lifting).

---

## 2. Repo scan — find stale / in-progress projects and recommend next steps

**Status: partially blocked.** The GitHub connector did not expose repository-list tools
in this session, so a full automated scan of every `itayosov` / `osovlanski` repo could not
be completed. What *is* confirmed from Vercel:

| Project | Vercel state | Note |
|---|---|---|
| `cowork-dashboard` | Live (READY) | Active; see item 5. |
| `pocketknife` | Project exists on Vercel | Mentioned by you — needs a look. |
| `vinodirect` | Project exists | Created Jan 2026. |
| `v0-portfolio-website-creation` | Project exists | v0-generated portfolio. |
| `zuzim` | Not found on Vercel | Likely GitHub-only; needs connector to inspect. |

**Recommended approach:**

1. Authorize the GitHub connector (or paste a read-only PAT), then run a scan that pulls,
   per repo: last-commit date, open branches/PRs, presence of a README/TODO, CI status,
   and whether it's deployed anywhere.
2. Score each repo on a simple **"revive / finish / archive"** rubric: last activity, %
   complete (heuristic from TODOs + open issues), and strategic value to you.
3. Produce a one-page **portfolio digest** (same format as `funding-digest`) and, for the
   top 2–3 "finish" candidates, a concrete next-step checklist.
4. Optionally schedule this monthly so the backlog never goes stale silently.

**Effort:** S once GitHub access is granted. **Blocker:** GitHub connector auth.

---

## 3. Personal assistant on EC2 (from `nano-personal-assistant` / NanoClaw)

**What it is:** NanoClaw runs Claude agents inside isolated **Docker containers**, with
channel adapters (Telegram, Discord, WhatsApp, Slack, Signal, iMessage, Teams, etc.). On
your Mac it's wired via a `launchd` plist (`com.nanoclaw.plist`); the build is in
`container/` (Dockerfile + `agent-runner`). Setup is `nanoclaw.sh`.

**Key fact for the EC2 move:** `launchd` is macOS-only. On EC2 (Linux) you replace it with
**systemd**. Everything else (Docker, Node/pnpm, the container build, channel pairing) is
portable.

**Recommended EC2 path:**

1. **Instance:** Ubuntu 22.04, `t3.medium` (2 vCPU / 4 GB) as a starting point — the agent
   container plus Docker needs headroom; `t3.small` may be tight.
2. **Bootstrap:** install Docker, Node, pnpm; clone the repo; run `nanoclaw.sh` (it's
   designed to bootstrap a fresh machine and hand off to Claude Code on failures).
3. **Service:** create a `systemd` unit (mirroring `launchd/com.nanoclaw.plist`) so it
   restarts on boot/crash. This is the one real porting task.
4. **Channel choice:** start with **Telegram** — it polls outbound, so it works on a
   headless box with **no inbound ports open**. WhatsApp/Slack/Teams need a public webhook
   endpoint (then add Caddy/Nginx + a domain + TLS, and open 443 only).
5. **Secrets:** Anthropic API key and channel tokens via environment / SSM Parameter Store,
   never committed.
6. **Security group:** default-deny inbound; SSH from your IP only; 443 only if a webhook
   channel needs it. This matches NanoClaw's "secure by isolation" philosophy.
7. **State & cost:** persist the DB + group folders on the EBS volume (snapshot for backup);
   consider stop/start scheduling to control cost if it's personal-use.

**Open decision for you:** always-on EC2 vs. cheaper alternatives (a small always-on box,
or Fly.io/Railway which you already use). EC2 is right if you want full control + Docker
isolation; note Apple-container networking quirks in the repo's docs don't apply on Linux.

**Effort:** M — mostly the systemd unit, channel pairing, and security-group hygiene.

---

## 4. Copy `dotfiles-ai` concepts to coworkers

**What `dotfiles-ai` is:** the company's "AI coding standards" repo — one source of truth that
`setup.sh` fans out into `~/.claude` and `~/.cursor` for Claude Code, Cursor, and Copilot.
It's a genuinely strong template. Notable assets:

- **Rules mirror:** edit `CLAUDE.md` once; a pre-commit hook regenerates `AGENTS.md`,
  `.cursor/rules/ai-rules.mdc`, and `.github/copilot-instructions.md`.
- **~40 skills** (`.claude/skills/`), e.g. `ai-trends-scan`, `dev-lifecycle`,
  `company-pr-review`, `secret-scan`, `coralogix-*-triage`, ADO + gitnexus suites.
- **8 sub-agents** (`code-reviewer`, `security-reviewer`, `planner`, `test-writer`, …).
- **11 safety hooks** (`pre-bash-secret-scan`, `pre-write-secret-scan`,
  `pre-bash-block-destructive`, `protect-files`, `post-edit-format`, `stop-test-gate`, …).
- **`ai-trends-scan` → `proposals/` loop:** a daily scan (`scripts/run-trends-scan.sh` +
  `com.company.ai-trends-scan.plist`) drafts candidate skills/rules/agents/hooks into
  `proposals/<date>/` for human review — nothing auto-merges. ~40 days of proposals exist.
- **`tools/dashboard`:** a ~600-line TS/Node local UI to accept/reject those proposals.
- **`shraga`:** a monitoring/routine-automation sub-project (Coralogix/Grafana/Dynatrace
  triage + weekly summary) built *on top of* the same scaffolding.

**Concepts worth packaging for coworkers (highest value first):**

1. **The trends-scan → proposals → review-dashboard loop.** This is the standout idea:
   continuous improvement of the team's AI tooling with a human gate. Package it as a
   drop-in.
2. **The safety hooks** (secret-scan on write/bash, destructive-command block, file
   protection). Cheap to adopt, high value, low controversy.
3. **The single-source rules mirror** (CLAUDE.md → Cursor/Copilot) so a team shares one
   ruleset across three tools.
4. **The dev-lifecycle orchestrator** (PBI → Design → Impl → Tests → Review → Ship with
   ADO/wiki/test-plan sync) for teams on Azure DevOps.

**Recommended delivery mechanism:** this maps cleanly onto a **Cowork/Claude Code plugin**
(you have the `create-cowork-plugin` and `cowork-plugin-customizer` skills installed).
Bundle the hooks + the trends-scan skill + the proposals dashboard into a shareable
`.plugin`, with an org-customization step so each team sets their own MCP tokens. That's far
easier for coworkers to adopt than "clone this repo and run setup.sh."

**Effort:** M — mostly curation + a customization layer; the assets already exist and are
proven.

---

## 5. Why the Vercel `cowork-dashboard` "isn't working" — diagnosed

**Root cause found (not a guess):** the latest production deployment is **READY**, not
failing to build. The problem is **routing**:

- Visiting the site root `/` returns **404 NOT_FOUND**.
- Visiting `/dashboard.html` returns **200** and the full dashboard renders.

`vercel.json` only declares the two serverless functions; there is **no `index.html`** and
**no rewrite** mapping `/` to `dashboard.html`. Vercel serves static files by their literal
filename, so the homepage 404s. (It returned a clean 404, not a 401 — so this is *not*
Vercel deployment-protection/auth; the site is publicly reachable.)

**Fix (pick one, both are tiny):**

- **Option A (simplest):** rename `dashboard.html` → `index.html`. Done.
- **Option B (keep the name):** add a rewrite to `vercel.json`:

  ```json
  {
    "rewrites": [{ "source": "/", "destination": "/dashboard.html" }],
    "functions": {
      "api/chat.js":    { "maxDuration": 30 },
      "api/summary.js": { "maxDuration": 30 }
    }
  }
  ```

**After the fix, verify the data path** (these are the next things likely to look "broken"
even once `/` loads):

1. **Supabase tables/seed.** The dashboard reads `emails`, `habits`, `habit_completions`,
   `diy_log`, `weekly_plans` via REST with the anon key. If the schema/seed weren't applied
   to the current Supabase project (`lftejjbujwqrcnkbqlys`), pages show "error" or empty.
   Run `config/supabase_schema.sql` + `scripts/seed_supabase.py`.
2. **Railway workers.** If the cron workers haven't run (or Gmail OAuth/`github_push`
   isn't configured), `emails`/`diy_log`/`weekly_plans` stay empty — the UI will say "worker
   runs at 08:00" rather than erroring.
3. **`/api/chat` env.** The "✨ AI" button needs `ANTHROPIC_API_KEY`, `SUPABASE_URL`,
   `SUPABASE_SERVICE_KEY` set in Vercel project env.

**Note (minor):** the Supabase **publishable/anon** key is committed in `dashboard.html`.
That's the intended client-side key (not the service key), so it's acceptable, but worth a
conscious decision since the repo is public.

**Effort:** XS for the 404 fix; S to verify the Supabase + Railway data path.

---

## 6. Daily product-search tool (AliExpress / eBay / etc.)

**Reality check from the connector registry:** there is **no off-the-shelf MCP** for
AliExpress or eBay consumer search. Closest matches are Shopify (your own store),
Glovo (delivery), and G2 (software) — none fit "find me deals on AliExpress/eBay." So this
one needs a small custom build.

**Recommended approach (cheapest reliable path first):**

1. **eBay** has an official **Browse API** (free dev account, OAuth app token) — clean JSON
   product search. Use it directly from a `workers/deal_scan.py`.
2. **AliExpress** official data requires the **affiliate/portals API** (approval needed);
   without it, scraping is brittle and ToS-sensitive. Treat AliExpress as Phase 2, or use
   `WebSearch` / Claude-in-Chrome to pull listings on demand rather than scraping daily.
3. **Daily mechanism:** a **scheduled task** (you have the scheduler) runs each morning over
   a saved list of search terms / price thresholds, writes hits to a Supabase `deals` table,
   and surfaces a "Deals" page in `dashboard.html`. Optional: push a Telegram message via
   the NanoClaw assistant from item 3.
4. **Ranking:** have Claude Haiku score each hit for value-for-money and dedupe near-identical
   listings, so you get a short curated list, not a dump.

**Decision needed from you:** which marketplaces matter most, and your saved searches /
budget ceilings. eBay is the quick win; AliExpress depends on API approval.

**Effort:** M (eBay Browse integration + scheduled task + a dashboard page).

---

## 7. Book-recommendation tool

**This one is nearly free — the dashboard already speaks "books."** `api/summary.js`
already has a `book` prompt type ("summarize this book for a senior software engineer…").
So the plumbing for per-book AI summaries exists; you just need a *source of candidates* and
a place to show them.

**Recommended approach:**

1. **`workers/book_picks.py`** (weekly cron): generate recommendations from your interests
   (engineering + leadership + fiction for enjoyment), optionally cross-referenced with
   what's trending (`WebSearch`) and what you've already read. Write to a Supabase `books`
   table.
2. **Dashboard:** add a "Reading" page that lists picks with the existing "✨ AI summary"
   button (reuses `api/summary.js` `type: 'book'`).
3. **Optional connectors:** if you track reading in Goodreads/Notion, wire that as the
   "already read / want to read" input so picks don't repeat. (Notion connector is
   available; Goodreads has no MCP — would be manual or via a CSV export.)
4. **Personalization loop:** a 👍/👎 on each pick, stored in Supabase, feeds the next
   week's prompt.

**Effort:** S — reuses the existing summary endpoint; mostly the worker + one dashboard page.

---

## Suggested sequencing

| Phase | Items | Why this order |
|---|---|---|
| **Quick wins (this week)** | **#5** (fix the 404 — XS), **#7** (books, reuses existing endpoint), **#1 Phase 1** (finance brief from installed skills) | Highest value-to-effort; #5 unblocks everything that surfaces on the dashboard. |
| **Needs one unblock** | **#2** (repo scan — needs GitHub connector) | One auth step away from a full automated portfolio digest. |
| **Build-outs** | **#6** (eBay deals), **#1 Phases 2–3** (watchlist + ideas) | Real integrations + scheduled tasks. |
| **Infra** | **#3** (NanoClaw on EC2), **#4** (package dotfiles concepts as a plugin) | Larger, more independent efforts; do when the dashboard tools are stable. |

**Cross-cutting recommendation:** standardize every new tool on the existing spine —
*Railway worker → Supabase table → dashboard page (+ optional Vercel AI endpoint)* — and add
each as a folder in the `cowork-dashboard` monorepo. That keeps all seven coherent instead of
seven different stacks.

---

## Access gaps (what blocked full investigation)

1. **GitHub connector** exposed no repository-listing tools this session, so item #2 (full
   repo scan of `itayosov`/`osovlanski`, incl. `zuzim`) and a deep read of the `pocketknife`
   repo are pending. → Authorize GitHub (or provide a read-only PAT) to complete.
2. **Committing this file to `cowork-dashboard`** requires GitHub write auth, which isn't
   available here. This `ROADMAP.md` is delivered ready to drop into the repo (suggested path
   `docs/ROADMAP.md`); pushing needs the GitHub connector or a manual commit.
3. **Supabase / Railway runtime state** for the dashboard couldn't be inspected directly
   (no Supabase/Railway access) — item #5's data-path verification steps are therefore
   recommendations to run, not confirmed findings. The 404 root cause *is* confirmed.
```