#!/usr/bin/env bash
# install-service.sh — install + start the NanoClaw systemd unit.
# Run with sudo. Honors TARGET (repo path); defaults to /home/ubuntu/nanoclaw.
set -euo pipefail

TARGET="${TARGET:-/home/ubuntu/nanoclaw}"
RUN_USER="${RUN_USER:-ubuntu}"
NODE_BIN="$(command -v node || echo /usr/bin/node)"
KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT=/etc/systemd/system/nanoclaw.service

if [ "$(id -u)" -ne 0 ]; then echo "Run with sudo."; exit 1; fi
[ -f "$TARGET/dist/index.js" ] || { echo "Missing $TARGET/dist/index.js — run 'pnpm run build' first."; exit 1; }

echo "▸ Writing $UNIT (target=$TARGET user=$RUN_USER node=$NODE_BIN)"
sed -e "s#/home/ubuntu/nanoclaw#$TARGET#g" \
    -e "s#^User=ubuntu#User=$RUN_USER#" \
    -e "s#^ExecStart=/usr/bin/node#ExecStart=$NODE_BIN#" \
    "$KIT_DIR/nanoclaw.service" > "$UNIT"

systemctl daemon-reload
systemctl enable nanoclaw
systemctl restart nanoclaw
sleep 2
systemctl --no-pager status nanoclaw || true
