#!/bin/sh
# pre-bash-block-destructive — refuse destructive shell commands.
#
# Wired as a PreToolUse hook on the Bash tool. Reads the tool input as JSON
# from stdin, exits 2 to block, exits 0 to allow.
#
# What it blocks:
#   File / OS:
#     rm -rf <anything>            (mass deletes)
#     chmod 777                    (world-writable permissions)
#     curl|wget piped to bash/sh   (remote-code execution)
#     mkfs / dd if= / >/dev/...    (disk destruction)
#
#   Git:
#     git reset --hard             (discards uncommitted work)
#     git clean -fd                (deletes untracked files)
#     git checkout -- .            (discards working-tree edits)
#     git restore .                (same)
#     git push --force / -f        (clobbers remote — use --force-with-lease)
#     git push to main/master      (must go through PR)
#
#   Containers / DB:
#     kubectl delete               (cluster destruction)
#     dropdb / DROP DATABASE       (DB destruction)
#     DROP TABLE / DROP SCHEMA     (DB destruction)
#     DELETE FROM ... (no WHERE)   (mass delete)
#     TRUNCATE TABLE               (DB destruction)
#
#   Package publishing (must go through CI):
#     npm / yarn / pnpm / bun publish
#     cargo publish
#     gem push
#     twine upload
#
# Bypass: prepend `# allow:` to the command. The hook will let it through.
#
# Exit codes:
#   0 — allow
#   2 — block, stderr is fed back to Claude as a tool error

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

# Bypass marker
case "$command" in
  *"# allow:"*) exit 0 ;;
esac

# Empty command → nothing to check
if [ -z "$command" ]; then
  exit 0
fi

# ──────────────────────────────────────────────────────────────────────
# Detection. Use python via env var (NOT stdin) — pipe+heredoc anti-pattern
# silently breaks: stdin gets bound to the heredoc and the piped text
# becomes part of the python source, raising SyntaxError.
# ──────────────────────────────────────────────────────────────────────
reason="$(HOOK_COMMAND="$command" python3 <<'PY'
import os, re, sys

text = os.environ.get("HOOK_COMMAND", "")

# (label, pattern, flags) — first match wins.
checks = [
    # Filesystem destruction
    ("rm -rf with broad target",
        r"(?:^|[\s;&|`(])rm\s+-[a-zA-Z]*(?:rf|fr)[a-zA-Z]*\s+(?:/|~|\$HOME|\.\./)", 0),
    ("rm -rf any path",
        r"(?:^|[\s;&|`(])rm\s+-[a-zA-Z]*(?:rf|fr)[a-zA-Z]*\s+\S", 0),

    # Permissions / RCE
    ("chmod 777",
        r"(?:^|[\s;&|`])chmod\s+777", 0),
    ("piping curl/wget to a shell",
        r"(?:curl|wget)\b[^|]*\|\s*(?:sudo\s+)?(?:bash|sh|zsh|fish|ksh)\b", 0),

    # Disk / device destruction
    ("disk format / device write",
        r"(?:^|[\s;&|`])(?:mkfs(?:\.\w+)?|dd\s+if=)\b|>\s*/dev/(?!null|stderr|stdout|tty)", 0),

    # Git destruction
    ("git reset --hard",
        r"\bgit\s+reset\s+--hard\b", 0),
    ("git clean -f",
        r"\bgit\s+clean\s+-[a-zA-Z]*f\b", 0),
    ("git checkout -- . (discards working tree)",
        r"\bgit\s+checkout\s+--\s+\.", 0),
    ("git restore . (discards working tree)",
        r"\bgit\s+restore\s+\.(?:\s|$)", 0),

    # Git push protections
    ("git push --force (use --force-with-lease)",
        r"\bgit\s+push\b[^|;&]*?\s(?:-[a-zA-Z]*f\b|--force\b)(?!-with-lease)", 0),
    ("git push to main/master",
        r"\bgit\s+push\b[^|;&]*?\s(?:origin\s+|:)?(?:main|master)\b", 0),

    # Cluster / DB destruction
    ("kubectl delete",
        r"\bkubectl\s+delete\b", 0),
    ("dropdb / DROP DATABASE",
        r"\bdropdb\b|\bdrop\s+database\b", re.IGNORECASE),
    ("DROP TABLE / DROP SCHEMA",
        r"\bdrop\s+(?:table|schema)\b", re.IGNORECASE),
    ("DELETE FROM without WHERE",
        r"\bdelete\s+from\s+[a-zA-Z_][\w.]*\s*(?:;|$)(?!.*\bwhere\b)", re.IGNORECASE | re.DOTALL),
    ("TRUNCATE TABLE",
        r"\btruncate\s+(?:table\s+)?\w+", re.IGNORECASE),

    # Package publishing (must go through CI)
    ("npm/yarn/pnpm/bun publish",
        r"\b(?:npm|yarn|pnpm|bun)\s+publish\b", 0),
    ("cargo publish",
        r"\bcargo\s+publish\b", 0),
    ("gem push",
        r"\bgem\s+push\b", 0),
    ("twine upload",
        r"\btwine\s+upload\b", 0),
]

for label, pat, flags in checks:
    if re.search(pat, text, flags):
        print(label)
        sys.exit(0)
PY
)"

if [ -n "$reason" ]; then
  cat >&2 <<EOF
🛑 Blocked by pre-bash-block-destructive hook: $reason

   $command

This command can destroy work, data, or production state irreversibly.
If you really need it:
  - Run it yourself in a terminal, OR
  - Re-issue with '# allow:' prepended to acknowledge the risk:
      # allow: $command

Specific guidance:
  - Force push    → use --force-with-lease (safer)
  - Push to main  → use a feature branch + PR
  - DELETE / DROP → run manually in your DB client
  - npm publish   → publish via CI pipeline, not Claude
EOF
  exit 2
fi

exit 0
