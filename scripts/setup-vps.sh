#!/bin/bash
# Setup script for new VPS (Docker-based deployment)
# Usage: curl -fsSL <raw-url> | bash
# Or: git clone repo && cd tiffany-bot && bash scripts/setup-vps.sh

set -e

echo "=== Tiffany Bot - VPS Setup ==="

# 1. Install Docker
if ! command -v docker &> /dev/null; then
    echo "[1/4] Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
else
    echo "[1/4] Docker already installed."
fi

# 2. Install Docker Compose plugin
if ! docker compose version &> /dev/null; then
    echo "[2/4] Installing Docker Compose plugin..."
    apt-get update && apt-get install -y docker-compose-plugin
else
    echo "[2/4] Docker Compose already installed."
fi

# 3. Setup project
echo "[3/4] Setting up project..."
cd "$(dirname "$0")/.."
mkdir -p data logs

# Copy .env if not exists
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo ">>> IMPORTANT: Edit .env with your tokens and secrets <<<"
    echo "    nano .env"
    echo ""
fi

# 4. Build and start
echo "[4/4] Building and starting containers..."
docker compose build
echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Edit .env with your secrets:  nano .env"
echo "  2. Copy data from old VPS:       scp old-vps:/opt/tiffany-bot/*.json ./data/"
echo "  3. Start the bot:                docker compose up -d"
echo "  4. Check logs:                   docker compose logs -f"
echo "  5. Update GitHub Secrets with new VPS IP and SSH key"
echo ""
