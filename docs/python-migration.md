# Python 3.11+ Migration Plan

## Why
Ubuntu 22.04 ships **Python 3.10**. yt-dlp already prints:

```
Deprecated Feature: Support for Python version 3.10 has been deprecated.
Please update to Python 3.11 or above
```

The bot still works today, but yt-dlp will eventually **drop 3.10 support**. When
that happens, a `pip install -U yt-dlp` produces a build that refuses to run and
music breaks. Migrate before that deadline — this is not urgent, but plan it.

## Approach: isolated venv with Python 3.11 (deadsnakes)

This keeps the system Python untouched (Ubuntu tooling depends on it) and runs
Tiffany in its own interpreter. **Already wired up in the repo:**
- `scripts/run.sh` auto-selects `.venv/bin/python` if it exists, else system python3.
- `scripts/tiffany-bot.service` runs via `run.sh`.
- `scripts/deploy.sh` creates the venv and installs deps into it automatically.

So the only manual step on the VPS is creating the venv once:

```bash
# 1. Install Python 3.11 from the deadsnakes PPA
apt install -y software-properties-common
add-apt-repository -y ppa:deadsnakes/ppa
apt update
apt install -y python3.11 python3.11-venv python3.11-dev

# 2. Create the venv and install dependencies
cd /opt/tiffany-bot
python3.11 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# 3. Refresh the service (run.sh now picks up the venv automatically) and restart
cp scripts/run.sh /opt/tiffany-bot/scripts/run.sh 2>/dev/null || true
cp scripts/tiffany-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl restart tiffany-bot
systemctl status tiffany-bot
```

## Verification checklist
- [ ] `journalctl -u tiffany-bot -n 40` shows a clean startup (no import errors)
- [ ] `t!p <playlist>` works (yt-dlp + WARP)
- [ ] Voice/STT works (vosk, SpeechRecognition, edge-tts)
- [ ] News + offers cycles run
- [ ] No more "Python 3.10 deprecated" warning

## Rollback
`run.sh` falls back to system python3 automatically when the venv is absent.
So to roll back, just remove the venv and restart:

```bash
rm -rf /opt/tiffany-bot/.venv
systemctl restart tiffany-bot
```

## Alternative (simpler, less isolated)
Upgrade the whole VPS to Ubuntu 24.04 LTS (ships Python 3.12). Heavier operation
(full OS upgrade / reprovision) — prefer the venv route unless you're rebuilding
the VPS anyway.
