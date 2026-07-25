#!/bin/bash
# Start Lavalink cluster (bot stays on systemd). Requires Docker + WARP on host :40000.
set -e
cd /opt/tiffany-bot
if ! docker compose version &>/dev/null; then
  echo "Docker Compose not found."
  exit 1
fi
docker compose up -d lavalink-primary
echo "Lavalink primary on 127.0.0.1:2333 (WARP proxy via JAVA_TOOL_OPTIONS)"
docker compose ps lavalink-primary
