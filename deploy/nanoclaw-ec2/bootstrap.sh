#!/usr/bin/env bash
# bootstrap.sh — run ONCE after SSHing into the prepared EC2 host.
#
# Clones NanoClaw, runs the interactive setup (Docker container build, OneCLI
# credential registration, channel pairing), then installs the systemd service
# so it auto-starts on boot and restarts on crash.
#
# Prereqs: cloud-init.yaml already ran (Docker + Node 22 + pnpm present), and
# you've logged out/in once so the 'ubuntu' user is in the docker group.
#
# Azure DevOps repo needs auth — you'll be prompted for a username + PAT
# (Personal Access Token with Code:Read) at clone time. Override the URL with
# REPO_URL=... if you use a different remote (e.g. the public upstream).
set -euo pipefail

REPO_URL="${REPO_URL:-https://dev.azure.com/Payoneer/Payoneer/_git/nano-personal-assistant}"
TARGET="${TARGET:-$HOME/nanoclaw}"
KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "▸ Checking prerequisites…"
command -v docker >/dev/null || { echo "docker missing — run cloud-init first"; exit 1; }
command -v node   >/dev/null || { echo "node missing — run cloud-init first"; exit 1; }
docker info >/dev/null 2>&1 || { echo "Can't talk to Docker. Log out/in (docker group) and retry."; exit 1; }

if [ ! -d "$TARGET/.git" ]; then
  echo "▸ Cloning NanoClaw into $TARGET …"
  git clone "$REPO_URL" "$TARGET"
else
  echo "▸ Repo already present at $TARGET — pulling latest"
  git -C "$TARGET" pull --ff-only || true
fi

cd "$TARGET"
echo "▸ Running NanoClaw setup (interactive — pick Telegram for a headless server)…"
bash nanoclaw.sh

echo "▸ Building the host (dist/) so the systemd service can run it…"
pnpm install --frozen-lockfile
pnpm run build

echo "▸ Installing the systemd service…"
sudo TARGET="$TARGET" "$KIT_DIR/install-service.sh"

echo "✅ Done. NanoClaw is running under systemd."
echo "   Status:  systemctl status nanoclaw"
echo "   Logs:    journalctl -u nanoclaw -f"
