#!/bin/bash
cd /opt/tiffany-bot
git fetch origin main --quiet
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)
if [ "$LOCAL" != "$REMOTE" ]; then
    echo "$(date): deploying..."
    git stash -q 2>/dev/null
    git checkout origin/main -- launcher.py notices.py tiffany_voice.py offers.py random_songs.py affiliate_config.py 2>/dev/null
    git stash pop -q 2>/dev/null
    systemctl restart tiffany-bot
    echo "$(date): done"
fi
