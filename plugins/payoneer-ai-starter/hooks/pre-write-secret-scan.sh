#!/bin/sh
# pre-write-secret-scan — refuse Edit/Write that would commit a literal secret.
#
# Wired as a PreToolUse hook on the Edit / Write tools. Scans the content
# being written for high-confidence secret patterns before it lands in a file
# (and probably soon after, in git history).
#
# Companion to pre-bash-secret-scan.sh, which scans Bash *commands*. Different
# tool, different surface, both useful.
#
# What it catches:
#   - AWS access keys (AKIA…)
#   - AWS secret access keys assigned to a key var (40-char base64 after =)
#   - GitHub tokens (ghp_/gho_/ghs_/ghr_/github_pat_…)
#   - OpenAI / Stripe / Anthropic style keys (sk-…)
#   - Slack tokens (xox[baprs]-…)
#   - Private key blocks (-----BEGIN ... PRIVATE KEY-----)
#   - Connection strings with embedded credentials (mongodb/postgres/mysql/etc)
#   - Generic credential assignments with a literal value (skips env-var refs)
#
# Decision: emits "ask" (not "deny") so the user can override — content can
# legitimately be a test fixture or a docs example. Override happens via the
# normal Claude Code permission dialog.

input="$(cat)"

content="$(HOOK_INPUT="$input" python3 <<'PY'
import json, os, sys
try:
    data = json.loads(os.environ.get("HOOK_INPUT", ""))
    tool = data.get("tool_name", "")
    ti = data.get("tool_input", {})
    if tool == "Write":
        print(ti.get("content", ""))
    elif tool == "Edit":
        print(ti.get("new_string", ""))
    elif tool == "MultiEdit":
        edits = ti.get("edits", [])
        print("\n".join(e.get("new_string", "") for e in edits if isinstance(e, dict)))
    # Other tools — no content to scan
except Exception:
    pass
PY
)"

if [ -z "$content" ]; then
  exit 0
fi

# Skip files that are documentation-by-convention. *.example / *.template /
# *.sample files and anything under /docs/ are committed docs, never real
# secrets. Real protection at this point is layered:
#   - commit-time hooks (pre-commit, gitleaks)
#   - server-side push scans
# So short-circuiting here trades a small layer-1 gap for the ability to
# pre-fill credential-shaped placeholders into example files without friction.
file_path="$(HOOK_INPUT="$input" python3 <<'PY'
import json, os
try:
    data = json.loads(os.environ.get("HOOK_INPUT", ""))
    print(data.get("tool_input", {}).get("file_path", ""))
except Exception:
    pass
PY
)"

case "$file_path" in
  *.example|*.template|*.sample|*/docs/*|*/docs)
    exit 0
    ;;
  # appsettings.Development.json is the .NET-standard committed dev-defaults file.
  # Loopback `changeme` placeholders shadow real secrets; production-like files
  # (appsettings.Production.json, appsettings.QA.json) are NOT in this exception
  # and are still scanned.
  */appsettings.Development.json|appsettings.Development.json)
    exit 0
    ;;
esac

findings="$(HOOK_CONTENT="$content" python3 <<'PY'
import os, re, sys

text = os.environ.get("HOOK_CONTENT", "")

patterns = [
    ("AWS access key (AKIA…)",
        r"AKIA[0-9A-Z]{16}", 0),
    ("AWS secret access key",
        r"(?i)(aws_secret_access_key|secret_access_key)\s*[=:]\s*[\"']?[A-Za-z0-9/+=]{40}", 0),
    ("GitHub token",
        r"\b(?:ghp_|gho_|ghs_|ghr_|github_pat_)[A-Za-z0-9_]{20,}", 0),
    ("OpenAI/Stripe/Anthropic key (sk-…)",
        r"\bsk-[A-Za-z0-9_-]{20,}", 0),
    ("Slack token",
        r"xox[baprs]-[A-Za-z0-9-]{10,}", 0),
    ("private key block",
        r"-----BEGIN[\s]+(?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", 0),
    ("connection string with credentials",
        r"\b(?:mongodb|postgres|postgresql|mysql|redis|amqp|smtp)(?:\+\w+)?://[^:\s]+:[^@\s]+@", 0),
]

hits = []
for label, pat, flags in patterns:
    if re.search(pat, text, flags):
        hits.append(label)

# Generic credential assignment with a literal value. Skip env-var references.
generic_re = re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|api[_-]?secret|pat)\b\s*[=:]\s*[\"']([^\"']{8,})[\"']")
env_ref_re = re.compile(r"^(?:process\.env|os\.environ|getenv|\$\{|ENV\[|env\(|\$[A-Z_])")
for m in generic_re.finditer(text):
    value = m.group(2)
    if not env_ref_re.match(value):
        hits.append(f"hardcoded {m.group(1).lower()}")
        break

print(",".join(hits))
PY
)"

if [ -n "$findings" ]; then
  # Use "ask" not "deny" — content might be a test fixture or doc example.
  reason="Possible secret in content: $findings. Review carefully before allowing."
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"%s"}}\n' "$reason"
  exit 2
fi

exit 0
