---
name: ai-trends-scan
description: Scan public sources for new AI coding tooling trends (Claude Code / Cursor / Copilot updates, new skill / rule / hook / sub-agent patterns), evaluate quality, and draft candidate additions to the dotfiles-ai repo. Outputs to proposals/<date>/. Trigger phrases — "scan AI trends", "what's new in AI coding tools", "find new skills", or run from cron via scripts/run-trends-scan.sh.
---

# AI Trends Scan

Run a daily-or-on-demand survey of the AI coding tooling ecosystem and draft
candidate additions to the dotfiles-ai repo. **Never auto-commit.** Always write
to `proposals/<YYYY-MM-DD>/` and let the human review.

## Inputs you can rely on

- Today's date: from `date +%Y-%m-%d`.
- Repo root: `git rev-parse --show-toplevel`.
- A list of sources to check (below).
- The repo's existing content under `.claude/` and `.cursor/` — to avoid
  proposing duplicates.

## Sources to check (in order)

### Tier A — official changelogs (always check)

1. **Anthropic Claude Code** — `https://docs.claude.com/en/release-notes/claude-code`
2. **Anthropic skills/agents/hooks docs** — index at `https://docs.claude.com/en/docs/claude-code/`
3. **Cursor changelog** — `https://cursor.com/changelog`
4. **GitHub Copilot release notes** — `https://github.blog/changelog/label/copilot/`
5. **MCP server registry updates** — `https://github.com/modelcontextprotocol/servers/commits/main`

### Tier B — community signal (high-signal aggregators)

6. **`awesome-claude-code`** — `https://github.com/hesreallyhim/awesome-claude-code` (commits since last scan)
7. **`awesome-cursor-rules`** — search GitHub for repos matching the pattern, sort by stars / recent activity
8. **r/ClaudeAI top posts (this week)** — best via the `/.json` endpoint
9. **Hacker News search** — `https://hn.algolia.com/?q=claude+code` filtered by date

### Tier C — your-stack relevance (keyword filters)

After collecting candidates, prefer items mentioning your team's stack. Edit this
list to match what you use (languages, frameworks, infra, CI, observability).
Down-rank items outside your stack unless they're general patterns.

## Workflow

### 1. Establish "since when"

Read `proposals/.last-scan` if it exists — that's the ISO date of the last
scan. If it doesn't exist, use 7 days ago.

### 2. Fetch sources

Use the `WebFetch` tool for each Tier A source. Extract entries newer than the
"since" date.

For Tier B, fetch the JSON / HTML and parse.

If the scan is rate-limited or a fetch fails, log it under "Sources I couldn't
read" in the digest — don't fabricate.

### 3. Score each candidate

For every candidate item (a new release note, a popular new skill, a new MCP
server), score it on this rubric:

| Dimension | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| Relevance to your stack | Off-topic | Tangential | Useful | Direct fit |
| Format quality | Broken | Loose Markdown | Skill/rule format | Drop-in ready |
| Novelty (we don't already have it) | Duplicate | Variant | Adjacent | New |
| Security posture | Adds risk | Neutral | Reduces risk | Hardens our setup |
| Maintainability | Brittle / cult | Single author | Multi-contributor | Official |

**Total /15.** Threshold for inclusion: ≥10. Below 10, mention in the digest as "considered, not drafted."

### 4. Draft candidate files

For each item scoring ≥10:

- Decide which folder it would go in (`.claude/agents/`, `.claude/skills/<name>/`,
  `.claude/hooks/`, `.cursor/rules/`).
- Write a draft file under `proposals/<YYYY-MM-DD>/<dest-folder>/<filename>`
  matching the destination layout. Include a `CANDIDATE` block at the top:

  ```
  <!--
  CANDIDATE — proposed by ai-trends-scan on <date>
  Source:    <URL>
  Score:     <N>/15  (R<n> F<n> N<n> S<n> M<n>)
  Rationale: <one sentence>
  Action:    Move to <dest-folder>/ and commit if accepted.
  -->
  ```

- For skills/sub-agents, include the proper YAML front matter so the file is
  drop-in valid.
- For Cursor rules, include the `description` / `globs` / `alwaysApply` block.

### 5. Write the digest

`proposals/<YYYY-MM-DD>/DIGEST.md` — one page, hyper-skimmable:

```markdown
# AI Trends — <YYYY-MM-DD>

## Drafted candidates (<N>)
- `<file>` — <one-line summary> — <score>/15
- ...

## Considered, not drafted (<M>)
- "<title>" — <score>/15 — <one-sentence why>

## Sources I couldn't read
- <URL> — <error>

## Suggested next actions
- Review `<file>`; high-confidence drop-in.
- Discuss "<title>" — borderline, may fit our stack.
```

### 6. Update `proposals/.last-scan`

Write today's ISO date to `proposals/.last-scan` so the next run knows where to
start.

### 7. Stop. Do NOT commit, do NOT push, do NOT modify any file under `.claude/`,
`.cursor/`, `mcp/`, or repo root.

## Rules

- **Never overwrite an existing skill / rule / agent / hook.** Always write under
  `proposals/`.
- **Never push.** That's the human's call.
- **Never include literal tokens** in any draft. If a source has them, redact.
- **Never propose an MCP server** unless its README documents env-var configuration.
- **Hard stop on >10 candidates per scan.** Daily noise is worse than missing
  one. If more pass the threshold, keep the top 10 by score.
- **Document the deduplication.** When proposing something we already have a
  variant of, name the existing file and explain the delta.

## Output for the user (printed at session end)

```
✅ AI trends scan complete — <date>
   <N> candidates drafted under proposals/<date>/
   <M> items considered, not drafted (see digest)
   Read: proposals/<date>/DIGEST.md
   Accept any: mv proposals/<date>/<file> .claude/<...>/<file>; git add ...; git commit
```
