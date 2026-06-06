# EC2 security group — NanoClaw

Default to **deny-all inbound except SSH from your own IP**. NanoClaw needs no
inbound ports for the recommended Telegram channel (it polls outbound), so keep
the box closed.

## Inbound rules

| Type | Port | Source | When |
|---|---|---|---|
| SSH | 22 | **My IP** (x.x.x.x/32) | Always — for setup/ops. Never `0.0.0.0/0`. |
| HTTPS | 443 | 0.0.0.0/0 | **Only** if you add a webhook-style channel (WhatsApp Cloud, Slack, Teams) that needs a public callback. Otherwise omit. |

## Outbound rules

| Type | Port | Destination | Why |
|---|---|---|---|
| All traffic | All | 0.0.0.0/0 | Anthropic API, Telegram/Docker registry, package installs. (Tighten later to 443 + Docker if you want.) |

## Channel guidance

- **Telegram (recommended for a server):** long-polls outbound — works with zero
  inbound ports. Easiest and safest for a headless EC2 box.
- **WhatsApp/Slack/Teams (webhook style):** need a public HTTPS endpoint. Add an
  Nginx/Caddy reverse proxy with a real domain + TLS, then open 443 only. Don't
  expose NanoClaw's port directly.

## Hardening checklist

- SSH key-only auth (AWS default); disable password auth.
- Restrict SSH source to your IP/CIDR, not the world.
- Keep the OneCLI vault (127.0.0.1:10254) bound to localhost — never expose it.
- Snapshot the EBS volume periodically (it holds the SQLite DBs + channel auth).
- If personal-use only, consider stop/start scheduling to cut cost.
