# Cowork Dashboard — Setup Guide

Complete stack: **GitHub → Railway (cron workers) → Supabase (storage) → Vercel (dashboard + AI API)**

---

## Prerequisites

- GitHub account + repo for this folder
- [Railway](https://railway.app) account
- [Vercel](https://vercel.com) account
- [Supabase](https://supabase.com) account
- Anthropic API key
- Google Cloud project (for Gmail OAuth)

---

## Step 1 — Push to GitHub

```bash
cd /Users/itayos/cowork
git init
git add .
git commit -m "initial: cowork dashboard"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

Add a `.gitignore` to keep secrets out:

```
.env
config/.env
workers/credentials.json
workers/token.json
```

---

## Step 2 — Supabase: Create Project & Schema

1. Go to [supabase.com](https://supabase.com) → **New Project**
2. Name it `cowork-dashboard`, pick the closest region (EU West for Tel Aviv)
3. Once created, go to **SQL Editor → New query**
4. Paste and run the contents of `config/supabase_schema.sql`
5. Go to **Project Settings → API** and copy:
   - **URL** → `SUPABASE_URL`
   - **anon / public key** → `SUPABASE_ANON_KEY`
   - **service_role key** → `SUPABASE_SERVICE_KEY`

---

## Step 3 — Gmail OAuth (one-time local setup)

> This generates a refresh token so Railway can read your Gmail without you being present.

### 3a. Create Google Cloud credentials

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or use an existing one)
3. Enable the **Gmail API**: APIs & Services → Library → search "Gmail API" → Enable
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
   - Application type: **Desktop app**
   - Name: `cowork-railway`
5. Download the JSON file → save as `workers/credentials.json`

### 3b. Run the auth script

```bash
cd /Users/itayos/cowork
pip install google-auth-oauthlib --break-system-packages
python workers/setup_gmail_auth.py
```

A browser window opens → sign in → grant access.  
The script prints three values — copy them for the next step:

```
GMAIL_CLIENT_ID=...
GMAIL_CLIENT_SECRET=...
GMAIL_REFRESH_TOKEN=...
```

---

## Step 4 — Railway: Deploy Cron Workers

### 4a. Create a Railway project

1. Go to [railway.app](https://railway.app) → **New Project → Deploy from GitHub repo**
2. Select your cowork repo

### 4b. Add environment variables

In Railway → your project → **Variables**, add:

| Variable | Value |
|---|---|
| `ANTHROPIC_API_KEY` | your Anthropic key |
| `SUPABASE_URL` | from Step 2 |
| `SUPABASE_SERVICE_KEY` | from Step 2 (service role) |
| `GMAIL_CLIENT_ID` | from Step 3 |
| `GMAIL_CLIENT_SECRET` | from Step 3 |
| `GMAIL_REFRESH_TOKEN` | from Step 3 |
| `GIT_USER_NAME` | your GitHub username |
| `GIT_USER_EMAIL` | itayosov@gmail.com |
| `GITHUB_TOKEN` | a GitHub PAT with `repo` scope |

### 4c. Configure services

Railway reads `railway.toml` automatically. You'll see three services:

| Service | Schedule | What it does |
|---|---|---|
| `email-audit` | 08:00 Israel (05:00 UTC) | Fetches Gmail → Claude audit → saves MD |
| `diy-log` | 07:00 Israel (04:00 UTC) | Generates daily DIY log entry |
| `weekly-plan` | Sunday 18:00 Israel (15:00 UTC) | Generates next week's full plan |

### 4d. Allow git push from Railway

The workers commit and push generated files back to GitHub. For this to work:

1. Create a **GitHub Personal Access Token** (Settings → Developer settings → PAT → Fine-grained)
   - Repository access: your cowork repo
   - Permissions: **Contents** → Read and Write
2. In Railway, set `GITHUB_TOKEN` to this token
3. The workers use it automatically via the `git push` calls in the worker scripts

> Tip: Run a worker manually first to test — Railway → service → **Deploy → Run now**

---

## Step 5 — Vercel: Deploy Dashboard + AI API

### 5a. Import project

1. Go to [vercel.com](https://vercel.com) → **Add New → Project**
2. Import your GitHub repo
3. Framework preset: **Other** (it's a static HTML file + one serverless function)
4. Root directory: leave as `/` (repo root)

### 5b. Add environment variables

In Vercel → your project → **Settings → Environment Variables**, add:

| Variable | Environment | Value |
|---|---|---|
| `ANTHROPIC_API_KEY` | Production | your Anthropic key |
| `SUPABASE_URL` | Production | from Step 2 |
| `SUPABASE_SERVICE_KEY` | Production | service role key |

### 5c. Deploy

Click **Deploy**. Vercel builds and deploys. You get a URL like `https://cowork-itay.vercel.app`.

---

## Step 6 — Configure the Dashboard

Open `dashboard.html` and fill in the `CONFIG` block near the top:

```js
const CONFIG = {
  supabase: {
    url:     'https://xxxxxxxxxxxxxxxxxxxx.supabase.co',   // Step 2
    anonKey: 'eyJ...',                                      // Step 2 anon key
  },
  vercel: {
    apiUrl: 'https://cowork-itay.vercel.app',              // Step 5 URL
  },
};
```

Commit and push — Vercel auto-redeploys.

---

## Step 7 — Verify Everything

| Check | How |
|---|---|
| Supabase schema | Supabase → Table Editor → see 5 tables |
| Railway workers | Railway → service → Logs (run manually first) |
| Email audit | Check `productive/emails/` in GitHub after first run |
| DIY log | Check `fun/diy/daily_log.md` in GitHub |
| Weekly plan | Check `recurring/plans/` in GitHub after Sunday |
| Vercel AI summary | Open dashboard → click ✨ on any card |
| Habit persistence | Check dashboard habits → refresh → still checked |

---

## Cron Schedules Summary

```
email-audit   0 5 * * *    → 08:00 Israel (daily)
diy-log       0 4 * * *    → 07:00 Israel (daily)
weekly-plan   0 15 * * 0   → 18:00 Israel (Sunday only)
```

---

## Cost Estimate (monthly)

| Service | Free tier | Expected cost |
|---|---|---|
| Railway | $5 credit/mo included | ~$0–2 (cron workers, low CPU) |
| Vercel | Hobby is free | $0 |
| Supabase | 500MB free | $0 |
| Anthropic | Pay per use | ~$0.10–0.50 (Haiku is cheap) |

**Total: effectively free or < $3/month.**

---

## Troubleshooting

**Gmail auth fails on Railway**  
→ Check that `GMAIL_REFRESH_TOKEN` is set and wasn't accidentally truncated.  
→ Re-run `setup_gmail_auth.py` locally to get a fresh token.

**Git push fails in worker**  
→ Verify `GITHUB_TOKEN` has `Contents: Write` permission on the repo.  
→ Check that `GIT_USER_NAME` and `GIT_USER_EMAIL` are set.

**AI summary button shows error**  
→ Check Vercel function logs: Vercel → project → Functions tab.  
→ Verify `ANTHROPIC_API_KEY` is set in Vercel env vars.

**Habits not persisting**  
→ Check browser console for Supabase errors.  
→ Confirm `CONFIG.supabase.url` and `anonKey` are correctly filled in `dashboard.html`.
