#!/bin/sh
# pre-bash-secret-scan — refuse bash commands that contain literal secrets.
#
# Wired as a PreToolUse hook on the Bash tool. The goal is to make it harder
# to ever paste a real PAT, API key, JWT, or password into a command (where
# it would land in shell history, terminal scrollback, or tool logs).
#
# What it catches:
#   - AWS access keys (AKIA…)
#   - JWTs (eyJ…)
#   - Slack tokens (xox[baprs]-…)
#   - GitHub PATs (ghp_…) and OAuth/App tokens (gho_/ghs_/ghr_/github_pat_…)
#   - OpenAI / Stripe / Anthropic style keys (sk-…)
#   - Connection strings with embedded credentials (mongodb/postgres/mysql/etc)
#   - Generic credential assignments (password=…, api_key=…, etc) — skips
#     references like process.env.X / os.environ / ${VAR} / getenv(…)
#
# False positives: yes, sometimes. Override with '# allow:' prefix.
#
# Implementation note: pass payload via env var, NOT pipe-into-heredoc.
# `cmd | python3 - <<HEREDOC` looks correct but the heredoc takes over stdin,
# so the piped text becomes part of the python source and raises SyntaxError —
# the hook then silently allows everything. Using env vars sidesteps the issue.

input="$(cat)"

command="$(HOOK_INPUT="$input" python3 <<'PY'
import json, os, sys
try:
    data = json.loads(os.environ.get("HOOK_INPUT", ""))
    print(data.get("tool_input", {}).get("command", ""))
except Exception:
    pass
PY
)"

case "$command" in
  *"# allow:"*) exit 0 ;;
esac

if [ -z "$command" ]; then
  exit 0
fi

findings="$(HOOK_COMMAND="$command" python3 <<'PY'
import os, re, sys

text = os.environ.get("HOOK_COMMAND", "")

patterns = [
    ("AWS access key",   r"AKIA[0-9A-Z]{16}", 0),
    ("JWT",              r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", 0),
    ("Slack token",      r"xox[baprs]-[A-Za-z0-9-]{10,}", 0),
    ("GitHub token",     r"\b(?:ghp_|gho_|ghs_|ghr_|github_pat_)[A-Za-z0-9_]{20,}", 0),
    ("OpenAI/Stripe/Anthropic key (sk-…)", r"\bsk-[A-Za-z0-9_-]{20,}", 0),
    ("connection string with credentials",
        r"\b(?:mongodb|postgres|postgresql|mysql|redis|amqp|smtp)(?:\+\w+)?://[^:\s]+:[^@\s]+@", 0),
]

hits = []
for label, pat, flags in patterns:
    if re.search(pat, text, flags):
        hits.append(label)

# Generic credential assignment, but only if the value is a literal string
# (skip references like process.env.FOO, os.environ['FOO'], ${FOO}, getenv('FOO')).
generic_re   = re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|api[_-]?secret|pat)\b\s*[=:]\s*[\"']?([A-Za-z0-9_/+\-=.${}()\[\]]{8,})[\"']?")
env_ref_re   = re.compile(r"^(?:process\.env|os\.environ|getenv|\$\{|ENV\[|env\(|\$[A-Z_])")
for m in generic_re.finditer(text):
    value = m.group(2)
    if not env_ref_re.match(value):
        hits.append(f"hardcoded {m.group(1).lower()}")
        break

print(",".join(hits))
PY
)"

if [ -n "$findings" ]; then
  cat >&2 <<EOF
🛑 Blocked by pre-bash-secret-scan hook.

The command appears to contain a secret: $findings

   $command

If this is a false positive, prepend '# allow:' to the command:
   # allow: $command

If it's NOT a false positive — DO NOT run this. Either:
  • read the secret from an environment variable instead, or
  • read it from a file (~/.azdo/config, etc.).
EOF
  exit 2
fi

exit 0
