# NanoClaw on EC2 — deployment kit

Run your NanoClaw personal assistant on an always-on AWS EC2 box instead of your
Mac. The only real porting work vs. macOS is swapping the `launchd` plist for a
`systemd` service — this kit does that and preps the host.

**What's here**

| File | Purpose |
|---|---|
| `cloud-init.yaml` | EC2 user-data: installs Docker, Node 22, pnpm, build tools. |
| `bootstrap.sh` | Run once after SSH: clone, run setup, build, install service. |
| `install-service.sh` | Installs/enables/starts the systemd unit. |
| `nanoclaw.service` | The systemd unit (replaces `launchd/com.nanoclaw.plist`). |
| `.env.example` | Optional per-host env (e.g. `ASSISTANT_NAME`). |
| `security-group.md` | Inbound/outbound rules + channel guidance. |

## Manual steps (yours — AWS account + SSH)

1. **Launch an instance.** Ubuntu 24.04 LTS, **t3.medium** (2 vCPU / 4 GB) to
   start — Docker + the agent container need headroom; `t3.small` may be tight.
   Give it ~20 GB gp3 EBS.
2. **Key pair + security group.** Create/select an SSH key pair. Apply the rules
   in `security-group.md` (SSH from your IP only; no other inbound for Telegram).
3. **User data.** Paste the contents of `cloud-init.yaml` into *Advanced details →
   User data* at launch. (Or run it later — it's just the prereq installs.)
4. **Launch, then SSH in:** `ssh -i your-key.pem ubuntu@<public-ip>`. Log out and
   back in once so the `ubuntu` user picks up the `docker` group.

## Then (mostly automated)

5. Copy this `deploy/nanoclaw-ec2/` folder to the box (or `git clone` your cowork
   repo), then run:

   ```bash
   bash bootstrap.sh
   ```

   It clones NanoClaw (you'll be prompted for an **Azure DevOps PAT** with
   `Code:Read`, since the repo is private), runs `bash nanoclaw.sh` (interactive —
   **pick Telegram** for a headless server), builds `dist/`, and installs the
   systemd service. Override the source with `REPO_URL=...` if needed.

6. **Verify:**

   ```bash
   systemctl status nanoclaw      # should be active (running)
   journalctl -u nanoclaw -f      # live logs
   ```

   Then message your assistant on Telegram.

## Operating it

```bash
sudo systemctl restart nanoclaw     # restart
sudo systemctl stop nanoclaw        # stop
journalctl -u nanoclaw -f           # logs (replaces the launchd log files)
```

To update: `cd ~/nanoclaw && git pull && pnpm install && pnpm run build && sudo systemctl restart nanoclaw`.

## Notes & caveats

- **OneCLI vault.** `nanoclaw.sh` registers your Anthropic credential with the
  OneCLI gateway (localhost:10254). Confirm it comes back up on reboot; if it
  doesn't, check how `nanoclaw.sh` started it on Linux and add a matching systemd
  unit. Keep it bound to localhost — never expose it.
- **Apple-container docs don't apply.** The repo's `docs/APPLE-CONTAINER-NETWORKING.md`
  is macOS-only; on Linux the runtime is plain Docker, which cloud-init installed.
- **Secrets stay off this box's git.** API keys/channel tokens are managed by
  OneCLI, not committed. `.env` here is only for non-secret host settings.
- **Cost.** A t3.medium is ~$30/mo if always-on. For personal use, stop it when
  idle or schedule stop/start. The EBS volume persists your SQLite DBs + channel
  auth across stop/start — snapshot it for backup.
- **This folder lives in the cowork repo**, but it deploys the separate
  `nano-personal-assistant` repo — they're intentionally decoupled.
```
