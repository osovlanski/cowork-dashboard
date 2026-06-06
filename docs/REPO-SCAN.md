# Repo Scan — portfolio digest

**Date:** 2026-06-06 · **Method:** shallow public `git clone` (no connector needed).
Private repos (`vinodirect`, `v0-portfolio-website-creation`) could not be cloned without
auth and are pending the GitHub connector.

## Summary

| Repo | What it is | Last activity | Size / maturity | Verdict |
|---|---|---|---|---|
| **pocketknife** | Multi-agent AI platform (email, jobs, travel deals, knowledge, interview prep) — TS backend + frontend + shared | 2026-02-24 | Large: ~339 `.ts`, ~57 `.tsx`, full docs set, PRs merged (#45) | **Finish / consolidate** |
| **zuzim** | Next.js personal payments dashboard | 2026-03-01 | Early: ~9 `.ts`, 6 `.tsx`, one feature commit | **Decide: revive or fold in** |
| **cowork-dashboard** | This repo — dashboard + workers + content | active | live on Vercel | keep (primary) |
| **vinodirect** | Private — not inspected | — | — | needs GitHub auth |
| **v0-portfolio-website-creation** | Private — v0-generated portfolio | — | — | needs GitHub auth |

## pocketknife — Finish / consolidate (highest-value)

The most substantial project by far, and well-documented (ARCHITECTURE, CLOUD_SETUP,
DATABASE_MIGRATIONS, a TECH_LEAD_REVIEW). It's a real multi-agent platform: email
classification (Hebrew/English, invoice→Drive), a jobs agent (multi-source + CV matching),
travel deals, knowledge gathering, interview prep.

**The key observation:** pocketknife's feature set **overlaps heavily with the
cowork-dashboard workers** — email audit, deals, learning/knowledge. You're effectively
building the same ideas twice in two stacks. Decision to make:

- **Option A — pocketknife is the product, cowork-dashboard is the personal cockpit.**
  Keep cowork-dashboard as your lightweight personal view; treat pocketknife as the "real"
  app you finish and possibly share. Don't duplicate agents across both.
- **Option B — cowork-dashboard wins, harvest pocketknife.** If pocketknife stalled because
  it got too big, port only the agents you actually use (email, jobs) into the simpler
  worker pattern here and archive pocketknife.

Either way, the recommendation is **stop parallel-building**. Pick one home per capability.
Given pocketknife has a tech-lead review doc already, skim that first — it likely lists the
exact gaps to "finish."

## zuzim — Revive or fold in

A clean but early Next.js "personal payments dashboard" — essentially scaffolding plus one
feature commit. Two realistic paths:

- **Fold in:** payments/budgeting is already a theme in your weekly-plan worker (the ₪1,500/
  week budget block). A "Money" page in cowork-dashboard could absorb zuzim's intent without
  maintaining a separate Next.js app.
- **Revive standalone** only if you want a richer, dedicated finance app (bank-sync, charts)
  that doesn't fit the single-file dashboard.

Recommendation: **fold the concept into cowork-dashboard** unless you have a concrete reason
to keep a separate payments app — it's not far enough along to be costly to abandon.

## Next step to complete this scan

Connect the GitHub MCP connector (or provide a read-only PAT) so `vinodirect` and
`v0-portfolio-website-creation` can be assessed, and so a full activity/PR/issue view is
available rather than a shallow clone snapshot.
