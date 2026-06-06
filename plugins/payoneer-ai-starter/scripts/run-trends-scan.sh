#!/bin/sh
# run-trends-scan — daily AI coding trends scan wrapper (plugin edition).
#
# Invokes Claude Code headlessly against the ai-trends-scan skill. Drafts
# candidate skills / rules / agents / hooks under proposals/<date>/ in the
# CURRENT repo. NEVER commits or pushes — the human reviews and accepts.
#
# Usage:
#   scripts/run-trends-scan.sh             # scan since the last run
#   scripts/run-trends-scan.sh --force     # ignore .last-scan, look back 7 days
#   scripts/run-trends-scan.sh --dry-run   # print plan, don't invoke claude
#
# Run this from the root of the repo you want proposals written into.

set -e

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
TODAY="$(date +%Y-%m-%d)"
PROPOSALS_DIR="$REPO_ROOT/proposals"
LAST_SCAN_FILE="$PROPOSALS_DIR/.last-scan"

DRY_RUN=0; FORCE=0
for arg in "$@"; do
  case "$arg" in
    --dry-run|-n) DRY_RUN=1 ;;
    --force|-f)   FORCE=1 ;;
    --help|-h)    sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)            echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done

mkdir -p "$PROPOSALS_DIR/$TODAY"

if [ -f "$LAST_SCAN_FILE" ] && [ "$FORCE" = "0" ]; then
  SINCE="$(cat "$LAST_SCAN_FILE")"
else
  SINCE="$(date -v-7d +%Y-%m-%d 2>/dev/null || date -d '7 days ago' +%Y-%m-%d)"
fi

echo "ai-trends-scan: $TODAY (since $SINCE) → $PROPOSALS_DIR/$TODAY"

if [ "$DRY_RUN" = "1" ]; then
  echo "[dry-run] would invoke Claude Code with the ai-trends-scan skill"
  exit 0
fi

if ! command -v claude > /dev/null 2>&1; then
  echo "claude not found. Install: npm install -g @anthropic-ai/claude-code" >&2
  exit 1
fi

PROMPT="Run the ai-trends-scan skill. Today is $TODAY. Last scan was $SINCE — use it as the 'since' date. Repo root is $REPO_ROOT. Write all output under $PROPOSALS_DIR/$TODAY/. Do not modify any other file. Do not commit. Do not push."

cd "$REPO_ROOT"
claude --dangerously-skip-permissions -p "$PROMPT" --output-format text

if [ -f "$PROPOSALS_DIR/$TODAY/DIGEST.md" ]; then
  echo "$TODAY" > "$LAST_SCAN_FILE"
  echo "✅ Done. Review: $PROPOSALS_DIR/$TODAY/DIGEST.md"
else
  echo "⚠️  Scan ran but no DIGEST.md produced." >&2
  exit 2
fi
