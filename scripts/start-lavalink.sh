#!/bin/bash
# Start Lavalink cluster (bot stays on systemd). Requires Docker + WARP on host :40000.
set -e
cd /opt/tiffany-bot
if ! docker compose version &>/dev/null; then
  echo "Docker Compose not found."
  exit 1
fi
echo "Config check:"
grep -E "lavasrc-plugin|deezer:" lavalink/application.yml | head -5
docker compose up -d lavalink-primary --force-recreate
echo "Lavalink primary on 127.0.0.1:2333 (WARP proxy via JAVA_TOOL_OPTIONS)"
sleep 3
docker compose ps lavalink-primary
docker logs lavalink-primary --tail 15 2>&1 | grep -iE "Started Lavalink|plugin|error|lavasrc" || true
