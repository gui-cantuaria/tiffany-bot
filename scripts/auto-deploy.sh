#!/bin/bash
cd /opt/tiffany-bot
git fetch origin main --quiet
REMOTE=$(git rev-parse origin/main)
LAST_DEPLOY_FILE="/opt/tiffany-bot/.last_deploy"
LAST_DEPLOY=$(cat "$LAST_DEPLOY_FILE" 2>/dev/null || echo "none")
if [ "$LAST_DEPLOY" != "$REMOTE" ]; then
    echo "$(date): deploying $REMOTE ..."
    git stash -q 2>/dev/null
    git checkout origin/main -- launcher.py notices.py tiffany_voice.py offers_cog.py random_songs.py affiliate_config.py 2>/dev/null
    git stash pop -q 2>/dev/null
    echo "$REMOTE" > "$LAST_DEPLOY_FILE"
    systemctl restart tiffany-bot
    echo "$(date): done"
fi
