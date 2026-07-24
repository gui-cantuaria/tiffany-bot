#!/bin/bash
# Start Lavalink container (bot stays on systemd). Requires Docker.
set -e
cd /opt/tiffany-bot
if ! docker compose version &>/dev/null; then
  echo "Docker Compose not found."
  exit 1
fi
docker compose up -d lavalink
echo "Lavalink listening on 127.0.0.1:2333"
docker compose ps lavalink
