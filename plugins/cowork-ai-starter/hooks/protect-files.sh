#!/bin/sh
# protect-files — refuse Edit/Write that would touch sensitive or generated files.
#
# Wired as a PreToolUse hook on the Edit / Write tools. Blocks edits to:
#   Secrets:
#     .env / .env.*           (any environment file)
#     *.pem, *.key, *.crt     (TLS material)
#     *.p12, *.pfx            (cert bundles)
#     id_rsa, id_ed25519      (SSH keys)
#     credentials.json        (cloud SDK credential files)
#     .npmrc, .pypirc         (registry tokens)
#     anything in secrets/    (convention)
#
#   Lockfiles (regenerated, not hand-edited):
#     package-lock.json, yarn.lock, pnpm-lock.yaml, Cargo.lock,
#     poetry.lock, Gemfile.lock, composer.lock, go.sum
#
#   Generated code:
#     *.gen.{ts,js,go,cs,py}, *.generated.*, *.min.{js,css}
#
#   Tooling internals:
#     .git/* — never edit git internals from Claude
#     $HOME/.claude/hooks/*.{sh,py,js} — the live installed hook scripts
#       enforce security boundaries; edit the canonical copy under
#       dotfiles-ai/.claude/hooks/ and re-run setup.sh instead.
#
#   Asks confirmation (instead of blocking) for:
#     .claude/settings.json — controls hooks/permissions; non-trivial change

input="$(cat)"

file_path="$(HOOK_INPUT="$input" python3 <<'PY'
import json, os, sys
try:
    data = json.loads(os.environ.get("HOOK_INPUT", ""))
    print(data.get("tool_input", {}).get("file_path", ""))
except Exception:
    pass
PY
)"

[ -z "$file_path" ] && exit 0

basename="$(basename "$file_path")"

deny() {
  reason="$1"
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$reason"
  exit 2
}

ask() {
  reason="$1"
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"%s"}}\n' "$reason"
  exit 2
}

# ── Secrets ──
# Allow committed example/template variants (.env.example, .env.sample, etc.) — those
# don't carry real secrets and are how teams document the env shape.
case "$basename" in
  .env.example|.env.sample|.env.template|.env.dist|.env.defaults) ;;
  .env|.env.*) deny "Cannot edit .env files — secrets live there. Use .env.example for documentation." ;;
esac
case "$basename" in
  *.pem|*.key|*.crt|*.p12|*.pfx) deny "Cannot edit TLS / key material ($basename)." ;;
  id_rsa|id_rsa.pub|id_ed25519|id_ed25519.pub|id_ecdsa|id_ecdsa.pub) deny "Cannot edit SSH keys ($basename)." ;;
  credentials.json|application_default_credentials.json) deny "Cannot edit cloud SDK credential files." ;;
  .npmrc|.pypirc) deny "Cannot edit registry credential files ($basename)." ;;
esac

# ── Lockfiles ──
case "$basename" in
  package-lock.json|yarn.lock|pnpm-lock.yaml|Cargo.lock|poetry.lock|Gemfile.lock|composer.lock|go.sum)
    deny "Cannot edit $basename — regenerate via the package manager (npm install, cargo build, etc.)." ;;
esac

# ── Generated code ──
case "$basename" in
  *.gen.ts|*.gen.js|*.gen.go|*.gen.cs|*.gen.py|*.generated.*|*.min.js|*.min.css)
    deny "Cannot edit generated file $basename — regenerate from source." ;;
esac

# ── Path-based protections ──
# Only block the LIVE installed copy under $HOME/.claude/hooks/. Edits to the
# canonical source under dotfiles-ai/.claude/hooks/ are how you're supposed to
# change a hook (then re-run setup.sh). README.md and other docs in either
# location are also allowed — only executable script files are protected.
live_hooks_dir="$HOME/.claude/hooks"
case "$file_path" in
  .git/*|*/.git/*) deny "Cannot edit files inside .git/ — git internals." ;;
  secrets/*|*/secrets/*) deny "Cannot edit files inside secrets/ — convention says secrets live there." ;;
  "$live_hooks_dir"/*.sh|"$live_hooks_dir"/*.py|"$live_hooks_dir"/*.js)
    deny "Cannot edit live hook scripts in $live_hooks_dir/ — these enforce security boundaries. Edit the canonical version in dotfiles-ai/.claude/hooks/ and run setup.sh." ;;
  .claude/settings.json|*/.claude/settings.json)
    ask "Editing .claude/settings.json — controls hooks and permissions. Confirm this change." ;;
esac

exit 0
