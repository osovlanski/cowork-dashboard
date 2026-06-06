# payoneer-ai-starter

A small, shareable Claude Code plugin that gives a teammate two things on day one:

1. **Safety hooks** — block secrets and destructive commands before they run, and
   protect sensitive/generated files from edits.
2. **The AI-trends-scan loop** — a skill (+ cron wrapper) that drafts candidate
   skills/rules/agents/hooks into `proposals/<date>/` for human review. Nothing
   auto-commits.

Distilled from the full `dotfiles-ai` repo into a one-install bundle so coworkers
get the highest-value pieces without cloning and running `setup.sh`.

## What's inside

| Component | Type | What it does |
|---|---|---|
| `pre-bash-block-destructive.sh` | PreToolUse hook (Bash) | Refuses `rm -rf`, `git reset --hard`, force-push, push-to-main, `DROP/DELETE/TRUNCATE`, `curl\|bash`, publish commands, etc. Bypass with `# allow:`. |
| `pre-bash-secret-scan.sh` | PreToolUse hook (Bash) | Refuses commands containing literal secrets (AWS keys, JWTs, GitHub PATs, `sk-…` keys, connection strings). Bypass with `# allow:`. |
| `pre-write-secret-scan.sh` | PreToolUse hook (Edit/Write) | Asks for confirmation when written content looks like a secret. |
| `protect-files.sh` | PreToolUse hook (Edit/Write) | Blocks edits to `.env`, TLS/SSH keys, lockfiles, generated code, `.git/`; asks on `.claude/settings.json`. |
| `ai-trends-scan` | Skill | Surveys AI-coding tooling sources and drafts proposals; never commits. |
| `scripts/run-trends-scan.sh` | Script | Headless cron wrapper for the scan. |

## Install

Share the `payoneer-ai-starter.plugin` file (drag into Cowork, or via the Claude
Code plugin install flow). Once installed:

- The hooks are active automatically on the relevant tool events.
- Ask Claude to **"scan AI trends"** to run the skill on demand, or wire the cron:

```sh
# Daily at 09:00, from inside the repo you want proposals written into:
0 9 * * *  cd /path/to/your/repo && /path/to/run-trends-scan.sh >> ~/trends-scan.log 2>&1
```

## Notes

- Hooks read the tool payload from **stdin** and use exit code 2 to block — the
  Claude Code hook protocol. They pass payloads to `python3` via env vars (not
  pipe-into-heredoc), which is the correct, non-silently-breaking pattern.
- The trends-scan skill writes only under `proposals/` and never pushes — review
  and `git mv` accepted candidates into place yourself.
- This is the internal Payoneer edition: the scan keeps the Payoneer-stack
  keyword filters (.NET, Mongo, Kafka, Azure DevOps, Coralogix). For a generic
  external version, strip the Tier-C block in `skills/ai-trends-scan/SKILL.md`.
- Full versions of these (plus formatters, test-gate, session-context hooks, the
  proposals review dashboard, and the dev-lifecycle orchestrator) live in
  `dotfiles-ai` — point teammates there once they want more.
