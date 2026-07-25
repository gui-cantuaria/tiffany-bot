# Automated deploy (GitHub Actions)

Production deploys can run automatically on push to `main`.

## Flow

```
git push main  →  GitHub Actions  →  SSH to server  →  scripts/deploy.sh  →  systemd restart
```

## One-time setup

### On the server

```bash
bash /opt/tiffany-bot/scripts/setup-github-actions.sh
```

Save the SSH key output for GitHub secrets.

### On GitHub

Repository → **Settings → Secrets and variables → Actions**:

| Secret | Value |
|--------|--------|
| `VPS_HOST` | Your server IP or hostname |
| `VPS_SSH_KEY` | Private key (`-----BEGIN...`) |

## Verify

- GitHub → **Actions** → **Deploy to VPS**
- On the server: `systemctl status tiffany-bot`

## Manual deploy (fallback)

```bash
cd /opt/tiffany-bot && git fetch origin main
git checkout origin/main -- launcher.py notices.py tiffany_voice.py offers_cog.py
systemctl restart tiffany-bot
```

Do **not** run `git pull` on a server with a local `.env`. Use `git checkout origin/main -- <files>` instead.

## Runtime JSON state

Deploy updates code and dependencies only. State files (`notices_history.json`, `chat_memory.json`, etc.) stay on the server. Back them up before migrating hosts.

## When SSH is still needed

- Editing `.env` (tokens, channel IDs)
- First-time WARP/proxy setup (see `docs/voice-technical.md`)
- Reading logs: `journalctl -u tiffany-bot -n 50 --no-pager`
